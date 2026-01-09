"""
签到任务服务层
提供签到任务的 CRUD 操作和执行功能
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.core.config import get_settings

settings = get_settings()


class SignTaskService:
    """签到任务服务类"""

    def __init__(self):
        from backend.core.config import get_settings
        settings = get_settings()
        self.workdir = Path(settings.data_dir) / ".signer"
        self.signs_dir = self.workdir / "signs"
        self.run_history_dir = self.workdir / "history"
        self.signs_dir.mkdir(parents=True, exist_ok=True)
        self.run_history_dir.mkdir(parents=True, exist_ok=True)
        print(f"DEBUG: 初始化 SignTaskService, signs_dir={self.signs_dir}, exists={self.signs_dir.exists()}")
        self._active_logs: Dict[str, List[str]] = {}  # 存储正在运行任务的实时日志
        self._active_tasks: Dict[str, bool] = {}     # 记录正在运行的任务
        self._tasks_cache = None  # 内存缓存
        self._cleanup_old_logs()

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

    def get_account_history_logs(self, account_name: str) -> List[Dict[str, Any]]:
        """获取某账号下所有任务的最近历史日志"""
        all_history = []
        if not self.run_history_dir.exists():
            return []

        for history_file in self.run_history_dir.glob("*.json"):
            try:
                with open(history_file, "r", encoding="utf-8") as f:
                    data_list = json.load(f)
                    if not isinstance(data_list, list):
                        data_list = [data_list]

                    for data in data_list:
                        if data.get("account_name") == account_name:
                            data["task_name"] = history_file.stem
                            all_history.append(data)
            except Exception:
                continue

        # 按时间倒序
        all_history.sort(key=lambda x: x.get("time", ""), reverse=True)
        return all_history

    def _get_last_run_info(self, task_dir: Path) -> Optional[Dict[str, Any]]:
        """
        获取任务的最后执行信息
        """
        history_file = self.run_history_dir / f"{task_dir.name}.json"

        if not history_file.exists():
            return None

        try:
            with open(history_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and len(data) > 0:
                    return data[0] # 最近的一条
                elif isinstance(data, dict):
                    return data
                return None
        except Exception:
            return None

    def _save_run_info(self, task_name: str, success: bool, message: str = "", account_name: str = ""):
        """保存任务执行历史 (保留列表)"""
        from datetime import datetime

        history_file = self.run_history_dir / f"{task_name}.json"

        new_entry = {
            "time": datetime.now().isoformat(),
            "success": success,
            "message": message,
            "account_name": account_name
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
        # 只保留最近 100 条
        history = history[:100]

        try:
            with open(history_file, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=2)

            # 同时更新任务配置中的 last_run，减少 list_tasks 时的 I/O
            task = self.get_task(task_name, account_name)
            if task:
                 task_dir = self.signs_dir / account_name / task_name
                 config_file = task_dir / "config.json"
                 if config_file.exists():
                     with open(config_file, "r", encoding="utf-8") as f:
                         config = json.load(f)
                     config["last_run"] = new_entry
                     with open(config_file, "w", encoding="utf-8") as f:
                         json.dump(config, f, ensure_ascii=False, indent=2)
            # 清除缓存
            self._tasks_cache = None
        except Exception as e:
            print(f"DEBUG: 保存运行信息失败: {str(e)}")

    def list_tasks(self, account_name: Optional[str] = None, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        获取所有签到任务列表 (支持内存缓存)
        """
        if self._tasks_cache is not None and not force_refresh:
            if account_name:
                return [t for t in self._tasks_cache if t.get("account_name") == account_name]
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

            self._tasks_cache = sorted(tasks, key=lambda x: (x["account_name"], x["name"]))

            if account_name:
                return [t for t in self._tasks_cache if t.get("account_name") == account_name]
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
                last_run = self._get_last_run_info(task_dir)

            return {
                "name": task_dir.name,
                "account_name": config.get("account_name", ""),
                "sign_at": config.get("sign_at", ""),
                "random_seconds": config.get("random_seconds", 0),
                "sign_interval": config.get("sign_interval", 1),
                "chats": config.get("chats", []),
                "enabled": True,
                "last_run": last_run,
            }
        except Exception:
            return None

    def get_task(self, task_name: str, account_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
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
                    if acc_dir.is_dir() and (acc_dir / task_name / "config.json").exists():
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
    ) -> Dict[str, Any]:
        """
        创建新的签到任务
        """
        import random

        from backend.services.config import config_service

        if not account_name:
             raise ValueError("必须指定账号名称")

        account_dir = self.signs_dir / account_name
        account_dir.mkdir(parents=True, exist_ok=True)

        task_dir = account_dir / task_name
        task_dir.mkdir(parents=True, exist_ok=True)

        # 获取 sign_interval
        if sign_interval is None:
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
        }

        config_file = task_dir / "config.json"

        try:
            with open(config_file, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"DEBUG: 写入配置文件失败: {str(e)}")
            raise

        return {
            "name": task_name,
            "account_name": account_name,
            "sign_at": sign_at,
            "random_seconds": random_seconds,
            "sign_interval": sign_interval,
            "chats": chats,
            "enabled": True,
        }

    def update_task(
        self,
        task_name: str,
        sign_at: Optional[str] = None,
        chats: Optional[List[Dict[str, Any]]] = None,
        random_seconds: Optional[int] = None,
        sign_interval: Optional[int] = None,
        account_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        更新签到任务
        """
        # 获取现有配置
        existing = self.get_task(task_name, account_name)
        if not existing:
            raise ValueError(f"任务 {task_name} 不存在")

        acc_name = account_name or existing.get("account_name", "")

        # 更新配置
        config = {
            "_version": 3,
            "account_name": acc_name,
            "sign_at": sign_at if sign_at is not None else existing["sign_at"],
            "random_seconds": random_seconds if random_seconds is not None else existing["random_seconds"],
            "sign_interval": sign_interval if sign_interval is not None else existing["sign_interval"],
            "chats": chats if chats is not None else existing["chats"],
        }

        # 保存配置
        task_dir = self.signs_dir / acc_name / task_name
        if not task_dir.exists():
            # 兼容旧路径
            task_dir = self.signs_dir / task_name

        config_file = task_dir / "config.json"
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

        return {
            "name": task_name,
            "account_name": config["account_name"],
            "sign_at": config["sign_at"],
            "random_seconds": config["random_seconds"],
            "sign_interval": config["sign_interval"],
            "chats": config["chats"],
            "enabled": True,
        }

    def delete_task(self, task_name: str, account_name: Optional[str] = None) -> bool:
        """
        删除签到任务
        """
        task_dir = None
        if account_name:
            task_dir = self.signs_dir / account_name / task_name

        if not task_dir or not task_dir.exists():
            # 搜一下
            task_dir = self.signs_dir / task_name
            if not task_dir.exists():
                for acc_dir in self.signs_dir.iterdir():
                    if acc_dir.is_dir() and (acc_dir / task_name).exists():
                        task_dir = acc_dir / task_name
                        break

        if not task_dir or not task_dir.exists():
            return False

        try:
            import shutil
            shutil.rmtree(task_dir)
            return True
        except Exception:
            return False

    async def get_account_chats(self, account_name: str, force_refresh: bool = False) -> List[Dict[str, Any]]:
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

    async def refresh_account_chats(self, account_name: str) -> List[Dict[str, Any]]:
        """
        连接 Telegram 并刷新 Chat 列表
        """
        from pyrogram import Client
        from pyrogram.enums import ChatType

        # 获取 session 文件路径
        from backend.core.config import get_settings
        from backend.services.config import config_service
        settings = get_settings()
        session_dir = Path(settings.data_dir) / "sessions"
        session_path = str(session_dir / account_name)

        if not (session_dir / f"{account_name}.session").exists():
            raise ValueError(f"账号 {account_name} 的 Session 文件不存在")

        tg_config = config_service.get_telegram_config()
        api_id = os.getenv("TG_API_ID", tg_config.get("api_id"))
        api_hash = os.getenv("TG_API_HASH", tg_config.get("api_hash"))

        if not api_id or not api_hash:
            raise ValueError("未配置 Telegram API ID 或 API Hash")

        client = Client(
            name=session_path,
            api_id=int(api_id),
            api_hash=api_hash,
            in_memory=False, # 必须为 False 才能加载本地 session 文件
        )

        chats = []
        try:
            await client.connect()
            try:
                # 尝试获取用户信息，如果失败说明 session 无效
                await client.get_me()
            except Exception as e:
                # 捕获所有异常，如果是 401 等错误则说明 session 失效
                # 显式抛出错误而不是进入交互式登录 (导致 EOFError)
                raise ValueError(f"Session 无效或已过期: {e}")

            # 确认已授权，由于已经 connect，这里不需要再 start() 也可以调用 get_dialogs 吗?
            # Pyrogram 建议使用 start() 来初始化所有组件，但 start() 可能会再次检查授权调用 interactive_login
            # 由于我们已经验证了 get_me() 成功，start() 内部的 authorize() 检查应该也会通过，从而跳过 interactive_login
            # 但是为了保险，我们可以跳过 start() 直接使用，或者确信 start() 安全。
            # 这里如果不掉 start()，get_dialogs 可能无法正确工作 (dispatcher 未启动?)
            # 实际上 get_dialogs 是 API 方法，只要 connect 就可以。
            # 但为了稳妥，我们不调用 start() 以免副作用，直接使用 connected client。
            # 修正：Pyrogram 的 get_dialogs 并不依赖 dispatcher，只要 connected 即可。

            async for dialog in client.get_dialogs():
                chat = dialog.chat

                chat_info = {
                    "id": chat.id,
                    "title": chat.title or chat.first_name or chat.username or str(chat.id),
                    "username": chat.username,
                    "type": chat.type.name.lower(),
                }

                # 特殊处理机器人和私聊
                if chat.type == ChatType.BOT:
                    chat_info["title"] = f"🤖 {chat_info['title']}"

                chats.append(chat_info)

            await client.stop()

            # 保存到缓存
            account_dir = self.signs_dir / account_name
            account_dir.mkdir(parents=True, exist_ok=True)
            cache_file = account_dir / "chats_cache.json"

            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(chats, f, ensure_ascii=False, indent=2)

            return chats

        except Exception as e:
            try:
                await client.stop()
            except Exception:
                pass
            raise e

    def run_task(self, account_name: str, task_name: str) -> Dict[str, Any]:
        """
        运行签到任务

        Args:
            account_name: 账号名称
            task_name: 任务名称

        Returns:
            执行结果
        """
        if self.is_task_running(task_name):
            return {"success": False, "error": "任务已经在运行中", "output": ""}

        self._active_tasks[task_name] = True
        try:
            # 调用 CLI 命令执行任务
            import subprocess

            # 构建命令: tg-signer --workdir <workdir> --session_dir <session_dir> --account <account> run-once <task>
            session_dir = str(Path(settings.data_dir) / "sessions")

            cmd = [
                "tg-signer",
                "--workdir", str(self.workdir),
                "--session_dir", session_dir,
                "--account", account_name,
                "run-once",  # 使用 run-once 来运行一次
                task_name,
            ]

            print(f"DEBUG: 执行命令: {' '.join(cmd)}")

            # 获取环境变量并注入 Telegram API 凭据
            env = os.environ.copy()
            from backend.services.config import config_service
            tg_config = config_service.get_telegram_config()
            if tg_config.get("api_id"):
                env["TG_API_ID"] = str(tg_config["api_id"])
            if tg_config.get("api_hash"):
                env["TG_API_HASH"] = tg_config["api_hash"]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5 分钟超时
                env=env,
            )

            # 打印 CLI 执行结果，用于调试
            print(f"DEBUG: CLI 返回码: {result.returncode}")
            if result.stdout:
                print(f"DEBUG: CLI stdout:\n{result.stdout}")
            if result.stderr:
                print(f"DEBUG: CLI stderr:\n{result.stderr}")

            success = result.returncode == 0
            error_msg = result.stderr if not success else ""

            # 保存执行记录
            self._save_run_info(task_name, success, error_msg)

            return {
                "success": success,
                "output": result.stdout,
                "error": result.stderr,
            }
        except subprocess.TimeoutExpired:
            # 保存超时记录
            self._save_run_info(task_name, False, "任务执行超时（超过 5 分钟）")
            return {
                "success": False,
                "output": "",
                "error": "任务执行超时（超过 5 分钟）",
            }
        except Exception as e:
            # 保存错误记录
            self._save_run_info(task_name, False, str(e), account_name)
            return {
                "success": False,
                "output": "",
                "error": str(e),
            }
        finally:
            self._active_tasks[task_name] = False

    def get_active_logs(self, task_name: str) -> List[str]:
        """获取正在运行任务的日志"""
        return self._active_logs.get(task_name, [])

    def is_task_running(self, task_name: str) -> bool:
        """检查任务是否正在运行"""
        return self._active_tasks.get(task_name, False)

    async def run_task_with_logs(self, account_name: str, task_name: str) -> Dict[str, Any]:
        """运行任务并实时捕获日志"""
        import asyncio

        if self.is_task_running(task_name):
            return {"success": False, "error": "任务已经在运行中", "output": ""}

        self._active_tasks[task_name] = True
        self._active_logs[task_name] = []

        session_dir = str(Path(settings.data_dir) / "sessions")
        cmd = [
            "tg-signer",
            "--workdir", str(self.workdir),
            "--session_dir", session_dir,
            "--account", account_name,
            "run-once",
            task_name,
        ]

        env = os.environ.copy()
        from backend.services.config import config_service
        tg_config = config_service.get_telegram_config()
        if tg_config.get("api_id"):
            env["TG_API_ID"] = str(tg_config["api_id"])
        if tg_config.get("api_hash"):
            env["TG_API_HASH"] = tg_config["api_hash"]

        try:
            # 使用 asyncio 创建子进程
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=env
            )

            full_output = []
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                decoded_line = line.decode('utf-8', errors='replace').strip()
                if decoded_line:
                    self._active_logs[task_name].append(decoded_line)
                    full_output.append(decoded_line)
                    # 保持日志长度，避免内存占用过大
                    if len(self._active_logs[task_name]) > 500:
                        self._active_logs[task_name].pop(0)

            await process.wait()
            success = process.returncode == 0
            output_str = "\n".join(full_output)

            self._save_run_info(task_name, success, "" if success else "执行失败", account_name)

            return {
                "success": success,
                "output": output_str,
                "error": "" if success else "Exit code " + str(process.returncode),
            }
        except Exception as e:
            msg = f"运行时发生异常: {str(e)}"
            self._active_logs[task_name].append(msg)
            self._save_run_info(task_name, False, msg, account_name)
            return {"success": False, "output": "", "error": msg}
        finally:
            self._active_tasks[task_name] = False
            # 注意：不立即删除日志，让前端有最后一次机会读取
            # 我们可以在下一次任务开始时清理，或者设置一个延时清理
            async def cleanup():
                await asyncio.sleep(60) # 60秒后清理
                if not self._active_tasks.get(task_name):
                    self._active_logs.pop(task_name, None)
            asyncio.create_task(cleanup())


# 创建全局实例
sign_task_service = SignTaskService()
