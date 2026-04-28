"""
签到任务服务层
提供签到任务的 CRUD 操作和执行功能
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.core.config import get_settings
from backend.utils.account_locks import get_account_lock
from backend.utils.proxy import build_proxy_dict
from backend.utils.tg_session import (
    get_account_proxy,
    get_account_session_string,
    get_account_status,
    get_global_semaphore,
    get_session_mode,
    load_session_string_file,
    set_account_status,
)
from tg_signer.core import UserSigner, get_client

settings = get_settings()


class TaskLogHandler(logging.Handler):
    """
    自定义日志处理器，将日志实时写入到内存列表中
    """

    def __init__(self, log_list: List[str]):
        super().__init__()
        self.log_list = log_list

    def emit(self, record):
        try:
            msg = self.format(record)
            self.log_list.append(msg)
            # 保持日志长度，避免内存占用过大
            if len(self.log_list) > 1000:
                self.log_list.pop(0)
        except Exception:
            self.handleError(record)


class BackendUserSigner(UserSigner):
    """
    后端专用的 UserSigner，适配后端目录结构并禁止交互式输入
    """

    @property
    def task_dir(self):
        # 适配后端的目录结构: signs_dir / account_name / task_name
        # self.tasks_dir -> workdir/signs
        return self.tasks_dir / self._account / self.task_name

    def ask_for_config(self):
        raise ValueError(
            f"任务配置文件不存在: {self.config_file}，且后端模式下禁止交互式输入。"
        )

    def reconfig(self):
        raise ValueError(
            f"任务配置文件不存在: {self.config_file}，且后端模式下禁止交互式输入。"
        )

    def ask_one(self):
        raise ValueError("后端模式下禁止交互式输入")


class SignTaskService:
    """签到任务服务类"""

    @staticmethod
    def _read_positive_int_env(name: str, default: int, minimum: int = 1) -> int:
        raw = os.getenv(name)
        if raw is None:
            return default
        try:
            return max(int(raw), minimum)
        except (TypeError, ValueError):
            return default

    def __init__(self):
        from backend.core.config import get_settings

        settings = get_settings()
        self.workdir = settings.resolve_workdir()
        self.signs_dir = self.workdir / "signs"
        self.run_history_dir = self.workdir / "history"
        self.signs_dir.mkdir(parents=True, exist_ok=True)
        self.run_history_dir.mkdir(parents=True, exist_ok=True)
        print(
            f"DEBUG: 初始化 SignTaskService, signs_dir={self.signs_dir}, exists={self.signs_dir.exists()}"
        )
        self._active_logs: Dict[tuple[str, str], List[str]] = {}  # (account, task) -> logs
        self._active_tasks: Dict[tuple[str, str], bool] = {}  # (account, task) -> running
        self._cleanup_tasks: Dict[tuple[str, str], asyncio.Task] = {}
        self._tasks_cache = None  # 内存缓存
        self._account_locks: Dict[str, asyncio.Lock] = {}  # 账号锁
        self._account_last_run_end: Dict[str, float] = {}  # 账号最后一次结束时间
        self._account_cooldown_seconds = int(
            os.getenv("SIGN_TASK_ACCOUNT_COOLDOWN", "5")
        )
        self._history_max_entries = self._read_positive_int_env(
            "SIGN_TASK_HISTORY_MAX_ENTRIES", 100, 10
        )
        self._history_max_flow_lines = self._read_positive_int_env(
            "SIGN_TASK_HISTORY_MAX_FLOW_LINES", 5000, 20
        )
        self._history_max_line_chars = self._read_positive_int_env(
            "SIGN_TASK_HISTORY_MAX_LINE_CHARS", 2000, 80
        )
        self._cleanup_old_logs()

    @staticmethod
    def _task_requires_updates(task_config: Optional[Dict[str, Any]]) -> bool:
        """
        判断任务是否依赖 update handlers。
        """
        if not isinstance(task_config, dict):
            return True
        chats = task_config.get("chats")
        if not isinstance(chats, list):
            return True
        response_actions = {3, 4, 5, 6, 7}
        for chat in chats:
            if not isinstance(chat, dict):
                continue
            actions = chat.get("actions")
            if not isinstance(actions, list):
                continue
            for action in actions:
                if not isinstance(action, dict):
                    continue
                try:
                    action_id = int(action.get("action"))
                except (TypeError, ValueError):
                    continue
                if action_id in response_actions:
                    return True
        return False

    def _cleanup_old_logs(self):
        """清理超过 3 天的日志"""
        from datetime import datetime, timedelta

        if not self.run_history_dir.exists():
            return

        limit = datetime.now() - timedelta(days=3)
        for log_file in self.run_history_dir.glob("*.json"):
            if log_file.stat().st_mtime < limit.timestamp():
                try:
                    log_file.unlink()
                except Exception:
                    continue

    def _safe_history_key(self, name: str) -> str:
        return name.replace("/", "_").replace("\\", "_")

    def _history_file_path(self, task_name: str, account_name: str = "") -> Path:
        if account_name:
            safe_account = self._safe_history_key(account_name)
            safe_task = self._safe_history_key(task_name)
            return self.run_history_dir / f"{safe_account}__{safe_task}.json"
        return self.run_history_dir / f"{self._safe_history_key(task_name)}.json"

    @staticmethod
    def _repair_mojibake(text: str) -> str:
        if not isinstance(text, str) or not text:
            return "" if text is None else str(text)

        suspicious_tokens = (
            "绛",
            "璐",
            "浠",
            "鐧",
            "鏃",
            "閰",
            "杩",
            "鍙",
            "鍦",
            "娑",
            "妫",
            "瀛",
            "�",
        )
        suspicious_count = sum(text.count(token) for token in suspicious_tokens)
        if suspicious_count < 2 and "�" not in text:
            return text

        try:
            candidate = text.encode("gbk", errors="strict").decode(
                "utf-8", errors="strict"
            )
        except Exception:
            return text

        candidate_suspicious = sum(
            candidate.count(token) for token in suspicious_tokens
        )
        if candidate_suspicious < suspicious_count:
            return candidate
        return text

    def _normalize_flow_logs(
        self, flow_logs: Optional[List[str]]
    ) -> tuple[List[str], bool, int]:
        if not isinstance(flow_logs, list):
            return [], False, 0

        total = len(flow_logs)
        trimmed: List[str] = []
        for line in flow_logs:
            text = self._repair_mojibake(str(line)).replace("\r", "").rstrip("\n")
            trimmed.append(text)
        return trimmed, False, total

    def _load_history_entries(
        self, task_name: str, account_name: str = ""
    ) -> List[Dict[str, Any]]:
        history_file = self._history_file_path(task_name, account_name)
        legacy_file = self.run_history_dir / f"{self._safe_history_key(task_name)}.json"

        if not history_file.exists():
            if account_name and legacy_file.exists():
                history_file = legacy_file
            elif not account_name and legacy_file.exists():
                history_file = legacy_file
            else:
                return []

        try:
            with open(history_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return []

        if isinstance(data, dict):
            data_list = [data]
        elif isinstance(data, list):
            data_list = data
        else:
            return []

        entries: List[Dict[str, Any]] = []
        for item in data_list:
            if not isinstance(item, dict):
                continue
            if account_name:
                item_account = item.get("account_name")
                if item_account and item_account != account_name:
                    continue
            entries.append(item)

        entries.sort(key=lambda x: x.get("time", ""), reverse=True)
        return entries

    def get_task_history_logs(
        self, task_name: str, account_name: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        if limit < 1:
            limit = 1
        if limit > 200:
            limit = 200

        history = self._load_history_entries(task_name, account_name=account_name)
        result: List[Dict[str, Any]] = []
        for item in history[:limit]:
            flow_logs = item.get("flow_logs")
            if not isinstance(flow_logs, list):
                flow_logs = []

            result.append(
                {
                    "time": item.get("time", ""),
                    "success": bool(item.get("success", False)),
                    "message": self._repair_mojibake(item.get("message", "") or ""),
                    "flow_logs": [self._repair_mojibake(str(line)) for line in flow_logs],
                    "flow_truncated": bool(item.get("flow_truncated", False)),
                    "flow_line_count": int(item.get("flow_line_count", len(flow_logs))),
                }
            )
        return result

    def get_account_history_logs(self, account_name: str) -> List[Dict[str, Any]]:
        """获取某账号下所有任务的最近历史日志"""
        all_history = []
        if not self.run_history_dir.exists():
            return []

        # 优化：先获取该账号下的任务列表，只读取相关任务的日志
        # 避免扫描整个 history 目录并读取所有文件
        tasks = self.list_tasks(account_name=account_name)

        for task in tasks:
            task_name = task["name"]
            history_file = self._history_file_path(task_name, account_name)

            if not history_file.exists():
                legacy_file = self.run_history_dir / f"{task_name}.json"
                if legacy_file.exists():
                    history_file = legacy_file
                else:
                    continue

            try:
                with open(history_file, "r", encoding="utf-8") as f:
                    data_list = json.load(f)
                    if not isinstance(data_list, list):
                        data_list = [data_list]

                    # 再次确认 account_name (虽然是从 task 列表来的，但以防万一)
                    for data in data_list:
                        if data.get("account_name") == account_name:
                            data["task_name"] = task_name
                            data["message"] = self._repair_mojibake(
                                data.get("message", "") or ""
                            )
                            flow_logs = data.get("flow_logs")
                            if isinstance(flow_logs, list):
                                data["flow_logs"] = [
                                    self._repair_mojibake(str(line))
                                    for line in flow_logs
                                ]
                            all_history.append(data)
            except Exception:
                continue

        # 按时间倒序
        all_history.sort(key=lambda x: x.get("time", ""), reverse=True)
        return all_history

    def clear_account_history_logs(self, account_name: str) -> Dict[str, int]:
        """娓呯悊鏌愯处鍙风殑鍘嗗彶鏃ュ織锛屼笉褰卞搷鍏朵粬璐﹀彿"""
        removed_files = 0
        removed_entries = 0

        if not self.run_history_dir.exists():
            return {"removed_files": 0, "removed_entries": 0}

        def _count_entries(data: Any) -> int:
            if isinstance(data, list):
                return len(data)
            if isinstance(data, dict):
                return 1
            return 0

        tasks = self.list_tasks(account_name=account_name)
        for task in tasks:
            task_name = task.get("name") or ""
            if not task_name:
                continue

            # --- CLEAR TASK LAST RUN METADATA ---
            task_dir = self.signs_dir / account_name / task_name
            if not task_dir.exists():
                task_dir = self.signs_dir / task_name
            config_file = task_dir / "config.json"
            if config_file.exists():
                try:
                    import json
                    with open(config_file, "r", encoding="utf-8") as f:
                        config = json.load(f)
                    if "last_run" in config:
                        del config["last_run"]
                        with open(config_file, "w", encoding="utf-8") as f:
                            json.dump(config, f, ensure_ascii=False, indent=2)
                except Exception:
                    pass

            if self._tasks_cache is not None:
                for t in self._tasks_cache:
                    if t["name"] == task_name and t.get("account_name") == account_name:
                        t.pop("last_run", None)
                        break
            # ------------------------------------

            history_file = self._history_file_path(task_name, account_name)
            if history_file.exists():
                try:
                    with open(history_file, "r", encoding="utf-8") as f:
                        removed_entries += _count_entries(json.load(f))
                except Exception:
                    pass
                try:
                    history_file.unlink()
                    removed_files += 1
                except Exception:
                    pass
                continue

            legacy_file = self.run_history_dir / f"{self._safe_history_key(task_name)}.json"
            if not legacy_file.exists():
                continue

            try:
                with open(legacy_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    data_list = [data]
                elif isinstance(data, list):
                    data_list = data
                else:
                    data_list = []
            except Exception:
                continue

            if not data_list:
                try:
                    legacy_file.unlink()
                    removed_files += 1
                except Exception:
                    pass
                continue

            # legacy 鏂囦欢鍙兘娌℃湁 account_name 锛屾槸鏃х増鍗曡处鍙峰湺鏅?
            has_account_field = any(
                isinstance(item, dict) and "account_name" in item for item in data_list
            )
            if not has_account_field:
                removed_entries += len(data_list)
                try:
                    legacy_file.unlink()
                    removed_files += 1
                except Exception:
                    pass
                continue

            kept: List[Dict[str, Any]] = []
            for item in data_list:
                if not isinstance(item, dict):
                    continue
                if item.get("account_name") == account_name:
                    removed_entries += 1
                else:
                    kept.append(item)

            if not kept:
                try:
                    legacy_file.unlink()
                    removed_files += 1
                except Exception:
                    pass
            else:
                try:
                    with open(legacy_file, "w", encoding="utf-8") as f:
                        json.dump(kept, f, ensure_ascii=False, indent=2)
                except Exception:
                    pass

        return {"removed_files": removed_files, "removed_entries": removed_entries}

    def _get_last_run_info(
        self, task_dir: Path, account_name: str = ""
    ) -> Optional[Dict[str, Any]]:
        """
        获取任务的最后执行信息
        """
        history_file = self._history_file_path(task_dir.name, account_name)
        legacy_file = self.run_history_dir / f"{task_dir.name}.json"

        if not history_file.exists():
            if account_name and legacy_file.exists():
                history_file = legacy_file
            else:
                return None

        try:
            with open(history_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and len(data) > 0:
                    return data[0]  # 最近的一条
                elif isinstance(data, dict):
                    return data
                return None
        except Exception:
            return None

    def _save_run_info(
        self,
        task_name: str,
        success: bool,
        message: str = "",
        account_name: str = "",
        flow_logs: Optional[List[str]] = None,
    ):
        """保存任务执行历史 (保留列表)"""
        from datetime import datetime

        history_file = self._history_file_path(task_name, account_name)
        normalized_logs, flow_truncated, flow_line_count = self._normalize_flow_logs(
            flow_logs
        )

        new_entry = {
            "time": datetime.now().isoformat(),
            "success": success,
            "message": self._repair_mojibake(message),
            "account_name": account_name,
            "flow_logs": normalized_logs,
            "flow_truncated": flow_truncated,
            "flow_line_count": flow_line_count,
        }

        history = []
        if history_file.exists():
            try:
                with open(history_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        history = data
                    else:
                        history = [data]
            except Exception:
                history = []

        history.insert(0, new_entry)
        # 只保留最近 N 条
        history = history[: self._history_max_entries]

        try:
            with open(history_file, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=2)

            # 同时更新任务配置中的 last_run
            # 1. 更新磁盘上的 config.json
            task = self.get_task(task_name, account_name)
            if task:
                # 注意 get_task 返回的是 dict，我们需要路径
                # 重新构建路径或复用逻辑
                # 这里为了简单，再次查找路径有点低效，但比全量扫描好
                # 我们可以利用 self.signs_dir / account_name / task_name
                # 但考虑到兼容性，还是得稍微判断下
                task_dir = self.signs_dir / account_name / task_name
                if not task_dir.exists():
                    task_dir = self.signs_dir / task_name

                config_file = task_dir / "config.json"
                if config_file.exists():
                    try:
                        with open(config_file, "r", encoding="utf-8") as f:
                            config = json.load(f)
                        config["last_run"] = new_entry
                        with open(config_file, "w", encoding="utf-8") as f:
                            json.dump(config, f, ensure_ascii=False, indent=2)
                    except Exception as e:
                        print(f"DEBUG: 更新任务配置 last_run 失败: {e}")

            # 2. 更新内存缓存 (关键优化：避免置空 self._tasks_cache)
            if self._tasks_cache is not None:
                for t in self._tasks_cache:
                    if t["name"] == task_name and t.get("account_name") == account_name:
                        t["last_run"] = new_entry
                        break

        except Exception as e:
            print(f"DEBUG: 保存运行信息失败: {str(e)}")

    def _append_scheduler_log(self, filename: str, message: str) -> None:
        try:
            logs_dir = settings.resolve_logs_dir()
            logs_dir.mkdir(parents=True, exist_ok=True)
            log_path = logs_dir / filename
            with open(log_path, 'a', encoding='utf-8') as f:
                f.write(f'{message}\n')
        except Exception as e:
            logging.getLogger('backend.sign_tasks').warning(
                'Failed to write scheduler log %s: %s', filename, e
            )

    def _get_effective_proxy(self, account_name: str) -> Optional[str]:
        proxy_value = get_account_proxy(account_name)
        if proxy_value:
            return proxy_value
        try:
            from backend.services.config import get_config_service

            global_proxy = get_config_service().get_global_settings().get("global_proxy")
            if isinstance(global_proxy, str) and global_proxy.strip():
                return global_proxy.strip()
        except Exception:
            pass
        return None

    async def _send_failure_notification(
        self,
        account_name: str,
        task_name: str,
        message: str,
        flow_logs: Optional[List[str]] = None,
    ) -> None:
        try:
            from backend.services.config import get_config_service

            cfg = get_config_service().get_global_settings()
            if not cfg.get("telegram_bot_notify_enabled"):
                return
            bot_token = (cfg.get("telegram_bot_token") or "").strip()
            chat_id = (cfg.get("telegram_bot_chat_id") or "").strip()
            if not bot_token or not chat_id:
                return
            message_thread_id = cfg.get("telegram_bot_message_thread_id")
            try:
                message_thread_id = (
                    int(message_thread_id)
                    if message_thread_id is not None and str(message_thread_id).strip()
                    else None
                )
            except (TypeError, ValueError):
                message_thread_id = None

            log_tail = "\n".join((flow_logs or [])[-20:])
            text = (
                "TG-SignPulse 任务执行失败\n"
                f"账号: {account_name}\n"
                f"任务: {task_name}\n"
                f"错误: {message or '未知错误'}"
            )
            if log_tail:
                text += f"\n\n最近日志:\n{log_tail}"
            from backend.services.push_notifications import send_telegram_bot_message

            await send_telegram_bot_message(
                bot_token=bot_token,
                chat_id=chat_id,
                text=text,
                message_thread_id=message_thread_id,
            )
        except Exception as e:
            logging.getLogger("backend.sign_tasks").warning(
                "Failed to send Telegram failure notification: %s", e
            )

    async def _send_account_invalid_notification(
        self,
        account_name: str,
        task_name: str,
        message: str,
    ) -> None:
        try:
            from backend.services.config import get_config_service

            cfg = get_config_service().get_global_settings()
            if not cfg.get("telegram_bot_notify_enabled"):
                return
            bot_token = (cfg.get("telegram_bot_token") or "").strip()
            chat_id = (cfg.get("telegram_bot_chat_id") or "").strip()
            if not bot_token or not chat_id:
                return
            message_thread_id = cfg.get("telegram_bot_message_thread_id")
            try:
                message_thread_id = (
                    int(message_thread_id)
                    if message_thread_id is not None and str(message_thread_id).strip()
                    else None
                )
            except (TypeError, ValueError):
                message_thread_id = None

            text = (
                "TG-SignPulse 账号登录失效\n"
                f"账号: {account_name}\n"
                f"触发任务: {task_name}\n"
                f"原因: {message or 'session 已失效，请重新登录'}\n\n"
                "该账号下的任务已跳过。"
            )
            from backend.services.push_notifications import send_telegram_bot_message

            await send_telegram_bot_message(
                bot_token=bot_token,
                chat_id=chat_id,
                text=text,
                message_thread_id=message_thread_id,
            )
        except Exception as e:
            logging.getLogger("backend.sign_tasks").warning(
                "Failed to send Telegram account invalid notification: %s", e
            )

    async def _mark_account_invalid(
        self,
        account_name: str,
        task_name: str,
        message: str,
    ) -> bool:
        current = get_account_status(account_name)
        already_notified = bool(current.get("invalid_notified_at"))
        notified_at = current.get("invalid_notified_at") or datetime.utcnow().isoformat()
        set_account_status(
            account_name,
            status="invalid",
            message=message,
            code="ACCOUNT_SESSION_INVALID",
            needs_relogin=True,
            invalid_notified_at=notified_at,
        )
        if not already_notified:
            await self._send_account_invalid_notification(
                account_name=account_name,
                task_name=task_name,
                message=message,
            )
        return not already_notified

    async def _check_account_before_task(
        self,
        account_name: str,
        task_name: str,
    ) -> Optional[str]:
        stored_status = get_account_status(account_name)
        if (
            stored_status.get("status") == "invalid"
            and stored_status.get("needs_relogin")
        ):
            message = (
                str(stored_status.get("message") or "").strip()
                or f"账号 {account_name} 登录已失效，请重新登录"
            )
            await self._mark_account_invalid(account_name, task_name, message)
            return message

        try:
            from backend.services.telegram import get_telegram_service

            result = await get_telegram_service().check_account_status(
                account_name, timeout_seconds=10.0
            )
        except Exception as e:
            logging.getLogger("backend.sign_tasks").warning(
                "Account status check failed before task %s/%s: %s",
                account_name,
                task_name,
                e,
            )
            return None

        if result.get("ok"):
            return None

        needs_relogin = bool(result.get("needs_relogin"))
        status = str(result.get("status") or "")
        code = str(result.get("code") or "")
        if needs_relogin or status in {"invalid", "not_found"} or code == "ACCOUNT_SESSION_INVALID":
            message = (
                str(result.get("message") or "").strip()
                or f"账号 {account_name} 登录已失效，请重新登录"
            )
            await self._mark_account_invalid(account_name, task_name, message)
            return message

        return None

    def list_tasks(
        self, account_name: Optional[str] = None, force_refresh: bool = False
    ) -> List[Dict[str, Any]]:
        """
        获取所有签到任务列表 (支持内存缓存)
        """
        if self._tasks_cache is not None and not force_refresh:
            if account_name:
                return [
                    t
                    for t in self._tasks_cache
                    if t.get("account_name") == account_name
                ]
            return self._tasks_cache

        tasks = []
        base_dir = self.signs_dir

        print(f"DEBUG: 扫描任务目录: {base_dir}")
        try:
            # 扫描所有子目录 (账号名)
            for account_path in base_dir.iterdir():
                if not account_path.is_dir():
                    # 兼容旧路径：直接在 signs 目录下的任务
                    if (account_path / "config.json").exists():
                        task_info = self._load_task_config(account_path)
                        if task_info:
                            tasks.append(task_info)
                    continue

                # 扫描账号目录下的任务
                for task_dir in account_path.iterdir():
                    if not task_dir.is_dir():
                        continue

                    task_info = self._load_task_config(task_dir)
                    if task_info:
                        tasks.append(task_info)

            self._tasks_cache = sorted(
                tasks, key=lambda x: (x["account_name"], x["name"])
            )

            if account_name:
                return [
                    t
                    for t in self._tasks_cache
                    if t.get("account_name") == account_name
                ]
            return self._tasks_cache

        except Exception as e:
            print(f"DEBUG: 扫描任务出错: {str(e)}")
            return []

    def _load_task_config(self, task_dir: Path) -> Optional[Dict[str, Any]]:
        """加载单个任务配置，优先使用 config.json 中的 last_run"""
        config_file = task_dir / "config.json"
        if not config_file.exists():
            return None

        try:
            with open(config_file, "r", encoding="utf-8") as f:
                config = json.load(f)

            # 优先从 config 读取 last_run
            last_run = config.get("last_run")
            if not last_run:
                last_run = self._get_last_run_info(
                    task_dir, account_name=config.get("account_name", "")
                )

            return {
                "name": task_dir.name,
                "account_name": config.get("account_name", ""),
                "sign_at": config.get("sign_at", ""),
                "random_seconds": config.get("random_seconds", 0),
                "sign_interval": config.get("sign_interval", 1),
                "chats": config.get("chats", []),
                "enabled": True,
                "last_run": last_run,
                "execution_mode": config.get("execution_mode", "fixed"),
                "range_start": config.get("range_start", ""),
                "range_end": config.get("range_end", ""),
            }
        except Exception:
            return None

    def get_task(
        self, task_name: str, account_name: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        获取单个任务的详细信息
        """
        if account_name:
            task_dir = self.signs_dir / account_name / task_name
        else:
            # 搜索模式 (兼容旧版或未传 account_name 的情况)
            task_dir = self.signs_dir / task_name
            if not (task_dir / "config.json").exists():
                # 在所有账号目录下搜
                for acc_dir in self.signs_dir.iterdir():
                    if (
                        acc_dir.is_dir()
                        and (acc_dir / task_name / "config.json").exists()
                    ):
                        task_dir = acc_dir / task_name
                        break

        config_file = task_dir / "config.json"

        if not config_file.exists():
            return None

        try:
            with open(config_file, "r", encoding="utf-8") as f:
                config = json.load(f)

            return {
                "name": task_name,
                "account_name": config.get("account_name", ""),
                "sign_at": config.get("sign_at", ""),
                "random_seconds": config.get("random_seconds", 0),
                "sign_interval": config.get("sign_interval", 1),
                "chats": config.get("chats", []),
                "enabled": True,
                "execution_mode": config.get("execution_mode", "fixed"),
                "range_start": config.get("range_start", ""),
                "range_end": config.get("range_end", ""),
            }
        except Exception:
            return None

    def create_task(
        self,
        task_name: str,
        sign_at: str,
        chats: List[Dict[str, Any]],
        random_seconds: int = 0,
        sign_interval: Optional[int] = None,
        account_name: str = "",
        execution_mode: str = "fixed",
        range_start: str = "",
        range_end: str = "",
    ) -> Dict[str, Any]:
        """
        创建新的签到任务
        """
        import random

        from backend.services.config import get_config_service

        if not account_name:
            raise ValueError("必须指定账号名称")

        account_dir = self.signs_dir / account_name
        account_dir.mkdir(parents=True, exist_ok=True)

        task_dir = account_dir / task_name
        task_dir.mkdir(parents=True, exist_ok=True)

        # 获取 sign_interval
        if sign_interval is None:
            config_service = get_config_service()
            global_settings = config_service.get_global_settings()
            sign_interval = global_settings.get("sign_interval")

        if sign_interval is None:
            sign_interval = random.randint(1, 120)

        config = {
            "_version": 3,
            "account_name": account_name,
            "sign_at": sign_at,
            "random_seconds": random_seconds,
            "sign_interval": sign_interval,
            "chats": chats,
            "execution_mode": execution_mode,
            "range_start": range_start,
            "range_end": range_end,
        }

        config_file = task_dir / "config.json"

        try:
            with open(config_file, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"DEBUG: 写入配置文件失败: {str(e)}")
            raise

        # Invalidate cache
        self._tasks_cache = None

        try:
            from backend.scheduler import add_or_update_sign_task_job

            add_or_update_sign_task_job(
                account_name,
                task_name,
                range_start if execution_mode == "range" else sign_at,
                enabled=True,
            )
        except Exception as e:
            print(f"DEBUG: 更新调度任务失败: {e}")

        return {
            "name": task_name,
            "account_name": account_name,
            "sign_at": sign_at,
            "random_seconds": random_seconds,
            "sign_interval": sign_interval,
            "chats": chats,
            "enabled": True,
            "execution_mode": execution_mode,
            "range_start": range_start,
            "range_end": range_end,
        }

    def update_task(
        self,
        task_name: str,
        sign_at: Optional[str] = None,
        chats: Optional[List[Dict[str, Any]]] = None,
        random_seconds: Optional[int] = None,
        sign_interval: Optional[int] = None,
        account_name: Optional[str] = None,
        execution_mode: Optional[str] = None,
        range_start: Optional[str] = None,
        range_end: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        更新签到任务
        """
        # 获取现有配置
        existing = self.get_task(task_name, account_name)
        if not existing:
            raise ValueError(f"任务 {task_name} 不存在")

        # Determine the account name for the update.
        # If a new account_name is provided, use it. Otherwise, use the existing one.
        acc_name = (
            account_name
            if account_name is not None
            else existing.get("account_name", "")
        )

        # 更新配置
        config = {
            "_version": 3,
            "account_name": acc_name,
            "sign_at": sign_at if sign_at is not None else existing["sign_at"],
            "random_seconds": random_seconds
            if random_seconds is not None
            else existing["random_seconds"],
            "sign_interval": sign_interval
            if sign_interval is not None
            else existing["sign_interval"],
            "chats": chats if chats is not None else existing["chats"],
            "execution_mode": execution_mode
            if execution_mode is not None
            else existing.get("execution_mode", "fixed"),
            "range_start": range_start
            if range_start is not None
            else existing.get("range_start", ""),
            "range_end": range_end
            if range_end is not None
            else existing.get("range_end", ""),
        }

        # 保存配置
        task_dir = self.signs_dir / acc_name / task_name
        if not task_dir.exists():
            # 兼容旧路径
            task_dir = self.signs_dir / task_name

        config_file = task_dir / "config.json"
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

        # Invalidate cache
        self._tasks_cache = None

        try:
            from backend.scheduler import add_or_update_sign_task_job

            add_or_update_sign_task_job(
                config["account_name"],
                task_name,
                config.get("range_start")
                if config.get("execution_mode") == "range"
                else config["sign_at"],
                enabled=True,
            )
        except Exception as e:
            msg = f"DEBUG: 更新调度任务失败: {e}"
            print(msg)
            self._append_scheduler_log(
                "scheduler_error.log", f"{datetime.now()}: {msg}"
            )
        else:
            self._append_scheduler_log(
                "scheduler_update.log",
                f"{datetime.now()}: Updated task {task_name} with cron {config.get('range_start') if config.get('execution_mode') == 'range' else config['sign_at']}",
            )

        return {
            "name": task_name,
            "account_name": config["account_name"],
            "sign_at": config["sign_at"],
            "random_seconds": config["random_seconds"],
            "sign_interval": config["sign_interval"],
            "chats": config["chats"],
            "enabled": True,
            "execution_mode": config.get("execution_mode", "fixed"),
            "range_start": config.get("range_start", ""),
            "range_end": config.get("range_end", ""),
        }

    def delete_task(self, task_name: str, account_name: Optional[str] = None) -> bool:
        """
        删除签到任务
        """
        task_dir = None
        if account_name:
            task_dir = self.signs_dir / account_name / task_name
            # 如果指定了账号但任务不存在，直接返回失败，不进行搜索
            if not task_dir.exists():
                return False
        else:
            # 未指定账号，尝试搜索 (兼容旧逻辑，但不推荐)
            task_dir = self.signs_dir / task_name
            if not task_dir.exists():
                for acc_dir in self.signs_dir.iterdir():
                    if acc_dir.is_dir() and (acc_dir / task_name).exists():
                        task_dir = acc_dir / task_name
                        break

        if not task_dir or not task_dir.exists():
            return False

        # 确定真实的 account_name，以便移除调度
        real_account_name = account_name
        if not real_account_name:
            # 尝试从路径推断
            if task_dir.parent.parent == self.signs_dir:
                real_account_name = task_dir.parent.name
            else:
                # 回退尝试读取 config
                try:
                    with open(task_dir / "config.json", "r") as f:
                        real_account_name = json.load(f).get("account_name")
                except Exception:
                    pass

        try:
            import shutil

            shutil.rmtree(task_dir)
            # Invalidate cache
            self._tasks_cache = None

            if real_account_name:
                try:
                    from backend.scheduler import remove_sign_task_job

                    remove_sign_task_job(real_account_name, task_name)
                except Exception as e:
                    print(f"DEBUG: 移除调度任务失败: {e}")

            return True
        except Exception:
            return False

    async def get_account_chats(
        self, account_name: str, force_refresh: bool = False
    ) -> List[Dict[str, Any]]:
        """
        获取账号的 Chat 列表 (带缓存)
        """
        cache_file = self.signs_dir / account_name / "chats_cache.json"

        if not force_refresh and cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass

        # 如果没有缓存或强制刷新，执行刷新逻辑
        return await self.refresh_account_chats(account_name)

    def search_account_chats(
        self,
        account_name: str,
        query: str,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """
        通过缓存搜索账号的 Chat 列表（不触发全量 get_dialogs）
        """
        cache_file = self.signs_dir / account_name / "chats_cache.json"

        if limit < 1:
            limit = 1
        if limit > 200:
            limit = 200
        if offset < 0:
            offset = 0

        if not cache_file.exists():
            return {"items": [], "total": 0, "limit": limit, "offset": offset}

        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return {"items": [], "total": 0, "limit": limit, "offset": offset}

        if not isinstance(data, list):
            return {"items": [], "total": 0, "limit": limit, "offset": offset}

        q = (query or "").strip()
        if not q:
            total = len(data)
            return {
                "items": data[offset : offset + limit],
                "total": total,
                "limit": limit,
                "offset": offset,
            }

        is_numeric = q.lstrip("-").isdigit()
        if is_numeric or q.startswith("-100"):
            def match(chat: Dict[str, Any]) -> bool:
                chat_id = chat.get("id")
                if chat_id is None:
                    return False
                return q in str(chat_id)
        else:
            q_lower = q.lower()

            def match(chat: Dict[str, Any]) -> bool:
                title = (chat.get("title") or "").lower()
                username = (chat.get("username") or "").lower()
                return q_lower in title or q_lower in username

        filtered = [c for c in data if match(c)]
        total = len(filtered)
        return {
            "items": filtered[offset : offset + limit],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    @staticmethod
    def _is_invalid_session_error(err: Exception) -> bool:
        msg = str(err)
        if not msg:
            return False
        upper = msg.upper()
        return (
            "AUTH_KEY_UNREGISTERED" in upper
            or "AUTH_KEY_INVALID" in upper
            or "SESSION_REVOKED" in upper
            or "SESSION_EXPIRED" in upper
            or "USER_DEACTIVATED" in upper
        )

    async def _cleanup_invalid_session(self, account_name: str) -> None:
        try:
            from backend.services.telegram import get_telegram_service

            await get_telegram_service().delete_account(account_name)
        except Exception as e:
            print(f"DEBUG: 清理无效 Session 失败: {e}")

        # 清理 chats 缓存，避免后续误用旧数据
        try:
            cache_file = self.signs_dir / account_name / "chats_cache.json"
            if cache_file.exists():
                cache_file.unlink()
        except Exception:
            pass

    async def refresh_account_chats(self, account_name: str) -> List[Dict[str, Any]]:
        """
        连接 Telegram 并刷新 Chat 列表
        """
        from pyrogram.enums import ChatType

        # 获取 session 文件路径
        from backend.core.config import get_settings
        from backend.services.config import get_config_service

        settings = get_settings()
        session_dir = settings.resolve_session_dir()
        session_mode = get_session_mode()
        session_string = None
        fallback_session_string = None
        used_fallback_session = False
        session_file = session_dir / f"{account_name}.session"

        if session_mode == "string":
            session_string = (
                get_account_session_string(account_name)
                or load_session_string_file(session_dir, account_name)
            )
            if not session_string:
                raise ValueError(f"账号 {account_name} 登录已失效，请重新登录")
        else:
            fallback_session_string = (
                get_account_session_string(account_name)
                or load_session_string_file(session_dir, account_name)
            )
            if not session_file.exists():
                if fallback_session_string:
                    session_string = fallback_session_string
                    used_fallback_session = True
                else:
                    raise ValueError(f"账号 {account_name} 登录已失效，请重新登录")

        config_service = get_config_service()
        tg_config = config_service.get_telegram_config()
        api_id = os.getenv("TG_API_ID") or tg_config.get("api_id")
        api_hash = os.getenv("TG_API_HASH") or tg_config.get("api_hash")

        try:
            api_id = int(api_id) if api_id is not None else None
        except (TypeError, ValueError):
            api_id = None

        if isinstance(api_hash, str):
            api_hash = api_hash.strip()

        if not api_id or not api_hash:
            raise ValueError("未配置 Telegram API ID 或 API Hash")

        # 使用 get_client 获取（可能共享的）客户端实例
        proxy_dict = None
        proxy_value = self._get_effective_proxy(account_name)
        if proxy_value:
            proxy_dict = build_proxy_dict(proxy_value)
        client_kwargs = {
            "name": account_name,
            "workdir": session_dir,
            "api_id": api_id,
            "api_hash": api_hash,
            "session_string": session_string,
            "in_memory": session_mode == "string",
            "proxy": proxy_dict,
            "no_updates": True,
        }
        client = get_client(**client_kwargs)

        chats: List[Dict[str, Any]] = []
        logger = logging.getLogger("backend")
        try:
            # 初始化账号锁（跨服务共享）
            if account_name not in self._account_locks:
                self._account_locks[account_name] = get_account_lock(account_name)

            account_lock = self._account_locks[account_name]

            async def _fetch_chats(active_client) -> List[Dict[str, Any]]:
                local_chats: List[Dict[str, Any]] = []
                # 使用上下文管理器处理生命周期和锁
                async with account_lock:
                    async with get_global_semaphore():
                        async with active_client:
                            # 尝试获取用户信息，如果失败说明 session 无效
                            await active_client.get_me()

                            try:
                                async for dialog in active_client.get_dialogs():
                                    try:
                                        chat = getattr(dialog, "chat", None)
                                        if chat is None:
                                            logger.warning(
                                                "get_dialogs 返回空 chat，已跳过"
                                            )
                                            continue
                                        chat_id = getattr(chat, "id", None)
                                        if chat_id is None:
                                            logger.warning(
                                                "get_dialogs 返回 chat.id 为空，已跳过"
                                            )
                                            continue

                                        chat_info = {
                                            "id": chat_id,
                                            "title": chat.title
                                            or chat.first_name
                                            or chat.username
                                            or str(chat_id),
                                            "username": chat.username,
                                            "type": chat.type.name.lower(),
                                        }

                                        # 特殊处理机器人和私聊
                                        if chat.type == ChatType.BOT:
                                            chat_info["title"] = f"🤖 {chat_info['title']}"

                                        local_chats.append(chat_info)
                                    except Exception as e:
                                        logger.warning(
                                            f"处理 dialog 失败，已跳过: {type(e).__name__}: {e}"
                                        )
                                        continue
                            except Exception as e:
                                # Pyrogram 边界异常：保留已获取结果
                                logger.warning(
                                    f"get_dialogs 中断，返回已获取结果: {type(e).__name__}: {e}"
                                )
                return local_chats

            try:
                chats = await _fetch_chats(client)
            except Exception as e:
                if self._is_invalid_session_error(e):
                    if fallback_session_string and not used_fallback_session:
                        logger.warning(
                            "Session invalid for %s, retry with session_string: %s",
                            account_name,
                            e,
                        )
                        try:
                            from tg_signer.core import close_client_by_name

                            await close_client_by_name(account_name, workdir=session_dir)
                        except Exception:
                            pass
                        used_fallback_session = True
                        retry_kwargs = dict(client_kwargs)
                        retry_kwargs["session_string"] = fallback_session_string
                        retry_kwargs["in_memory"] = True
                        retry_kwargs["no_updates"] = True
                        client = get_client(**retry_kwargs)
                        chats = await _fetch_chats(client)
                    else:
                        logger.warning(
                            "Session invalid for %s: %s",
                            account_name,
                            e,
                        )
                        await self._cleanup_invalid_session(account_name)
                        raise ValueError(f"账号 {account_name} 登录已失效，请重新登录")
                else:
                    raise

            # 保存到缓存
            account_dir = self.signs_dir / account_name
            account_dir.mkdir(parents=True, exist_ok=True)
            cache_file = account_dir / "chats_cache.json"

            try:
                with open(cache_file, "w", encoding="utf-8") as f:
                    json.dump(chats, f, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"DEBUG: 保存 Chat 缓存失败: {e}")

            return chats

        except Exception as e:
            # client 上下文管理器会自动处理 disconnect/stop，这里只需要处理业务异常
            raise e

    async def run_task(self, account_name: str, task_name: str) -> Dict[str, Any]:
        """
        运行签到任务 (兼容接口，内部调用 run_task_with_logs)
        """
        return await self.run_task_with_logs(account_name, task_name)

    def _task_key(self, account_name: str, task_name: str) -> tuple[str, str]:
        return account_name, task_name

    def _find_task_keys(self, task_name: str) -> List[tuple[str, str]]:
        return [key for key in self._active_logs.keys() if key[1] == task_name]

    def get_active_logs(
        self, task_name: str, account_name: Optional[str] = None
    ) -> List[str]:
        """获取正在运行任务的日志"""
        if account_name:
            return self._active_logs.get(self._task_key(account_name, task_name), [])
        # 兼容旧接口：返回第一个同名任务的日志
        for key in self._find_task_keys(task_name):
            return self._active_logs.get(key, [])
        return []

    def is_task_running(self, task_name: str, account_name: Optional[str] = None) -> bool:
        """检查任务是否正在运行"""
        if account_name:
            return self._active_tasks.get(self._task_key(account_name, task_name), False)
        return any(key[1] == task_name for key, running in self._active_tasks.items() if running)

    async def run_task_with_logs(
        self, account_name: str, task_name: str
    ) -> Dict[str, Any]:
        """运行任务并实时捕获日志 (In-Process)"""

        if self.is_task_running(task_name, account_name):
            return {"success": False, "error": "任务已经在运行中", "output": ""}

        # 初始化账号锁（跨服务共享）
        if account_name not in self._account_locks:
            self._account_locks[account_name] = get_account_lock(account_name)

        account_lock = self._account_locks[account_name]

        # 检查是否能获取锁 (非阻塞检查，如果已被锁定则说明该账号有其他任务在运行)
        # 这里我们希望排队等待，还是直接报错？
        # 考虑到定时任务同时触发，应该排队执行。
        print(f"DEBUG: 等待获取账号锁 {account_name}...")

        task_key = self._task_key(account_name, task_name)
        self._active_tasks[task_key] = True
        self._active_logs[task_key] = []

        # 获取 logger 实例
        tg_logger = logging.getLogger("tg-signer")
        log_handler = TaskLogHandler(self._active_logs[task_key])
        log_handler.setLevel(logging.INFO)
        log_handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))
        tg_logger.addHandler(log_handler)

        success = False
        error_msg = ""
        output_str = ""
        account_invalid_detected = False

        try:
            invalid_reason = await self._check_account_before_task(account_name, task_name)
            if invalid_reason:
                account_invalid_detected = True
                error_msg = f"账号 {account_name} 登录已失效，请重新登录: {invalid_reason}"
                self._active_logs[task_key].append(error_msg)
            else:
                async with account_lock:
                    last_end = self._account_last_run_end.get(account_name)
                    if last_end:
                        gap = time.time() - last_end
                        wait_seconds = self._account_cooldown_seconds - gap
                        if wait_seconds > 0:
                            self._active_logs[task_key].append(
                                f"等待账号冷却 {int(wait_seconds)} 秒"
                            )
                            await asyncio.sleep(wait_seconds)

                    print(f"DEBUG: 已获取账号锁 {account_name}，开始执行任务 {task_name}")
                    self._active_logs[task_key].append(
                        f"开始执行任务: {task_name} (账号: {account_name})"
                    )

                    # 配置 API 凭据
                    from backend.services.config import get_config_service

                    config_service = get_config_service()
                    tg_config = config_service.get_telegram_config()
                    api_id = os.getenv("TG_API_ID") or tg_config.get("api_id")
                    api_hash = os.getenv("TG_API_HASH") or tg_config.get("api_hash")

                    try:
                        api_id = int(api_id) if api_id is not None else None
                    except (TypeError, ValueError):
                        api_id = None

                    if isinstance(api_hash, str):
                        api_hash = api_hash.strip()

                    if not api_id or not api_hash:
                        raise ValueError("未配置 Telegram API ID 或 API Hash")

                    session_dir = settings.resolve_session_dir()
                    session_mode = get_session_mode()
                    session_string = None
                    use_in_memory = False
                    proxy_dict = None
                    proxy_value = self._get_effective_proxy(account_name)
                    if proxy_value:
                        proxy_dict = build_proxy_dict(proxy_value)

                    if session_mode == "string":
                        session_string = (
                            get_account_session_string(account_name)
                            or load_session_string_file(session_dir, account_name)
                        )
                        if not session_string:
                            account_invalid_detected = True
                            raise ValueError(f"账号 {account_name} 的 session_string 不存在")
                        use_in_memory = True
                    else:
                        session_string = None
                        use_in_memory = False

                        if os.getenv("SIGN_TASK_FORCE_IN_MEMORY") == "1":
                            session_string = load_session_string_file(
                                session_dir, account_name
                            )
                            use_in_memory = bool(session_string)

                    task_cfg = self.get_task(task_name, account_name=account_name)
                    requires_updates = self._task_requires_updates(task_cfg)
                    signer_no_updates = not requires_updates
                    self._active_logs[task_key].append(
                        f"消息更新监听: {'开启' if requires_updates else '关闭'}"
                    )

                    # 实例化 UserSigner (使用 BackendUserSigner)
                    # 注意: UserSigner 内部会使用 get_client 复用 client
                    signer = BackendUserSigner(
                        task_name=task_name,
                        session_dir=str(session_dir),
                        account=account_name,
                        workdir=self.workdir,
                        proxy=proxy_dict,
                        session_string=session_string,
                        in_memory=use_in_memory,
                        api_id=api_id,
                        api_hash=api_hash,
                        no_updates=signer_no_updates,
                    )

                    # 执行任务（数据库锁冲突时重试）
                    async with get_global_semaphore():
                        max_retries = 3
                        for attempt in range(max_retries):
                            try:
                                await signer.run_once(num_of_dialogs=20)
                                break
                            except Exception as e:
                                if "database is locked" in str(e).lower():
                                    if attempt < max_retries - 1:
                                        delay = (attempt + 1) * 3
                                        self._active_logs[task_key].append(
                                            f"Session 被锁定，{delay} 秒后重试..."
                                        )
                                        await asyncio.sleep(delay)
                                        continue
                                raise

                    success = True
                    self._active_logs[task_key].append("任务执行完成")

                    # 增加缓冲时间，防止同账号连续执行任务时，Session文件锁尚未完全释放导致 "database is locked"
                    await asyncio.sleep(2)

        except Exception as e:
            if account_invalid_detected or self._is_invalid_session_error(e):
                account_invalid_detected = True
                invalid_message = str(e) or f"账号 {account_name} 登录已失效，请重新登录"
                await self._mark_account_invalid(account_name, task_name, invalid_message)
            error_msg = f"任务执行出错: {str(e)}"
            self._active_logs[task_key].append(error_msg)
            # 打印堆栈以便调试
            traceback.print_exc()
            logger = logging.getLogger("backend")
            logger.error(error_msg)
        finally:
            self._account_last_run_end[account_name] = time.time()
            self._active_tasks[task_key] = False
            tg_logger.removeHandler(log_handler)

            # 保存执行记录
            final_logs = list(self._active_logs.get(task_key, []))
            output_str = "\n".join(final_logs)

            last_reply = ""
            if success:
                for line in reversed(final_logs):
                    if "收到来自「" in line and ("」的消息:" in line or "」对消息的更新，消息:" in line):
                        try:
                            splitter = "」的消息:" if "」的消息:" in line else "」对消息的更新，消息:"
                            reply_part = line.split(splitter, 1)[-1].strip()
                            if reply_part.startswith("Message:"):
                                reply_part = reply_part[len("Message:"):].strip()

                            if "text: " in reply_part:
                                text_content = reply_part.split("text: ", 1)[-1].split("\n")[0].strip()
                                if text_content:
                                    last_reply = text_content
                                elif "图片: " in reply_part:
                                    last_reply = "[图片] " + reply_part.split("图片: ", 1)[-1].split("\n")[0].strip()
                                else:
                                    last_reply = reply_part.replace("\n", " ").strip()
                            else:
                                last_reply = reply_part.replace("\n", " ").strip()

                            if len(last_reply) > 200:
                                last_reply = last_reply[:197] + "..."
                        except Exception:
                            pass
                        if last_reply:
                            break
                if last_reply:
                    reply_lower = last_reply.lower()
                    failure_keywords = (
                        "失败",
                        "错误",
                        "异常",
                        "未成功",
                        "无法",
                        "failed",
                        "failure",
                        "error",
                        "invalid",
                        "not found",
                    )
                    if any(keyword in reply_lower for keyword in failure_keywords):
                        success = False
                        error_msg = f"机器人回复疑似失败: {last_reply}"
                        final_logs.append(error_msg)
                        self._active_logs.setdefault(task_key, []).append(error_msg)
                        output_str = "\n".join(final_logs)

            msg = error_msg if not success else last_reply
            self._save_run_info(
                task_name,
                success,
                msg,
                account_name,
                flow_logs=final_logs,
            )

            if not success and not account_invalid_detected:
                await self._send_failure_notification(
                    account_name,
                    task_name,
                    error_msg or msg,
                    flow_logs=final_logs,
                )

            # 延迟清理日志（同一 task_key 仅保留一个 cleanup 协程）
            old_cleanup_task = self._cleanup_tasks.get(task_key)
            if old_cleanup_task and not old_cleanup_task.done():
                old_cleanup_task.cancel()

            async def cleanup():
                try:
                    await asyncio.sleep(60)
                    if not self._active_tasks.get(task_key):
                        self._active_logs.pop(task_key, None)
                finally:
                    self._cleanup_tasks.pop(task_key, None)

            self._cleanup_tasks[task_key] = asyncio.create_task(cleanup())

        return {
            "success": success,
            "output": output_str,
            "error": error_msg,
        }


# 创建全局实例
_sign_task_service: Optional[SignTaskService] = None


def get_sign_task_service() -> SignTaskService:
    global _sign_task_service
    if _sign_task_service is None:
        _sign_task_service = SignTaskService()
    return _sign_task_service
