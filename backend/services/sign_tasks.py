"""
签到任务服务层
提供签到任务的 CRUD 操作和执行功能
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
import traceback
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from backend.core.config import get_settings
from backend.utils.account_locks import get_account_lock
from backend.utils.memory import trim_memory
from backend.utils.names import validate_storage_name
from backend.utils.proxy import build_proxy_dict
from backend.utils.task_logs import extract_last_target_message, normalize_log_line
from backend.utils.tg_session import (
    get_account_proxy,
    get_account_session_string,
    get_account_status,
    get_global_semaphore,
    get_session_mode,
    list_account_names,
    load_session_string_file,
    set_account_status,
)
from backend.utils.time import utc_now_iso
from tg_signer.async_utils import create_logged_task
from tg_signer.core import UserSigner, get_client
from tg_signer.utils import atomic_write_json

settings = get_settings()

_service_logger = logging.getLogger("backend.sign_tasks")


def _safe_print(*args, sep: str = " ", end: str = "\n") -> None:
    text = sep.join(str(arg) for arg in args) + end
    _service_logger.debug(text.rstrip())


print = _safe_print


class TaskLogHandler(logging.Handler):
    """
    自定义日志处理器，将日志实时写入到内存列表中
    """

    def __init__(self, log_list: List[str]):
        super().__init__()
        self.log_list = log_list

    def emit(self, record):
        try:
            msg = normalize_log_line(self.format(record)) or record.getMessage()
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
        account_task_dir = self.tasks_dir / self._account / self.task_name
        if (account_task_dir / "config.json").exists():
            return account_task_dir
        legacy_task_dir = self.tasks_dir / self.task_name
        if (legacy_task_dir / "config.json").exists():
            return legacy_task_dir
        return account_task_dir

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

    _STRONG_FAILURE_PATTERNS = (
        re.compile(r"(签到|任务|执行|操作|请求|发送|点击)\s*(失败|异常|超时)"),
        re.compile(r"(未找到|找不到).*(按钮|消息|会话|聊天|目标)"),
        re.compile(r"(账号|会话|session).*(失效|无效|invalid)"),
        re.compile(r"\b(failed|failure|timed out|timeout|not found|invalid session|error)\b"),
    )

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
        _service_logger.info(
            "SignTaskService initialized, signs_dir=%s", self.signs_dir
        )
        self._active_logs: Dict[tuple[str, str], List[str]] = {}  # (account, task) -> logs
        self._active_tasks: Dict[tuple[str, str], bool] = {}  # (account, task) -> running
        self._cleanup_tasks: Dict[tuple[str, str], asyncio.Task] = {}
        self._run_statuses: Dict[tuple[str, str], Dict[str, Any]] = {}
        self._run_status_cleanup_tasks: Dict[tuple[str, str], asyncio.Task] = {}
        self._background_run_tasks: Dict[tuple[str, str], asyncio.Task] = {}
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
        self._max_account_last_run_entries = 100  # Bound account tracking
        self._cleanup_old_logs()

    def _prune_stale_entries(self) -> None:
        """Remove stale entries from internal tracking dicts to prevent memory growth."""
        # Prune _active_tasks entries that are False (task completed)
        stale_keys = [k for k, v in self._active_tasks.items() if not v]
        for key in stale_keys:
            self._active_tasks.pop(key, None)

        # Prune _active_logs for tasks that are no longer running and have no cleanup pending
        for key in list(self._active_logs.keys()):
            if not self._active_tasks.get(key, False) and key not in self._cleanup_tasks:
                self._active_logs.pop(key, None)

        # Prune completed background run tasks
        done_keys = [k for k, t in self._background_run_tasks.items() if t.done()]
        for key in done_keys:
            self._background_run_tasks.pop(key, None)

        # Prune completed cleanup tasks
        done_cleanup = [k for k, t in self._cleanup_tasks.items() if t.done()]
        for key in done_cleanup:
            self._cleanup_tasks.pop(key, None)

        done_status_cleanup = [k for k, t in self._run_status_cleanup_tasks.items() if t.done()]
        for key in done_status_cleanup:
            self._run_status_cleanup_tasks.pop(key, None)

        # Bound _account_last_run_end to prevent unbounded growth
        if len(self._account_last_run_end) > self._max_account_last_run_entries:
            # Keep only the most recent entries
            sorted_entries = sorted(
                self._account_last_run_end.items(), key=lambda x: x[1], reverse=True
            )
            self._account_last_run_end = dict(
                sorted_entries[: self._max_account_last_run_entries]
            )

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
        response_actions = {3, 4, 5, 6, 7, 8}
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

    @staticmethod
    def _task_has_keyword_monitor(task_config: Optional[Dict[str, Any]]) -> bool:
        if not isinstance(task_config, dict):
            return False
        for chat in task_config.get("chats") or []:
            if not isinstance(chat, dict):
                continue
            for action in chat.get("actions") or []:
                if not isinstance(action, dict):
                    continue
                try:
                    if int(action.get("action")) == 8:
                        return True
                except (TypeError, ValueError):
                    continue
        return False

    @staticmethod
    def _message_matches_thread(message: Any, chat_config: Dict[str, Any]) -> bool:
        if message is None:
            return False
        raw_thread_id = chat_config.get("message_thread_id")
        if raw_thread_id in (None, "", 0):
            return True
        try:
            thread_id = int(raw_thread_id)
        except (TypeError, ValueError):
            return True
        message_thread_id = getattr(message, "message_thread_id", None) or getattr(
            message,
            "reply_to_top_message_id",
            None,
        )
        return message_thread_id == thread_id

    @staticmethod
    def _format_target_message_summary(message: Any) -> str:
        if message is None:
            return ""

        text = str(getattr(message, "text", None) or getattr(message, "caption", None) or "").strip()
        if text:
            return text

        reply_markup = getattr(message, "reply_markup", None)
        button_rows: List[str] = []
        if reply_markup is not None:
            inline_keyboard = getattr(reply_markup, "inline_keyboard", None)
            reply_keyboard = getattr(reply_markup, "keyboard", None)
            rows = inline_keyboard or reply_keyboard or []
            for row in rows:
                row_texts: List[str] = []
                for button in row or []:
                    button_text = str(
                        getattr(button, "text", None) or button or ""
                    ).strip()
                    if button_text:
                        row_texts.append(button_text)
                if row_texts:
                    button_rows.append(" | ".join(row_texts))
            if button_rows:
                return " / ".join(button_rows)

        media_markers = (
            ("photo", "[图片]"),
            ("sticker", "[贴纸]"),
            ("animation", "[动图]"),
            ("video", "[视频]"),
            ("document", "[文件]"),
            ("audio", "[音频]"),
            ("voice", "[语音]"),
            ("video_note", "[视频消息]"),
        )
        for attr_name, label in media_markers:
            if getattr(message, attr_name, None) is not None:
                return label

        poll = getattr(message, "poll", None)
        if poll is not None:
            question = str(getattr(poll, "question", "") or "").strip()
            return f"[投票] {question}".strip()

        return ""

    @classmethod
    def _message_indicates_strong_failure(cls, text: str) -> bool:
        normalized = str(text or "").strip().lower()
        if not normalized:
            return False

        success_markers = (
            "签到成功",
            "已签到",
            "任务完成",
            "执行完成",
            "操作完成",
            "success",
            "successful",
            "done",
            "completed",
        )
        if any(marker in normalized for marker in success_markers):
            return False

        return any(pattern.search(normalized) for pattern in cls._STRONG_FAILURE_PATTERNS)

    async def _fetch_last_target_message_from_chat_history(
        self,
        signer: BackendUserSigner,
        task_config: Optional[Dict[str, Any]],
    ) -> str:
        if signer is None or not isinstance(task_config, dict):
            return ""

        chats = task_config.get("chats")
        if not isinstance(chats, list) or not chats:
            return ""

        history_limit = self._read_positive_int_env(
            "SIGN_TASK_LAST_TARGET_HISTORY_LIMIT",
            8,
            1,
        )
        best_text = ""
        best_timestamp = None
        fallback_text = ""
        fallback_timestamp = None

        # Skip if client was already terminated/disconnected after task finished
        try:
            app = signer.app
            if app is None:
                return ""
            # Check if client is still usable (not terminated)
            if not getattr(app, "is_connected", False) and not getattr(app, "is_initialized", False):
                # Client already torn down - don't try to re-enter
                return ""
        except Exception:
            return ""

        try:
            async with signer.app:
                for chat in chats:
                    if not isinstance(chat, dict):
                        continue
                    chat_id = chat.get("chat_id")
                    if chat_id in (None, ""):
                        continue

                    try:
                        async for message in signer.app.get_chat_history(
                            chat_id,
                            limit=history_limit,
                        ):
                            if not self._message_matches_thread(message, chat):
                                continue

                            candidate = self._format_target_message_summary(message)
                            if not candidate:
                                continue

                        message_time = getattr(message, "date", None)
                        from_user = getattr(message, "from_user", None)
                        is_self = bool(getattr(from_user, "is_self", False))

                        if not is_self:
                            if best_timestamp is None or (
                                message_time is not None and message_time > best_timestamp
                            ):
                                best_text = candidate
                                best_timestamp = message_time
                            break

                        if fallback_timestamp is None or (
                            message_time is not None and message_time > fallback_timestamp
                        ):
                            fallback_text = candidate
                            fallback_timestamp = message_time
                    except Exception:
                        continue
        except Exception:
            # Silently ignore errors like "Client is already terminated"
            pass

        return best_text or fallback_text

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
    def _move_storage_path(source: Path, target: Path) -> None:
        if not source.exists():
            return

        source_resolved = str(source.resolve()).lower()
        target_resolved = str(target.resolve()).lower()
        if source_resolved == target_resolved:
            if str(source) == str(target):
                return
            temp_target = source.with_name(f"{source.name}.__rename_tmp__{uuid.uuid4().hex}")
            source.replace(temp_target)
            temp_target.replace(target)
            return

        if target.exists():
            raise ValueError(f"目标路径已存在: {target}")

        target.parent.mkdir(parents=True, exist_ok=True)
        source.replace(target)

    def _known_account_names(self) -> List[str]:
        names = set()
        try:
            names.update(name for name in list_account_names() if name)
        except Exception:
            pass

        try:
            session_dir = settings.resolve_session_dir()
            for pattern in ("*.session", "*.session_string"):
                for path in session_dir.glob(pattern):
                    if path.stem:
                        names.add(path.stem)
        except Exception:
            pass

        return sorted(names)

    def _infer_account_name(
        self, config: Dict[str, Any], task_dir: Optional[Path] = None
    ) -> str:
        account_name = config.get("account_name")
        if isinstance(account_name, str) and account_name.strip():
            return account_name.strip()

        if task_dir is not None and task_dir.parent != self.signs_dir:
            return task_dir.parent.name

        known_accounts = self._known_account_names()
        if "my_account" in known_accounts:
            return "my_account"
        if len(known_accounts) == 1:
            return known_accounts[0]
        return ""

    def _resolve_task_dir(
        self, task_name: str, account_name: Optional[str] = None
    ) -> Optional[Path]:
        task_name = validate_storage_name(task_name, field_name="task_name")
        if account_name:
            account_name = validate_storage_name(account_name, field_name="account_name")
            account_task_dir = self.signs_dir / account_name / task_name
            if (account_task_dir / "config.json").exists():
                return account_task_dir

            legacy_task_dir = self.signs_dir / task_name
            config_file = legacy_task_dir / "config.json"
            if not config_file.exists():
                return None
            try:
                with open(config_file, "r", encoding="utf-8") as f:
                    config = json.load(f)
            except Exception:
                return None
            if self._infer_account_name(config, legacy_task_dir) == account_name:
                return legacy_task_dir
            return None

        legacy_task_dir = self.signs_dir / task_name
        if (legacy_task_dir / "config.json").exists():
            return legacy_task_dir

        try:
            for acc_dir in self.signs_dir.iterdir():
                nested_task_dir = acc_dir / task_name
                if acc_dir.is_dir() and (nested_task_dir / "config.json").exists():
                    return nested_task_dir
        except Exception:
            return None
        return None

    @staticmethod
    def _normalize_account_names(
        account_names: Optional[Iterable[str]] = None,
        account_name: Optional[str] = None,
    ) -> List[str]:
        ordered: List[str] = []

        def _append(value: Optional[str]) -> None:
            if not isinstance(value, str):
                return
            # Preserve wildcard marker
            if value.strip() == "*":
                if "*" not in ordered:
                    ordered.append("*")
                return
            cleaned = validate_storage_name(value, field_name="account_name")
            if cleaned and cleaned not in ordered:
                ordered.append(cleaned)

        if account_names:
            for item in account_names:
                _append(item)
        _append(account_name)
        return ordered

    def _expand_account_names(self, account_names: List[str]) -> List[str]:
        """Expand wildcard '*' to all currently registered accounts."""
        if "*" in account_names:
            all_accounts = list_account_names()
            return all_accounts if all_accounts else account_names
        return account_names

    def _expand_wildcard_tasks(self) -> None:
        """
        For tasks with account_names: ["*"], create task directories
        for any accounts that don't have them yet.
        """
        if not self.signs_dir.exists():
            return
        all_accounts = list_account_names()
        if not all_accounts:
            return

        # Scan all existing task configs looking for wildcard
        seen_wildcard_tasks: List[tuple] = []  # (task_name, config, source_dir)
        for account_dir in self.signs_dir.iterdir():
            if not account_dir.is_dir():
                continue
            for task_dir in account_dir.iterdir():
                if not task_dir.is_dir():
                    continue
                config_file = task_dir / "config.json"
                if not config_file.exists():
                    continue
                try:
                    with open(config_file, "r", encoding="utf-8") as f:
                        config = json.load(f)
                    stored_names = config.get("account_names", [])
                    if isinstance(stored_names, list) and "*" in stored_names:
                        seen_wildcard_tasks.append((task_dir.name, config, task_dir))
                except Exception:
                    continue

        # For each wildcard task, ensure all accounts have a directory
        for task_name, base_config, _ in seen_wildcard_tasks:
            for acc in all_accounts:
                target_dir = self.signs_dir / acc / task_name
                if target_dir.exists():
                    continue
                # Create task for this account
                target_dir.mkdir(parents=True, exist_ok=True)
                new_config = dict(base_config)
                new_config["account_name"] = acc
                try:
                    with open(target_dir / "config.json", "w", encoding="utf-8") as f:
                        json.dump(new_config, f, ensure_ascii=False, indent=2)
                except Exception:
                    pass

        self._tasks_cache = None

    def _resolve_account_names_from_config(
        self,
        config: Dict[str, Any],
        task_dir: Optional[Path] = None,
        resolved_account_name: Optional[str] = None,
    ) -> List[str]:
        names = self._normalize_account_names(config.get("account_names"))
        if names:
            return names
        fallback = resolved_account_name or self._infer_account_name(config, task_dir)
        return self._normalize_account_names(account_name=fallback)

    @staticmethod
    def _select_latest_last_run(
        current: Optional[Dict[str, Any]], candidate: Optional[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        if not candidate:
            return current
        if not current:
            return candidate
        current_time = str(current.get("time") or "")
        candidate_time = str(candidate.get("time") or "")
        return candidate if candidate_time > current_time else current

    @staticmethod
    def _task_group_key(task: Dict[str, Any]) -> str:
        group_id = str(task.get("task_group_id") or "").strip()
        if group_id:
            return f"group:{group_id}"
        account_name = str(task.get("account_name") or "").strip()
        task_name = str(task.get("name") or "").strip()
        return f"single:{account_name}:{task_name}"

    def _build_task_response(
        self,
        *,
        task_name: str,
        primary_account_name: str,
        account_names: List[str],
        sign_at: str,
        chats: List[Dict[str, Any]],
        random_seconds: int,
        sign_interval: int,
        enabled: bool = True,
        last_run: Optional[Dict[str, Any]] = None,
        execution_mode: str = "fixed",
        range_start: str = "",
        range_end: str = "",
        notify_on_failure: bool = True,
        task_group_id: str = "",
        last_run_account_name: str = "",
    ) -> Dict[str, Any]:
        normalized_accounts = self._normalize_account_names(
            account_names, primary_account_name
        )
        return {
            "name": task_name,
            # Keep the owning account on raw task records. Aggregated task views
            # intentionally collapse to the first linked account elsewhere.
            "account_name": primary_account_name,
            "account_names": normalized_accounts,
            "sign_at": sign_at,
            "random_seconds": random_seconds,
            "sign_interval": sign_interval,
            "chats": chats,
            "enabled": enabled,
            "last_run": last_run,
            "execution_mode": execution_mode,
            "range_start": range_start,
            "range_end": range_end,
            "notify_on_failure": notify_on_failure,
            "task_group_id": task_group_id,
            "last_run_account_name": last_run_account_name,
        }

    def _aggregate_tasks(self, tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        grouped: Dict[str, Dict[str, Any]] = {}

        def _first_real_account(names: List[str], fallback: str = "") -> str:
            for n in names:
                if n and n != "*":
                    return n
            return fallback if fallback and fallback != "*" else ""

        for task in tasks:
            key = self._task_group_key(task)
            existing = grouped.get(key)
            if existing is None:
                merged = {
                    **task,
                    "account_names": self._normalize_account_names(
                        task.get("account_names"), task.get("account_name")
                    ),
                }
                # Ensure account_name is a real one, not "*"
                if not merged.get("account_name") or merged.get("account_name") == "*":
                    merged["account_name"] = _first_real_account(
                        merged["account_names"], task.get("account_name") or ""
                    )
                grouped[key] = merged
                continue

            merged_accounts = self._normalize_account_names(
                [*existing.get("account_names", []), *task.get("account_names", [])],
                existing.get("account_name") or task.get("account_name"),
            )
            latest_last_run = self._select_latest_last_run(
                existing.get("last_run"), task.get("last_run")
            )
            latest_last_run_account_name = existing.get("last_run_account_name") or ""
            if latest_last_run is task.get("last_run"):
                latest_last_run_account_name = task.get("account_name") or ""

            existing["account_names"] = merged_accounts
            # Pick first real account name, not "*"
            existing["account_name"] = _first_real_account(
                merged_accounts,
                existing.get("account_name") or task.get("account_name") or "",
            )
            existing["last_run"] = latest_last_run
            existing["last_run_account_name"] = latest_last_run_account_name

        return sorted(
            grouped.values(),
            key=lambda item: (
                ",".join(item.get("account_names", [])),
                str(item.get("name") or ""),
            ),
        )

    def _find_related_task_infos(
        self, task_name: str, account_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        raw_tasks = self.list_tasks(force_refresh=True, aggregate=False)
        if account_name:
            current = next(
                (
                    task
                    for task in raw_tasks
                    if task.get("name") == task_name
                    and task.get("account_name") == account_name
                ),
                None,
            )
            if current is None:
                return []

            group_id = str(current.get("task_group_id") or "").strip()
            if group_id:
                return [
                    task
                    for task in raw_tasks
                    if task.get("name") == task_name
                    and str(task.get("task_group_id") or "").strip() == group_id
                ]

            current_accounts = self._normalize_account_names(
                current.get("account_names"), current.get("account_name")
            )
            if len(current_accounts) > 1:
                return [
                    task
                    for task in raw_tasks
                    if task.get("name") == task_name
                    and self._normalize_account_names(
                        task.get("account_names"), task.get("account_name")
                    )
                    == current_accounts
                ]
            return [current]

        exact_matches = [task for task in raw_tasks if task.get("name") == task_name]
        if not exact_matches:
            return []
        if len(exact_matches) == 1:
            return exact_matches

        grouped = self._aggregate_tasks(exact_matches)
        if len(grouped) == 1:
            target_key = self._task_group_key(grouped[0])
            return [
                task for task in exact_matches if self._task_group_key(task) == target_key
            ]
        return [exact_matches[0]]

    def _iter_task_dirs(
        self, task_name: str, account_names: Iterable[str]
    ) -> List[tuple[str, Path]]:
        dirs: List[tuple[str, Path]] = []
        for name in self._normalize_account_names(account_names):
            task_dir = self._resolve_task_dir(task_name, name)
            if task_dir is not None:
                dirs.append((name, task_dir))
        return dirs

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

    def _resolve_existing_history_file(
        self, task_name: str, account_name: str = ""
    ) -> Optional[Path]:
        history_file = self._history_file_path(task_name, account_name)
        legacy_file = self.run_history_dir / f"{self._safe_history_key(task_name)}.json"

        if history_file.exists():
            return history_file
        if legacy_file.exists():
            return legacy_file
        return None

    @staticmethod
    def _load_history_payload_from_file(history_file: Path) -> List[Any]:
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return []

        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
        return []

    def _set_task_last_run_metadata(
        self,
        task_name: str,
        account_name: str = "",
        last_run: Optional[Dict[str, Any]] = None,
    ) -> None:
        try:
            task_dir = self._resolve_task_dir(task_name, account_name or None)
        except Exception:
            task_dir = None

        if task_dir is not None:
            config_file = task_dir / "config.json"
            if config_file.exists():
                try:
                    with open(config_file, "r", encoding="utf-8") as f:
                        config = json.load(f)
                    if last_run:
                        config["last_run"] = last_run
                    else:
                        config.pop("last_run", None)
                    with open(config_file, "w", encoding="utf-8") as f:
                        json.dump(config, f, ensure_ascii=False, indent=2)
                except Exception:
                    pass

        if self._tasks_cache is not None:
            for task in self._tasks_cache:
                if not isinstance(task, dict):
                    continue
                if task.get("name") != task_name or task.get("account_name") != account_name:
                    continue
                if last_run:
                    task["last_run"] = last_run
                else:
                    task.pop("last_run", None)
                break

    def _legacy_get_task_history_logs(
        self, task_name: str, account_name: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        if limit < 1:
            limit = 1
        if limit > 200:
            limit = 200

        history = self._load_history_entries(task_name, account_name=account_name)
        result: List[Dict[str, Any]] = []
        try:
            from backend.services.keyword_monitor import get_keyword_monitor_service

            monitor_entry = get_keyword_monitor_service().get_task_history_entry(
                task_name,
                account_name,
            )
            if monitor_entry:
                result.append(monitor_entry)
        except Exception:
            pass
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
        account_name = validate_storage_name(account_name, field_name="account_name")
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
                            data["last_target_message"] = (
                                str(data.get("last_target_message") or "").strip()
                                or extract_last_target_message(data.get("flow_logs"))
                            )
                            all_history.append(data)
            except Exception:
                continue

        # 按时间倒序
        all_history.sort(key=lambda x: x.get("time", ""), reverse=True)
        return all_history

    def get_recent_history_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        if limit < 1:
            limit = 1
        if limit > 200:
            limit = 200

        recent: List[Dict[str, Any]] = []
        seen_pairs: set[tuple[str, str]] = set()

        for task in self.list_tasks(force_refresh=False, aggregate=False):
            task_name = str(task.get("name") or "").strip()
            account_name = str(task.get("account_name") or "").strip()
            if not task_name or not account_name:
                continue

            pair = (account_name, task_name)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)

            history = self._load_history_entries(task_name, account_name=account_name)
            for item in history[:limit]:
                flow_logs = item.get("flow_logs")
                if not isinstance(flow_logs, list):
                    flow_logs = []
                recent.append(
                    {
                        "time": item.get("time", ""),
                        "success": bool(item.get("success", False)),
                        "message": self._repair_mojibake(item.get("message", "") or ""),
                        "flow_logs": [self._repair_mojibake(str(line)) for line in flow_logs],
                        "flow_truncated": bool(item.get("flow_truncated", False)),
                        "flow_line_count": int(item.get("flow_line_count", len(flow_logs))),
                        "task_name": task_name,
                        "account_name": account_name,
                        "last_target_message": str(
                            item.get("last_target_message") or ""
                        ).strip()
                        or extract_last_target_message(flow_logs),
                    }
                )

        recent.sort(key=lambda item: str(item.get("time") or ""), reverse=True)
        return recent[:limit]

    def get_filtered_history_logs(
        self,
        account_name: Optional[str] = None,
        date: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        if limit < 1:
            limit = 1
        if limit > 1000:
            limit = 1000

        normalized_account = (
            validate_storage_name(account_name, field_name="account_name")
            if account_name
            else None
        )
        normalized_date = str(date or "").strip()[:10]
        history_items: List[Dict[str, Any]] = []
        seen_pairs: set[tuple[str, str]] = set()

        for task in self.list_tasks(
            account_name=normalized_account,
            force_refresh=False,
            aggregate=False,
        ):
            task_name = str(task.get("name") or "").strip()
            current_account = str(task.get("account_name") or "").strip()
            if not task_name or not current_account:
                continue

            pair = (current_account, task_name)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)

            history = self._load_history_entries(task_name, account_name=current_account)
            for item in history:
                timestamp = str(item.get("time") or "")
                if normalized_date and not timestamp.startswith(normalized_date):
                    continue

                flow_logs = item.get("flow_logs")
                if not isinstance(flow_logs, list):
                    flow_logs = []

                history_items.append(
                    {
                        "time": timestamp,
                        "success": bool(item.get("success", False)),
                        "message": self._repair_mojibake(item.get("message", "") or ""),
                        "flow_logs": [self._repair_mojibake(str(line)) for line in flow_logs],
                        "flow_truncated": bool(item.get("flow_truncated", False)),
                        "flow_line_count": int(item.get("flow_line_count", len(flow_logs))),
                        "task_name": task_name,
                        "account_name": current_account,
                        "last_target_message": str(
                            item.get("last_target_message") or ""
                        ).strip()
                        or extract_last_target_message(flow_logs),
                    }
                )

        history_items.sort(key=lambda item: str(item.get("time") or ""), reverse=True)
        return history_items[:limit]

    def get_history_log_detail(
        self,
        account_name: str,
        task_name: str,
        created_at: str,
    ) -> Optional[Dict[str, Any]]:
        normalized_account = validate_storage_name(
            account_name, field_name="account_name"
        )
        normalized_task = validate_storage_name(task_name, field_name="task_name")
        target_time = str(created_at or "").strip()
        if not target_time:
            return None

        for item in self._load_history_entries(
            normalized_task, account_name=normalized_account
        ):
            timestamp = str(item.get("time") or "")
            if timestamp != target_time:
                continue

            flow_logs = item.get("flow_logs")
            if not isinstance(flow_logs, list):
                flow_logs = []

            return {
                "time": timestamp,
                "success": bool(item.get("success", False)),
                "message": self._repair_mojibake(item.get("message", "") or ""),
                "flow_logs": [self._repair_mojibake(str(line)) for line in flow_logs],
                "flow_truncated": bool(item.get("flow_truncated", False)),
                "flow_line_count": int(item.get("flow_line_count", len(flow_logs))),
                "task_name": normalized_task,
                "account_name": normalized_account,
                "last_target_message": str(item.get("last_target_message") or "").strip()
                or extract_last_target_message(flow_logs),
            }

        return None

    def delete_history_log(
        self,
        account_name: str,
        task_name: str,
        created_at: str,
    ) -> bool:
        normalized_account = validate_storage_name(
            account_name, field_name="account_name"
        )
        normalized_task = validate_storage_name(task_name, field_name="task_name")
        target_time = str(created_at or "").strip()
        if not target_time:
            return False

        history_file = self._resolve_existing_history_file(
            normalized_task, normalized_account
        )
        if history_file is None:
            return False

        raw_entries = self._load_history_payload_from_file(history_file)
        kept_entries: List[Any] = []
        deleted = False

        for entry in raw_entries:
            if not isinstance(entry, dict):
                kept_entries.append(entry)
                continue

            entry_time = str(entry.get("time") or "")
            entry_account = str(entry.get("account_name") or "")
            account_matches = not entry_account or entry_account == normalized_account

            if not deleted and entry_time == target_time and account_matches:
                deleted = True
                continue

            kept_entries.append(entry)

        if not deleted:
            return False

        if kept_entries:
            with open(history_file, "w", encoding="utf-8") as f:
                json.dump(kept_entries, f, ensure_ascii=False, indent=2)
        else:
            try:
                history_file.unlink()
            except FileNotFoundError:
                pass

        remaining_entries = [
            entry
            for entry in kept_entries
            if isinstance(entry, dict)
            and str(entry.get("account_name") or normalized_account) == normalized_account
        ]
        remaining_entries.sort(key=lambda item: str(item.get("time") or ""), reverse=True)
        latest_entry = remaining_entries[0] if remaining_entries else None
        self._set_task_last_run_metadata(
            normalized_task,
            normalized_account,
            latest_entry if isinstance(latest_entry, dict) else None,
        )
        return True

    @staticmethod
    def _count_history_entries(data: Any) -> int:
        if isinstance(data, list):
            return len(data)
        if isinstance(data, dict):
            return 1
        return 0

    def _clear_task_last_run_metadata(
        self, task_name: str, account_name: str = ""
    ) -> None:
        try:
            task_dir = self._resolve_task_dir(task_name, account_name or None)
        except Exception:
            task_dir = None

        if task_dir is None:
            return

        config_file = task_dir / "config.json"
        if not config_file.exists():
            return

        try:
            with open(config_file, "r", encoding="utf-8") as f:
                config = json.load(f)
            if "last_run" not in config:
                return
            del config["last_run"]
            with open(config_file, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def clear_all_history_logs(self) -> Dict[str, int]:
        removed_files = 0
        removed_entries = 0

        if not self.run_history_dir.exists():
            return {"removed_files": 0, "removed_entries": 0}

        seen_tasks: set[tuple[str, str]] = set()
        for task in self.list_tasks(force_refresh=True, aggregate=False):
            task_name = str(task.get("name") or "").strip()
            account_name = str(task.get("account_name") or "").strip()
            if not task_name:
                continue
            key = (account_name, task_name)
            if key in seen_tasks:
                continue
            seen_tasks.add(key)
            self._clear_task_last_run_metadata(task_name, account_name)

        if self._tasks_cache is not None:
            for task in self._tasks_cache:
                if isinstance(task, dict):
                    task.pop("last_run", None)

        for history_file in self.run_history_dir.glob("*.json"):
            try:
                with open(history_file, "r", encoding="utf-8") as f:
                    removed_entries += self._count_history_entries(json.load(f))
            except Exception:
                pass
            try:
                history_file.unlink()
                removed_files += 1
            except Exception:
                pass

        return {"removed_files": removed_files, "removed_entries": removed_entries}

    def clear_account_history_logs(self, account_name: str) -> Dict[str, int]:
        """清理某账号的历史日志，不影响其他账号"""
        account_name = validate_storage_name(account_name, field_name="account_name")
        removed_files = 0
        removed_entries = 0

        if not self.run_history_dir.exists():
            return {"removed_files": 0, "removed_entries": 0}

        tasks = self.list_tasks(account_name=account_name)
        for task in tasks:
            task_name = task.get("name") or ""
            if not task_name:
                continue

            self._clear_task_last_run_metadata(task_name, account_name)
            if self._tasks_cache is not None:
                for t in self._tasks_cache:
                    if t["name"] == task_name and t.get("account_name") == account_name:
                        t.pop("last_run", None)
                        break

            history_file = self._history_file_path(task_name, account_name)
            if history_file.exists():
                try:
                    with open(history_file, "r", encoding="utf-8") as f:
                        removed_entries += self._count_history_entries(json.load(f))
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

            # legacy 文件可能没有 account_name，是旧版单账号场景
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
        last_target_message = extract_last_target_message(normalized_logs)

        new_entry = {
            "time": datetime.now().isoformat(),
            "success": success,
            "message": self._repair_mojibake(message),
            "account_name": account_name,
            "flow_logs": normalized_logs,
            "flow_truncated": flow_truncated,
            "flow_line_count": flow_line_count,
            "last_target_message": last_target_message,
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
                        _service_logger.debug(f"更新任务配置 last_run 失败: {e}")

            # 2. 更新内存缓存 (关键优化：避免置空 self._tasks_cache)
            if self._tasks_cache is not None:
                for t in self._tasks_cache:
                    if t["name"] == task_name and t.get("account_name") == account_name:
                        t["last_run"] = new_entry
                        break

        except Exception as e:
            _service_logger.debug(f"保存运行信息失败: {str(e)}")

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
        last_target_message: Optional[str] = None,
        flow_logs: Optional[List[str]] = None,
    ) -> None:
        try:
            from backend.services.config import get_config_service

            cfg = get_config_service().get_global_settings()
            if not cfg.get("telegram_bot_notify_enabled"):
                return
            if not cfg.get("telegram_bot_task_failure_enabled", True):
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
            if last_target_message:
                text += f"\nLast target message: {last_target_message}"
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
        notify_on_failure: bool = True,
    ) -> bool:
        current = get_account_status(account_name)
        already_notified = bool(current.get("invalid_notified_at"))
        notified_at = current.get("invalid_notified_at") or utc_now_iso()
        set_account_status(
            account_name,
            status="invalid",
            message=message,
            code="ACCOUNT_SESSION_INVALID",
            needs_relogin=True,
            invalid_notified_at=notified_at,
        )
        if not already_notified and notify_on_failure:
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
        no_updates: bool,
        notify_on_failure: bool = True,
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
            await self._mark_account_invalid(
                account_name, task_name, message, notify_on_failure=notify_on_failure
            )
            return message

        try:
            from backend.services.telegram import get_telegram_service

            result = await get_telegram_service().check_account_status(
                account_name,
                timeout_seconds=10.0,
                no_updates=no_updates,
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
            await self._mark_account_invalid(
                account_name, task_name, message, notify_on_failure=notify_on_failure
            )
            return message

        return None

    def _legacy_list_tasks(
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

        _service_logger.debug(f"扫描任务目录: {base_dir}")
        try:
            # 扫描所有子目录 (账号名)
            for account_path in base_dir.iterdir():
                if not account_path.is_dir():
                    continue

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
            _service_logger.debug(f"扫描任务出错: {str(e)}")
            return []

    def _load_task_config(self, task_dir: Path) -> Optional[Dict[str, Any]]:
        """加载单个任务配置，优先使用 config.json 中的 last_run"""
        config_file = task_dir / "config.json"
        if not config_file.exists():
            return None

        try:
            with open(config_file, "r", encoding="utf-8") as f:
                config = json.load(f)

            resolved_account_name = self._infer_account_name(config, task_dir)

            # 优先从 config 读取 last_run
            last_run = config.get("last_run")
            if not last_run:
                last_run = self._get_last_run_info(
                    task_dir, account_name=resolved_account_name
                )

            return {
                "name": task_dir.name,
                "account_name": resolved_account_name,
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

    def _legacy_get_task(
        self, task_name: str, account_name: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        获取单个任务的详细信息
        """
        task_dir = self._resolve_task_dir(task_name, account_name)
        if task_dir is None:
            return None
        config_file = task_dir / "config.json"

        try:
            with open(config_file, "r", encoding="utf-8") as f:
                config = json.load(f)
            resolved_account_name = self._infer_account_name(config, task_dir)
            last_run = config.get("last_run")
            if not last_run:
                last_run = self._get_last_run_info(
                    task_dir, account_name=resolved_account_name
                )

            return {
                "name": task_name,
                "account_name": resolved_account_name,
                "sign_at": config.get("sign_at", ""),
                "random_seconds": config.get("random_seconds", 0),
                "sign_interval": config.get("sign_interval", 1),
                "chats": config.get("chats", []),
                "enabled": True,
                "last_run": last_run,
                "execution_mode": config.get("execution_mode", "fixed"),
                "range_start": config.get("range_start", ""),
                "range_end": config.get("range_end", ""),
                "notify_on_failure": config.get("notify_on_failure", True),
            }
        except Exception:
            return None

    def _legacy_create_task_v1(
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
        notify_on_failure: bool = True,
    ) -> Dict[str, Any]:
        """
        创建新的签到任务
        """
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
            sign_interval = 1

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
            "notify_on_failure": notify_on_failure,
        }

        config_file = task_dir / "config.json"

        try:
            with open(config_file, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            _service_logger.debug(f"写入配置文件失败: {str(e)}")
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
            _service_logger.debug(f"更新调度任务失败: {e}")

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
            "notify_on_failure": notify_on_failure,
        }

    def _legacy_update_task_v1(
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
        notify_on_failure: Optional[bool] = None,
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
            "notify_on_failure": notify_on_failure
            if notify_on_failure is not None
            else existing.get("notify_on_failure", True),
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
            "notify_on_failure": config.get("notify_on_failure", True),
        }

    def _legacy_delete_task_v1(
        self, task_name: str, account_name: Optional[str] = None
    ) -> bool:
        """
        删除签到任务
        """
        task_dir = self._resolve_task_dir(task_name, account_name)

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
                    _service_logger.debug(f"移除调度任务失败: {e}")

            return True
        except Exception:
            return False

    def get_task_history_logs(
        self, task_name: str, account_name: Optional[str] = None, limit: int = 20
    ) -> List[Dict[str, Any]]:
        if limit < 1:
            limit = 1
        if limit > 200:
            limit = 200

        if account_name:
            history = self._load_history_entries(task_name, account_name=account_name)
            result: List[Dict[str, Any]] = []
            try:
                from backend.services.keyword_monitor import get_keyword_monitor_service

                monitor_entry = get_keyword_monitor_service().get_task_history_entry(
                    task_name,
                    account_name,
                )
                if monitor_entry:
                    result.append(monitor_entry)
            except Exception:
                pass

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
                        "account_name": item.get("account_name") or account_name,
                        "last_target_message": str(
                            item.get("last_target_message") or ""
                        ).strip()
                        or extract_last_target_message(flow_logs),
                    }
                )
            return result

        merged: List[Dict[str, Any]] = []
        task = self.get_task(task_name, aggregate=True)
        if not task:
            return []

        for current_account in self._normalize_account_names(
            task.get("account_names"), task.get("account_name")
        ):
            merged.extend(
                self.get_task_history_logs(
                    task_name=task_name,
                    account_name=current_account,
                    limit=limit,
                )
            )

        merged.sort(key=lambda item: str(item.get("time") or ""), reverse=True)
        return merged[:limit]

    def list_tasks(
        self,
        account_name: Optional[str] = None,
        force_refresh: bool = False,
        aggregate: bool = False,
    ) -> List[Dict[str, Any]]:
        """Return sign tasks, optionally grouped by shared task set."""
        tasks: List[Dict[str, Any]]
        if self._tasks_cache is not None and not force_refresh:
            tasks = self._tasks_cache
        else:
            tasks = []
            base_dir = self.signs_dir

            _service_logger.debug(f"扫描任务目录: {base_dir}")
            try:
                for account_path in base_dir.iterdir():
                    if not account_path.is_dir():
                        continue

                    if (account_path / "config.json").exists():
                        task_info = self._load_task_config(account_path)
                        if task_info:
                            tasks.append(task_info)
                        continue

                    for task_dir in account_path.iterdir():
                        if not task_dir.is_dir():
                            continue

                        task_info = self._load_task_config(task_dir)
                        if task_info:
                            tasks.append(task_info)

                self._tasks_cache = sorted(
                    tasks, key=lambda item: (item["account_name"], item["name"])
                )
                tasks = self._tasks_cache
            except Exception as e:
                _service_logger.debug(f"扫描任务出错: {str(e)}")
                return []

        if account_name:
            tasks = [
                task for task in tasks if str(task.get("account_name") or "") == account_name
            ]

        if aggregate:
            return self._aggregate_tasks(tasks)
        return tasks

    def _load_task_config(self, task_dir: Path) -> Optional[Dict[str, Any]]:
        """Load one task config and normalize multi-account metadata."""
        config_file = task_dir / "config.json"
        if not config_file.exists():
            return None

        try:
            with open(config_file, "r", encoding="utf-8") as f:
                config = json.load(f)

            resolved_account_name = self._infer_account_name(config, task_dir)
            resolved_account_names = self._resolve_account_names_from_config(
                config,
                task_dir=task_dir,
                resolved_account_name=resolved_account_name,
            )

            last_run = config.get("last_run")
            if not last_run:
                last_run = self._get_last_run_info(
                    task_dir, account_name=resolved_account_name
                )

            return self._build_task_response(
                task_name=task_dir.name,
                primary_account_name=resolved_account_name,
                account_names=resolved_account_names,
                sign_at=config.get("sign_at", ""),
                chats=config.get("chats", []),
                random_seconds=config.get("random_seconds", 0),
                sign_interval=config.get("sign_interval", 1),
                enabled=True,
                last_run=last_run,
                execution_mode=config.get("execution_mode", "fixed"),
                range_start=config.get("range_start", ""),
                range_end=config.get("range_end", ""),
                notify_on_failure=config.get("notify_on_failure", True),
                task_group_id=str(config.get("task_group_id") or ""),
                last_run_account_name=str(
                    (last_run or {}).get("account_name") or resolved_account_name
                ),
            )
        except Exception:
            return None

    def get_task(
        self,
        task_name: str,
        account_name: Optional[str] = None,
        aggregate: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Get one task, optionally as an aggregated shared-task view."""
        if aggregate and not account_name:
            related = self._find_related_task_infos(task_name)
            if not related:
                return None
            grouped = self._aggregate_tasks(related)
            return grouped[0] if grouped else None

        task_dir = self._resolve_task_dir(task_name, account_name)
        if task_dir is None:
            return None
        return self._load_task_config(task_dir)

    def create_task(
        self,
        task_name: str,
        sign_at: str,
        chats: List[Dict[str, Any]],
        random_seconds: int = 0,
        sign_interval: Optional[int] = None,
        account_name: str = "",
        account_names: Optional[List[str]] = None,
        execution_mode: str = "fixed",
        range_start: str = "",
        range_end: str = "",
        notify_on_failure: bool = True,
    ) -> Dict[str, Any]:
        """Create a sign task that can be shared by multiple accounts."""
        from backend.services.config import get_config_service

        task_name = validate_storage_name(task_name, field_name="task_name")
        target_accounts = self._normalize_account_names(account_names, account_name)
        if not target_accounts:
            raise ValueError("必须指定至少一个账号名称")

        # Preserve the original list (may contain "*") for config storage
        stored_account_names = list(target_accounts)
        # Expand wildcard for actual directory creation and scheduling
        target_accounts = self._expand_account_names(target_accounts)
        if not target_accounts:
            raise ValueError("没有可用的账号")

        if sign_interval is None:
            config_service = get_config_service()
            global_settings = config_service.get_global_settings()
            sign_interval = global_settings.get("sign_interval")

        if sign_interval is None:
            sign_interval = 1

        task_group_id = uuid.uuid4().hex if len(target_accounts) > 1 else ""
        should_schedule = execution_mode != "listen"
        trigger_cron = range_start if execution_mode == "range" else sign_at

        for current_account in target_accounts:
            account_dir = self.signs_dir / current_account
            account_dir.mkdir(parents=True, exist_ok=True)

            task_dir = account_dir / task_name
            task_dir.mkdir(parents=True, exist_ok=True)

            config = {
                "_version": 4,
                "task_group_id": task_group_id,
                "account_name": current_account,
                "account_names": stored_account_names,
                "sign_at": sign_at,
                "random_seconds": random_seconds,
                "sign_interval": sign_interval,
                "chats": chats,
                "execution_mode": execution_mode,
                "range_start": range_start,
                "range_end": range_end,
                "notify_on_failure": notify_on_failure,
            }

            with open(task_dir / "config.json", "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)

        self._tasks_cache = None

        try:
            from backend.scheduler import (
                add_or_update_sign_task_job,
                remove_sign_task_job,
            )

            for current_account in target_accounts:
                if should_schedule:
                    add_or_update_sign_task_job(
                        current_account,
                        task_name,
                        trigger_cron,
                        enabled=True,
                    )
                else:
                    remove_sign_task_job(current_account, task_name)
        except Exception as e:
            _service_logger.debug(f"更新调度任务失败: {e}")

        related = self._find_related_task_infos(task_name, target_accounts[0])
        if len(target_accounts) > 1:
            grouped = self._aggregate_tasks(related)
            if grouped:
                return grouped[0]
        task = self.get_task(task_name, account_name=target_accounts[0])
        if task is None:
            raise ValueError(f"任务 {task_name} 创建后无法读取")
        return task

    def update_task(
        self,
        task_name: str,
        sign_at: Optional[str] = None,
        chats: Optional[List[Dict[str, Any]]] = None,
        random_seconds: Optional[int] = None,
        sign_interval: Optional[int] = None,
        account_name: Optional[str] = None,
        account_names: Optional[List[str]] = None,
        execution_mode: Optional[str] = None,
        range_start: Optional[str] = None,
        range_end: Optional[str] = None,
        notify_on_failure: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Update one task and fan out the config to all linked accounts."""
        task_name = validate_storage_name(task_name, field_name="task_name")

        # Normalize account_name: skip wildcard, resolve to real account
        if account_name == "*":
            account_name = None

        existing = self.get_task(
            task_name,
            account_name=account_name,
            aggregate=account_name is None,
        )
        related_tasks = self._find_related_task_infos(task_name, account_name)
        if not existing or not related_tasks:
            raise ValueError(f"任务 {task_name} 不存在")

        existing_accounts = self._normalize_account_names(
            existing.get("account_names"), existing.get("account_name")
        )
        target_accounts = (
            self._normalize_account_names(account_names)
            if account_names is not None
            else existing_accounts
        )
        if not target_accounts:
            raise ValueError("任务至少需要保留一个账号")

        # Preserve original list (may contain "*") for config storage
        stored_account_names = list(target_accounts)
        # Expand wildcard "*" to actual account names for directory creation
        target_accounts = self._expand_account_names(target_accounts)
        if not target_accounts:
            raise ValueError("没有可用的账号")
        # Also expand existing_accounts for proper diff calculation
        existing_accounts = self._expand_account_names(existing_accounts)

        current_group_id = str(existing.get("task_group_id") or "").strip()
        next_group_id = ""
        if len(target_accounts) > 1:
            next_group_id = current_group_id or uuid.uuid4().hex

        next_sign_at = sign_at if sign_at is not None else str(existing["sign_at"])
        next_random_seconds = (
            random_seconds
            if random_seconds is not None
            else int(existing["random_seconds"])
        )
        next_sign_interval = (
            sign_interval
            if sign_interval is not None
            else int(existing["sign_interval"])
        )
        next_chats = chats if chats is not None else existing["chats"]
        next_execution_mode = (
            execution_mode
            if execution_mode is not None
            else str(existing.get("execution_mode", "fixed"))
        )
        next_range_start = (
            range_start if range_start is not None else str(existing.get("range_start", ""))
        )
        next_range_end = (
            range_end if range_end is not None else str(existing.get("range_end", ""))
        )
        next_notify_on_failure = (
            notify_on_failure
            if notify_on_failure is not None
            else bool(existing.get("notify_on_failure", True))
        )
        should_schedule = next_execution_mode != "listen"

        existing_dirs = dict(self._iter_task_dirs(task_name, existing_accounts))
        existing_last_run_map = {
            str(task.get("account_name") or ""): task.get("last_run")
            for task in related_tasks
        }
        removed_accounts = [
            current_account
            for current_account in existing_accounts
            if current_account not in target_accounts
        ]

        import shutil

        from backend.scheduler import add_or_update_sign_task_job, remove_sign_task_job

        for removed_account in removed_accounts:
            removed_dir = existing_dirs.get(removed_account)
            if removed_dir and removed_dir.exists():
                shutil.rmtree(removed_dir)
            remove_sign_task_job(removed_account, task_name)

        for current_account in target_accounts:
            desired_dir = self.signs_dir / current_account / task_name
            desired_dir.mkdir(parents=True, exist_ok=True)

            config: Dict[str, Any] = {
                "_version": 4,
                "task_group_id": next_group_id,
                "account_name": current_account,
                "account_names": stored_account_names,
                "sign_at": next_sign_at,
                "random_seconds": next_random_seconds,
                "sign_interval": next_sign_interval,
                "chats": next_chats,
                "execution_mode": next_execution_mode,
                "range_start": next_range_start,
                "range_end": next_range_end,
                "notify_on_failure": next_notify_on_failure,
            }
            last_run = existing_last_run_map.get(current_account)
            if last_run:
                config["last_run"] = last_run

            with open(desired_dir / "config.json", "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)

            previous_dir = existing_dirs.get(current_account)
            if (
                previous_dir is not None
                and previous_dir != desired_dir
                and previous_dir.exists()
            ):
                shutil.rmtree(previous_dir)

            if should_schedule:
                add_or_update_sign_task_job(
                    current_account,
                    task_name,
                    next_range_start if next_execution_mode == "range" else next_sign_at,
                    enabled=True,
                )
            else:
                remove_sign_task_job(current_account, task_name)

        self._tasks_cache = None
        self._append_scheduler_log(
            "scheduler_update.log",
            f"{datetime.now()}: Updated task {task_name} for {','.join(target_accounts)}",
        )

        related = self._find_related_task_infos(task_name, target_accounts[0])
        if len(target_accounts) > 1:
            grouped = self._aggregate_tasks(related)
            if grouped:
                return grouped[0]
        task = self.get_task(task_name, account_name=target_accounts[0])
        if task is None:
            raise ValueError(f"任务 {task_name} 更新后无法读取")
        return task

    def rename_account_references(
        self,
        old_account_name: str,
        new_account_name: str,
    ) -> None:
        old_account_name = validate_storage_name(
            old_account_name,
            field_name="account_name",
        )
        new_account_name = validate_storage_name(
            new_account_name,
            field_name="account_name",
        )
        if old_account_name == new_account_name:
            return

        old_account_dir = self.signs_dir / old_account_name
        new_account_dir = self.signs_dir / new_account_name

        if old_account_dir.exists():
            self._move_storage_path(old_account_dir, new_account_dir)

        for config_path in self.signs_dir.glob("*/*/config.json"):
            try:
                config = json.loads(config_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(config, dict):
                continue

            changed = False
            if str(config.get("account_name") or "").strip() == old_account_name:
                config["account_name"] = new_account_name
                changed = True

            account_names = config.get("account_names")
            if isinstance(account_names, list):
                next_account_names: List[str] = []
                for item in account_names:
                    current_name = str(item or "").strip()
                    if not current_name:
                        continue
                    if current_name == old_account_name:
                        current_name = new_account_name
                    if current_name not in next_account_names:
                        next_account_names.append(current_name)
                if next_account_names != account_names:
                    config["account_names"] = next_account_names
                    changed = True

            if not changed:
                continue

            config_path.write_text(
                json.dumps(config, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        safe_old = self._safe_history_key(old_account_name)
        safe_new = self._safe_history_key(new_account_name)
        for history_file in self.run_history_dir.glob(f"{safe_old}__*.json"):
            target_file = self.run_history_dir / history_file.name.replace(
                f"{safe_old}__",
                f"{safe_new}__",
                1,
            )
            try:
                raw_data = json.loads(history_file.read_text(encoding="utf-8"))
            except Exception:
                raw_data = None

            if isinstance(raw_data, list):
                for item in raw_data:
                    if (
                        isinstance(item, dict)
                        and str(item.get("account_name") or "").strip() == old_account_name
                    ):
                        item["account_name"] = new_account_name
                history_file.write_text(
                    json.dumps(raw_data, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            elif (
                isinstance(raw_data, dict)
                and str(raw_data.get("account_name") or "").strip() == old_account_name
            ):
                raw_data["account_name"] = new_account_name
                history_file.write_text(
                    json.dumps(raw_data, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

            self._move_storage_path(history_file, target_file)

        for mapping_name in ("_active_logs", "_active_tasks", "_cleanup_tasks"):
            mapping = getattr(self, mapping_name)
            for key in list(mapping.keys()):
                account_name, task_name = key
                if account_name != old_account_name:
                    continue
                mapping[(new_account_name, task_name)] = mapping.pop(key)

        last_run_value = self._account_last_run_end.pop(old_account_name, None)
        if last_run_value is not None:
            self._account_last_run_end[new_account_name] = last_run_value

        self._tasks_cache = None

    def delete_task(
        self, task_name: str, account_name: Optional[str] = None
    ) -> bool:
        """Delete one task or one shared multi-account task set."""
        task_name = validate_storage_name(task_name, field_name="task_name")
        related_tasks = self._find_related_task_infos(task_name, account_name)
        if not related_tasks:
            return False

        task_dirs = self._iter_task_dirs(
            task_name,
            [str(task.get("account_name") or "") for task in related_tasks],
        )
        if not task_dirs:
            return False

        import shutil

        from backend.scheduler import remove_sign_task_job

        removed_paths: set[str] = set()
        for current_account, task_dir in task_dirs:
            resolved = str(task_dir.resolve())
            if resolved in removed_paths:
                continue
            if task_dir.exists():
                shutil.rmtree(task_dir)
            removed_paths.add(resolved)
            if current_account:
                remove_sign_task_job(current_account, task_name)

        self._tasks_cache = None
        return True

    async def get_account_chats(
        self, account_name: str, force_refresh: bool = False
    ) -> List[Dict[str, Any]]:
        """
        获取账号的 Chat 列表 (带缓存)
        """
        account_name = validate_storage_name(account_name, field_name="account_name")
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
        account_name = validate_storage_name(account_name, field_name="account_name")
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
            _service_logger.debug(f"清理无效 Session 失败: {e}")

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
        account_name = validate_storage_name(account_name, field_name="account_name")

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

                            # Try get_dialogs with async for with safety limit
                            try:
                                async for dialog in active_client.get_dialogs(limit=100):
                                    try:
                                        chat = getattr(dialog, "chat", None)
                                        if chat is None:
                                            continue
                                        chat_id = getattr(chat, "id", None)
                                        if chat_id is None:
                                            continue

                                        chat_type = getattr(chat, "type", None)
                                        type_name = chat_type.name.lower() if chat_type else "private"

                                        local_chats.append({
                                            "id": chat_id,
                                            "title": getattr(chat, "title", None)
                                            or getattr(chat, "first_name", None)
                                            or getattr(chat, "username", None)
                                            or str(chat_id),
                                            "username": getattr(chat, "username", None),
                                            "type": type_name,
                                        })
                                    except Exception:
                                        continue
                            except Exception as e:
                                logger.warning(
                                    f"get_dialogs 失败 (已获取 {len(local_chats)} 个): {type(e).__name__}: {e}"
                                )

                            # Fallback: if get_dialogs returned nothing, try search_global
                            if not local_chats:
                                logger.info("get_dialogs 返回空，尝试 search_global 获取会话")
                                seen_ids: set = set()
                                for term in ["", "a", "1"]:
                                    try:
                                        async for msg in active_client.search_global(term, limit=50):
                                            try:
                                                chat = getattr(msg, "chat", None)
                                                if chat is None:
                                                    continue
                                                chat_id = getattr(chat, "id", None)
                                                if chat_id is None or chat_id in seen_ids:
                                                    continue
                                                seen_ids.add(chat_id)

                                                chat_type = getattr(chat, "type", None)
                                                type_name = chat_type.name.lower() if chat_type else "private"

                                                local_chats.append({
                                                    "id": chat_id,
                                                    "title": getattr(chat, "title", None)
                                                    or getattr(chat, "first_name", None)
                                                    or getattr(chat, "username", None)
                                                    or str(chat_id),
                                                    "username": getattr(chat, "username", None),
                                                    "type": type_name,
                                                })
                                            except Exception:
                                                continue
                                    except Exception:
                                        continue

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
                atomic_write_json(cache_file, chats, indent=2)
            except Exception as e:
                _service_logger.debug(f"保存 Chat 缓存失败: {e}")

            return chats

        finally:
            trim_memory()

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
        monitor_logs: List[str] = []
        try:
            from backend.services.keyword_monitor import get_keyword_monitor_service

            monitor_logs = get_keyword_monitor_service().get_task_logs(
                task_name,
                account_name,
            )
        except Exception:
            monitor_logs = []

        if account_name:
            logs = list(self._active_logs.get(self._task_key(account_name, task_name), []))
            if monitor_logs:
                if logs:
                    logs.append("---- 关键词后台监听日志 ----")
                logs.extend(monitor_logs)
            return logs
        # 兼容旧接口：返回第一个同名任务的日志
        for key in self._find_task_keys(task_name):
            logs = list(self._active_logs.get(key, []))
            if monitor_logs:
                if logs:
                    logs.append("---- 关键词后台监听日志 ----")
                logs.extend(monitor_logs)
            return logs
        return monitor_logs

    def _set_run_status(
        self,
        account_name: str,
        task_name: str,
        *,
        run_id: str,
        state: str,
        success: Optional[bool] = None,
        error: str = "",
        output: str = "",
        started_at: Optional[str] = None,
        finished_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        task_key = self._task_key(account_name, task_name)
        status = {
            "run_id": run_id,
            "state": state,
            "success": success,
            "error": str(error or ""),
            "output": str(output or ""),
            "started_at": started_at or utc_now_iso(),
            "finished_at": finished_at,
        }
        self._run_statuses[task_key] = status
        return dict(status)

    def _schedule_run_status_cleanup(self, account_name: str, task_name: str) -> None:
        task_key = self._task_key(account_name, task_name)
        old_cleanup_task = self._run_status_cleanup_tasks.get(task_key)
        if old_cleanup_task and not old_cleanup_task.done():
            old_cleanup_task.cancel()

        async def cleanup() -> None:
            try:
                await asyncio.sleep(600)
                if not self._active_tasks.get(task_key):
                    self._run_statuses.pop(task_key, None)
            finally:
                self._run_status_cleanup_tasks.pop(task_key, None)

        self._run_status_cleanup_tasks[task_key] = create_logged_task(
            cleanup(),
            logger=logging.getLogger("backend.sign_tasks"),
            description=f"run status cleanup {account_name}/{task_name}",
        )

    async def start_task_run(self, account_name: str, task_name: str) -> Dict[str, Any]:
        account_name = validate_storage_name(account_name, field_name="account_name")
        task_name = validate_storage_name(task_name, field_name="task_name")

        task_key = self._task_key(account_name, task_name)
        existing_status = self._run_statuses.get(task_key)
        if self._active_tasks.get(task_key):
            if existing_status:
                return dict(existing_status)
            return {
                "run_id": "",
                "state": "running",
                "success": None,
                "error": "",
                "output": "",
                "started_at": utc_now_iso(),
                "finished_at": None,
            }

        task = self.get_task(task_name, account_name=account_name)
        if not task:
            raise ValueError(f"Task {task_name} does not exist or cannot be loaded")

        run_id = uuid.uuid4().hex
        started_at = utc_now_iso()
        status = self._set_run_status(
            account_name,
            task_name,
            run_id=run_id,
            state="running",
            success=None,
            error="",
            output="",
            started_at=started_at,
            finished_at=None,
        )

        async def runner() -> None:
            result: Dict[str, Any]
            state = "finished"
            try:
                result = await self.run_task_with_logs(account_name, task_name)
            except asyncio.CancelledError:
                state = "cancelled"
                result = {
                    "success": False,
                    "error": "Task execution cancelled",
                    "output": "",
                }
            except Exception as exc:
                result = {
                    "success": False,
                    "error": str(exc) or "Task execution failed",
                    "output": "",
                }

            current_status = self._run_statuses.get(task_key)
            if current_status and current_status.get("run_id") == run_id:
                self._set_run_status(
                    account_name,
                    task_name,
                    run_id=run_id,
                    state=state,
                    success=bool(result.get("success", False)),
                    error=str(result.get("error") or ""),
                    output=str(result.get("output") or ""),
                    started_at=started_at,
                    finished_at=utc_now_iso(),
                )
                self._schedule_run_status_cleanup(account_name, task_name)
            self._background_run_tasks.pop(task_key, None)

        background_task = create_logged_task(
            runner(),
            logger=logging.getLogger("backend.sign_tasks"),
            description=f"sign task run {account_name}/{task_name}",
        )
        self._background_run_tasks[task_key] = background_task
        return status

    def get_task_run_status(
        self, account_name: str, task_name: str, run_id: Optional[str] = None
    ) -> Dict[str, Any]:
        account_name = validate_storage_name(account_name, field_name="account_name")
        task_name = validate_storage_name(task_name, field_name="task_name")

        task_key = self._task_key(account_name, task_name)
        status = self._run_statuses.get(task_key)
        if not status:
            return {
                "run_id": run_id or "",
                "state": "idle",
                "success": None,
                "error": "",
                "output": "",
                "started_at": None,
                "finished_at": None,
            }
        if run_id and status.get("run_id") != run_id:
            return {
                "run_id": run_id,
                "state": "stale",
                "success": None,
                "error": "",
                "output": "",
                "started_at": None,
                "finished_at": None,
            }
        return dict(status)

    def is_task_running(self, task_name: str, account_name: Optional[str] = None) -> bool:
        """检查任务是否正在运行"""
        if account_name:
            return self._active_tasks.get(self._task_key(account_name, task_name), False)
        return any(key[1] == task_name for key, running in self._active_tasks.items() if running)

    async def run_task_with_logs(
        self, account_name: str, task_name: str
    ) -> Dict[str, Any]:
        """运行任务并实时捕获日志 (In-Process)"""

        account_name = validate_storage_name(account_name, field_name="account_name")
        task_name = validate_storage_name(task_name, field_name="task_name")

        if self.is_task_running(task_name, account_name):
            return {"success": False, "error": "任务已经在运行中", "output": ""}

        # 初始化账号锁（跨服务共享）
        if account_name not in self._account_locks:
            self._account_locks[account_name] = get_account_lock(account_name)

        account_lock = self._account_locks[account_name]

        # 检查是否能获取锁 (非阻塞检查，如果已被锁定则说明该账号有其他任务在运行)
        # 这里我们希望排队等待，还是直接报错？
        # 考虑到定时任务同时触发，应该排队执行。
        _service_logger.debug(f"等待获取账号锁 {account_name}...")

        task_key = self._task_key(account_name, task_name)
        self._active_tasks[task_key] = True
        self._active_logs[task_key] = []

        # 获取 logger 实例
        tg_logger = logging.getLogger("tg-signer")
        log_handler: Optional[TaskLogHandler] = None

        success = False
        error_msg = ""
        output_str = ""
        account_invalid_detected = False
        task_notify_on_failure = True
        task_cfg: Optional[Dict[str, Any]] = None
        signer: Optional[BackendUserSigner] = None

        try:
            task_cfg = self.get_task(task_name, account_name=account_name)
            if not task_cfg:
                raise ValueError(f"Task {task_name} does not exist or cannot be loaded")
            requires_updates = self._task_requires_updates(task_cfg)
            has_keyword_monitor = self._task_has_keyword_monitor(task_cfg)
            signer_no_updates = not requires_updates
            task_notify_on_failure = bool(task_cfg.get("notify_on_failure", True))

            invalid_reason = await self._check_account_before_task(
                account_name,
                task_name,
                no_updates=signer_no_updates,
                notify_on_failure=task_notify_on_failure,
            )
            if invalid_reason:
                account_invalid_detected = True
                error_msg = f"账号 {account_name} 登录已失效，请重新登录: {invalid_reason}"
                self._active_logs[task_key].append(error_msg)
            else:
                if has_keyword_monitor:
                    try:
                        from backend.services.keyword_monitor import (
                            get_keyword_monitor_service,
                        )

                        await get_keyword_monitor_service().restart_from_tasks()
                    except Exception as exc:
                        self._active_logs[task_key].append(
                            f"关键词后台监听刷新失败: {exc}"
                        )

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

                    log_handler = TaskLogHandler(self._active_logs[task_key])
                    log_handler.setLevel(logging.INFO)
                    log_handler.setFormatter(
                        logging.Formatter("%(asctime)s - %(message)s")
                    )
                    if tg_logger.getEffectiveLevel() > logging.INFO:
                        tg_logger.setLevel(logging.INFO)
                    tg_logger.addHandler(log_handler)

                    _service_logger.debug(f"已获取账号锁 {account_name}，开始执行任务 {task_name}")
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
                        # File mode: prefer in-memory to avoid SQLite "database is locked"
                        # Try to load session_string from .session_string file as fallback
                        session_string = load_session_string_file(
                            session_dir, account_name
                        )
                        if session_string:
                            use_in_memory = True
                        else:
                            use_in_memory = False

                        if os.getenv("SIGN_TASK_FORCE_IN_MEMORY") == "0":
                            # Explicitly disabled in-memory mode
                            session_string = None
                            use_in_memory = False

                    self._active_logs[task_key].append(
                        f"消息更新监听: {'开启' if requires_updates else '关闭'}"
                    )
                    if has_keyword_monitor:
                        self._active_logs[task_key].append(
                            "关键词监听说明: 该动作由后台常驻监听服务执行；本次手动运行只会刷新并展示后台监听状态，不代表监听只运行一次。"
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

                    # 执行任务（数据库锁冲突时重试，带超时保护）
                    task_timeout = float(
                        os.getenv("SIGN_TASK_EXECUTION_TIMEOUT", "300")
                    )
                    async with get_global_semaphore():
                        max_retries = 5
                        for attempt in range(max_retries):
                            try:
                                await asyncio.wait_for(
                                    signer.run_once(num_of_dialogs=20),
                                    timeout=task_timeout,
                                )
                                break
                            except asyncio.TimeoutError:
                                raise RuntimeError(
                                    f"任务执行超时（{int(task_timeout)}秒），已强制终止"
                                )
                            except Exception as e:
                                if "database is locked" in str(e).lower():
                                    if attempt < max_retries - 1:
                                        delay = 3 + (attempt * 3)
                                        self._active_logs[task_key].append(
                                            f"Session 被锁定，{delay} 秒后重试... ({attempt + 1}/{max_retries})"
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
                await self._mark_account_invalid(
                    account_name,
                    task_name,
                    invalid_message,
                    notify_on_failure=task_notify_on_failure,
                )
            error_msg = f"任务执行出错: {str(e)}"
            self._active_logs[task_key].append(error_msg)
            # 打印堆栈以便调试
            traceback.print_exc()
            logger = logging.getLogger("backend")
            logger.error(error_msg)
        finally:
            self._account_last_run_end[account_name] = time.time()
            try:
                if log_handler is not None:
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
                        if (
                            any(keyword in reply_lower for keyword in failure_keywords)
                            and self._message_indicates_strong_failure(last_reply)
                        ):
                            success = False
                            error_msg = f"机器人回复疑似失败: {last_reply}"
                            final_logs.append(error_msg)
                            self._active_logs.setdefault(task_key, []).append(error_msg)
                            output_str = "\n".join(final_logs)

                last_target_message = extract_last_target_message(final_logs)
                if success and not last_target_message and signer is not None:
                    try:
                        last_target_fetch_timeout = float(
                            os.getenv("SIGN_TASK_LAST_TARGET_FETCH_TIMEOUT", "5")
                        )
                        if last_target_fetch_timeout > 0:
                            last_target_message = await asyncio.wait_for(
                                self._fetch_last_target_message_from_chat_history(
                                    signer,
                                    task_cfg,
                                ),
                                timeout=last_target_fetch_timeout,
                            )
                        else:
                            last_target_message = await self._fetch_last_target_message_from_chat_history(
                                signer,
                                task_cfg,
                            )
                    except asyncio.TimeoutError:
                        timeout_log = (
                            f"补抓任务对象最后消息超时 ({last_target_fetch_timeout:.1f}s)，已跳过"
                        )
                        self._active_logs.setdefault(task_key, []).append(timeout_log)
                        final_logs = list(self._active_logs.get(task_key, []))
                        output_str = "\n".join(final_logs)
                        last_target_message = ""
                    except Exception:
                        last_target_message = ""
                if success and last_target_message:
                    last_reply = last_target_message
                if last_target_message and not any(
                    "任务对象最后一条消息:" in str(line) for line in final_logs
                ):
                    last_message_line = f"任务对象最后一条消息: {last_target_message}"
                    final_logs.append(last_message_line)
                    self._active_logs.setdefault(task_key, []).append(last_message_line)
                    output_str = "\n".join(final_logs)

                msg = error_msg if not success else last_reply
                self._save_run_info(
                    task_name,
                    success,
                    msg,
                    account_name,
                    flow_logs=final_logs,
                )

                if not success and not account_invalid_detected and task_notify_on_failure:
                    await self._send_failure_notification(
                        account_name,
                        task_name,
                        error_msg or msg,
                        last_target_message=last_target_message or None,
                        flow_logs=final_logs,
                    )
            finally:
                self._active_tasks[task_key] = False

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
                    trim_memory()

            self._cleanup_tasks[task_key] = create_logged_task(
                cleanup(),
                logger=logging.getLogger("backend.sign_tasks"),
                description=f"active log cleanup {account_name}/{task_name}",
            )

        # Periodic pruning of stale entries to prevent memory growth
        self._prune_stale_entries()
        trim_memory()

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
