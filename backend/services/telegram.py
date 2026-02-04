"""
Telegram 服务层
提供 Telegram 账号管理和操作的核心功能
"""

from __future__ import annotations

import asyncio
import base64
import os
import secrets
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from backend.core.config import get_settings
from backend.utils.account_locks import get_account_lock
from backend.utils.proxy import build_proxy_dict
from backend.utils.tg_session import (
    delete_account_session_string,
    delete_session_string_file,
    get_account_session_string,
    get_account_profile,
    get_global_semaphore,
    get_no_updates_flag,
    get_session_mode,
    is_string_session_mode,
    list_account_names,
    load_session_string_file,
    save_session_string_file,
    set_account_session_string,
)

settings = get_settings()

# 全局存储临时的登录 session
_login_sessions = {}
_qr_login_sessions = {}


class TelegramService:
    """Telegram 服务类"""

    def __init__(self):
        self.session_dir = settings.resolve_session_dir()
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self._accounts_cache: Optional[List[Dict[str, Any]]] = None

    def list_accounts(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        获取所有账号列表（基于 session 文件）

        Returns:
            账号列表，每个账号包含：
            - name: 账号名称
            - session_file: session 文件路径
            - exists: session 文件是否存在
            - size: 文件大小（字节）
        """
        if self._accounts_cache is not None and not force_refresh:
            return self._accounts_cache

        accounts = []

        # 扫描 session 目录
        try:
            if is_string_session_mode():
                seen = set()
                for session_file in self.session_dir.glob("*.session_string"):
                    account_name = session_file.stem
                    seen.add(account_name)
                    profile = get_account_profile(account_name)
                    accounts.append(
                        {
                            "name": account_name,
                            "session_file": str(session_file),
                            "exists": session_file.exists(),
                            "size": session_file.stat().st_size
                            if session_file.exists()
                            else 0,
                            "remark": profile.get("remark"),
                            "proxy": profile.get("proxy"),
                        }
                    )

                for account_name in list_account_names():
                    if account_name in seen:
                        continue
                    session_file = self.session_dir / f"{account_name}.session_string"
                    profile = get_account_profile(account_name)
                    accounts.append(
                        {
                            "name": account_name,
                            "session_file": str(session_file),
                            "exists": session_file.exists(),
                            "size": session_file.stat().st_size
                            if session_file.exists()
                            else 0,
                            "remark": profile.get("remark"),
                            "proxy": profile.get("proxy"),
                        }
                    )
            else:
                for session_file in self.session_dir.glob("*.session"):
                    account_name = session_file.stem  # 文件名（不含扩展名）
                    profile = get_account_profile(account_name)

                    accounts.append(
                        {
                            "name": account_name,
                            "session_file": str(session_file),
                            "exists": session_file.exists(),
                            "size": session_file.stat().st_size
                            if session_file.exists()
                            else 0,
                            "remark": profile.get("remark"),
                            "proxy": profile.get("proxy"),
                        }
                    )

            self._accounts_cache = sorted(accounts, key=lambda x: x["name"])
            return self._accounts_cache
        except Exception:
            return []

    def account_exists(self, account_name: str) -> bool:
        """检查账号是否存在"""
        # 优先查缓存
        if self._accounts_cache is not None:
            for acc in self._accounts_cache:
                if acc["name"] == account_name:
                    return True
            # 如果缓存里没有，可能是缓存过期，也可是真的没有
            # 保险起见，如果没有找到，还是查一下文件，或者信任缓存？
            # 考虑到 start_login 会更新缓存，应该可以信任。
            # 但为了稳妥，如果缓存没命中，再查文件
            pass

        if is_string_session_mode():
            if get_account_session_string(account_name):
                return True
            if load_session_string_file(self.session_dir, account_name):
                return True
            return False

        session_file = self.session_dir / f"{account_name}.session"
        return session_file.exists()

    async def delete_account(self, account_name: str) -> bool:
        """
        删除账号（删除 session 文件）

        Args:
            account_name: 账号名称

        Returns:
            是否成功删除
        """
        # 确保释放资源
        from tg_signer.core import close_client_by_name

        # 尝试关闭 active client
        try:
            await close_client_by_name(account_name, workdir=self.session_dir)
        except Exception as e:
            print(f"DEBUG: 关闭 Account Client 失败: {e}")

        session_file = self.session_dir / f"{account_name}.session"
        session_mode = get_session_mode()
        has_session_string = False
        if session_mode == "string":
            has_session_string = bool(
                get_account_session_string(account_name)
                or load_session_string_file(self.session_dir, account_name)
            )
            if not session_file.exists() and not has_session_string:
                return False
        else:
            if not session_file.exists():
                return False

        try:
            if session_file.exists():
                session_file.unlink()

                # 同时删除可能存在的 .session-journal 文件
                journal_file = self.session_dir / f"{account_name}.session-journal"
                if journal_file.exists():
                    journal_file.unlink()

                # 删除 shm 和 wal 文件 (sqlite3)
                shm_file = self.session_dir / f"{account_name}.session-shm"
                if shm_file.exists():
                    shm_file.unlink()

                wal_file = self.session_dir / f"{account_name}.session-wal"
                if wal_file.exists():
                    wal_file.unlink()

            if session_mode == "string" and has_session_string:
                delete_account_session_string(account_name)
                delete_session_string_file(self.session_dir, account_name)

            # 更新缓存
            if self._accounts_cache is not None:
                self._accounts_cache = [
                    acc for acc in self._accounts_cache if acc["name"] != account_name
                ]

            return True
        except OSError:
            return False

    async def start_login(
        self, account_name: str, phone_number: str, proxy: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        开始登录流程（发送验证码）

        这个方法会：
        1. 创建 Pyrogram 客户端
        2. 发送验证码到手机
        3. 返回 phone_code_hash 用于后续验证

        Args:
            account_name: 账号名称
            phone_number: 手机号（国际格式，如 +8613800138000）
            proxy: 代理地址（可选）

        Returns:
            包含 phone_code_hash 的字典
        """
        import gc

        from pyrogram import Client
        from pyrogram.errors import FloodWait, PhoneNumberInvalid

        from tg_signer.core import close_client_by_name

        account_lock = get_account_lock(account_name)
        session_mode = get_session_mode()
        no_updates = get_no_updates_flag()
        global_semaphore = get_global_semaphore()

        # 1. 清理全局 _login_sessions 中可能存在的残留连接
        # _login_sessions key 格式: f"{account_name}_{phone_number}"
        keys_to_remove = []
        for key, value in _login_sessions.items():
            if key.startswith(f"{account_name}_"):
                old_client = value.get("client")
                old_lock = value.get("lock")
                if old_lock and old_lock.locked():
                    old_lock.release()
                if old_client:
                    try:
                        await old_client.disconnect()
                    except Exception:
                        pass
                keys_to_remove.append(key)

        for key in keys_to_remove:
            _login_sessions.pop(key, None)

        # 获取账号锁，避免与任务并发写 session
        await account_lock.acquire()

        def _release_account_lock() -> None:
            if account_lock.locked():
                account_lock.release()

        # 2. 确保没有后台任务占用
        try:
            await close_client_by_name(account_name, workdir=self.session_dir)
        except Exception as e:
            print(f"DEBUG: start_login 清理后台客户端失败: {e}")

        # 3. 强制垃圾回收，释放可能的未关闭文件句柄 (Windows 特性)
        gc.collect()

        # 获取 API credentials
        from backend.services.config import get_config_service

        config_service = get_config_service()
        tg_config = config_service.get_telegram_config()
        api_id = tg_config.get("api_id")
        api_hash = tg_config.get("api_hash")

        env_api_id = os.getenv("TG_API_ID") or None
        env_api_hash = os.getenv("TG_API_HASH") or None
        if env_api_id:
            api_id = env_api_id
        if env_api_hash:
            api_hash = env_api_hash

        try:
            api_id = int(api_id) if api_id is not None else None
        except (TypeError, ValueError):
            api_id = None

        if isinstance(api_hash, str):
            api_hash = api_hash.strip()

        if not api_id or not api_hash:
            _release_account_lock()
            raise ValueError("Telegram API ID / API Hash 未配置或无效")

        proxy_dict = build_proxy_dict(proxy) if proxy else None

        # 4. 如果是重新登录，尝试先清理旧的 session 文件 (避免 SQLite 锁或损坏)
        # 注意: 如果 session 有效但用户只是想重登，删除也没问题，因为反正要重新验证
        if session_mode == "file":
            session_file = self.session_dir / f"{account_name}.session"
            if session_file.exists():
                try:
                    # 尝试删除主文件
                    session_file.unlink()
                    # 顺便删掉 journal/wal/shm
                    for ext in [".session-journal", ".session-wal", ".session-shm"]:
                        aux_file = self.session_dir / f"{account_name}{ext}"
                        if aux_file.exists():
                            aux_file.unlink()
                except OSError as e:
                    # 如果删除失败，说明真的被锁得很死，或者权限问题
                    print(f"DEBUG: 删除旧 Session 文件失败: {e} - 可能文件仍被占用")
                    # 这里不抛出异常，尝试继续，也许 Pyrogram 能处理?
                    # 但通常 "unable to open database file" 就是因为这个。
                    pass

        session_path = str(self.session_dir / account_name)
        client_kwargs = {
            "name": session_path,
            "api_id": api_id,
            "api_hash": api_hash,
            "proxy": proxy_dict,
            "in_memory": session_mode == "string",
        }
        if session_mode == "string":
            client_kwargs["no_updates"] = no_updates
        client = Client(**client_kwargs)

        try:
            async with global_semaphore:
                await client.connect()

                self._accounts_cache = None

                if hasattr(client, "storage") and getattr(client.storage, "conn", None):
                    try:
                        client.storage.conn.execute("PRAGMA journal_mode=WAL")
                        client.storage.conn.execute("PRAGMA busy_timeout=30000")
                    except Exception:
                        pass

                sent_code = await client.send_code(phone_number)

            session_key = f"{account_name}_{phone_number}"
            _login_sessions[session_key] = {
                "client": client,
                "phone_code_hash": sent_code.phone_code_hash,
                "phone_number": phone_number,
                "lock": account_lock,
            }

            # 保持连接，避免 session 变化导致验证码失效 (PhoneCodeExpired)
            # 断开连接会导致服务端重新分配 Session ID，从而使之前的 hash 失效
            # try:
            #     await client.disconnect()
            # except Exception:
            #     pass

            return {
                "phone_code_hash": sent_code.phone_code_hash,
                "phone_number": phone_number,
                "account_name": account_name,
            }

        except PhoneNumberInvalid:
            try:
                await client.disconnect()
            except Exception:
                pass
            _release_account_lock()
            raise ValueError("手机号格式无效，请使用国际格式（如 +8613800138000）")
        except FloodWait as e:
            try:
                await client.disconnect()
            except Exception:
                pass
            _release_account_lock()
            raise ValueError(f"请求过于频繁，请等待 {e.value} 秒后重试")
        except Exception as e:
            import traceback

            traceback.print_exc()
            try:
                await client.disconnect()
            except Exception:
                pass
            _release_account_lock()

            error_details = str(e)
            if (
                "database is locked" in error_details
                or "unable to open database file" in error_details
            ):
                raise ValueError(
                    f"会话文件被占用，请稍后重试或重启程序。错误: {error_details}"
                )

            raise ValueError(f"发送验证码失败: {error_details}")

    async def verify_login(
        self,
        account_name: str,
        phone_number: str,
        phone_code: str,
        phone_code_hash: str,
        password: Optional[str] = None,
        proxy: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        验证登录（输入验证码和可选的2FA密码）

        Args:
            account_name: 账号名称
            phone_number: 手机号
            phone_code: 验证码
            phone_code_hash: 从 start_login 返回的 hash
            password: 2FA 密码（可选）
            proxy: 代理地址（可选）

        Returns:
            登录结果
        """
        from pyrogram.errors import (
            PasswordHashInvalid,
            PhoneCodeExpired,
            PhoneCodeInvalid,
            SessionPasswordNeeded,
        )

        # 尝试从全局字典获取之前的 client
        session_key = f"{account_name}_{phone_number}"
        session_data = _login_sessions.get(session_key)

        if not session_data:
            raise ValueError("登录会话已过期，请重新发送验证码")

        client = session_data["client"]
        session_mode = get_session_mode()
        global_semaphore = get_global_semaphore()

        account_lock = session_data.get("lock")

        def _release_account_lock() -> None:
            if account_lock and account_lock.locked():
                account_lock.release()

        async def _persist_session_string() -> None:
            if session_mode != "string":
                return
            session_string = await client.export_session_string()
            if not session_string:
                raise ValueError("导出 session_string 失败")
            set_account_session_string(account_name, session_string)
            save_session_string_file(self.session_dir, account_name, session_string)
            self._accounts_cache = None

        def _persist_proxy_setting() -> None:
            if proxy:
                from backend.utils.tg_session import set_account_profile

                set_account_profile(account_name, proxy=proxy)

        if account_lock and not account_lock.locked():
            await account_lock.acquire()

        try:
            async with global_semaphore:
                # 重新连接 (因为 start_login 中断开了)
                if not client.is_connected:
                    await client.connect()

                # 移除验证码中的空格和横线
                phone_code = phone_code.strip().replace(" ", "").replace("-", "")

                # 尝试使用验证码登录
                try:
                    await client.sign_in(phone_number, phone_code_hash, phone_code)

                    # 登录成功，获取用户信息
                    me = await client.get_me()
                    await _persist_session_string()
                    _persist_proxy_setting()

                    # 断开连接并清理
                    await client.disconnect()
                    _login_sessions.pop(session_key, None)
                    _release_account_lock()

                    return {
                        "success": True,
                        "user_id": me.id,
                        "first_name": me.first_name,
                        "username": me.username,
                    }

                except SessionPasswordNeeded:
                    # 需要 2FA 密码
                    if not password:
                        # 不断开连接，等待用户输入 2FA 密码
                        raise ValueError("此账号启用了两步验证，请输入 2FA 密码")

                    # 使用 2FA 密码登录
                    try:
                        await client.check_password(password)
                        me = await client.get_me()
                        await _persist_session_string()
                        _persist_proxy_setting()

                        # 断开连接并清理
                        await client.disconnect()
                        _login_sessions.pop(session_key, None)
                        _release_account_lock()

                        return {
                            "success": True,
                            "user_id": me.id,
                            "first_name": me.first_name,
                            "username": me.username,
                        }
                    except PasswordHashInvalid:
                        raise ValueError("2FA 密码错误")

        except PhoneCodeInvalid:
            # 清理 session
            try:
                await client.disconnect()
            except Exception:
                pass
            _login_sessions.pop(session_key, None)
            _release_account_lock()
            raise ValueError("验证码错误，请检查验证码是否正确")
        except PhoneCodeExpired:
            # 清理 session
            try:
                await client.disconnect()
            except Exception:
                pass
            _login_sessions.pop(session_key, None)
            _release_account_lock()
            raise ValueError("验证码已过期，请重新获取")
        except ValueError as e:
            # 如果是 2FA 错误，不清理 session
            if "两步验证" not in str(e):
                try:
                    await client.disconnect()
                except Exception:
                    pass
                _login_sessions.pop(session_key, None)
                _release_account_lock()
            raise e
        except Exception as e:
            # 清理 session
            try:
                await client.disconnect()
            except Exception:
                pass
            _login_sessions.pop(session_key, None)
            _release_account_lock()

            # 更详细的错误信息
            error_msg = str(e)
            if "PHONE_CODE_INVALID" in error_msg:
                raise ValueError("验证码错误，请检查验证码是否正确")
            elif "PHONE_CODE_EXPIRED" in error_msg:
                raise ValueError("验证码已过期，请重新获取")
            elif "SESSION_PASSWORD_NEEDED" in error_msg:
                raise ValueError("此账号启用了两步验证，请输入 2FA 密码")
            else:
                raise ValueError(f"登录失败: {error_msg}")

    async def _persist_client_session(
        self, client, account_name: str, proxy: Optional[str] = None
    ) -> None:
        session_mode = get_session_mode()
        if session_mode == "string":
            session_string = await client.export_session_string()
            if not session_string:
                raise ValueError("导出 session_string 失败")
            set_account_session_string(account_name, session_string)
            save_session_string_file(self.session_dir, account_name, session_string)
        if proxy:
            from backend.utils.tg_session import set_account_profile

            set_account_profile(account_name, proxy=proxy)
        self._accounts_cache = None

    async def _cleanup_qr_login(self, login_id: str) -> None:
        data = _qr_login_sessions.pop(login_id, None)
        if not data:
            return
        client = data.get("client")
        handler = data.get("handler")
        if client and handler:
            try:
                client.remove_handler(*handler)
            except Exception:
                pass
        if client:
            try:
                await client.dispatcher.stop(clear=False)
            except Exception:
                pass
            try:
                await client.disconnect()
            except Exception:
                pass
        lock = data.get("lock")
        if lock and lock.locked():
            lock.release()

    async def _expire_qr_login(self, login_id: str, expires_ts: int) -> None:
        wait_seconds = max(0, int(expires_ts - time.time()))
        if wait_seconds:
            await asyncio.sleep(wait_seconds)
        data = _qr_login_sessions.get(login_id)
        if not data:
            return
        data["status"] = "expired"
        await self._cleanup_qr_login(login_id)

    async def start_qr_login(
        self, account_name: str, proxy: Optional[str] = None
    ) -> Dict[str, Any]:
        import gc

        from pyrogram import Client, filters, handlers, raw
        from pyrogram.errors import FloodWait

        from tg_signer.core import close_client_by_name

        account_lock = get_account_lock(account_name)
        session_mode = get_session_mode()
        no_updates = get_no_updates_flag()
        global_semaphore = get_global_semaphore()

        # 清理同账号残留的扫码会话
        for key, value in list(_qr_login_sessions.items()):
            if value.get("account_name") == account_name:
                await self._cleanup_qr_login(key)

        await account_lock.acquire()

        def _release_account_lock() -> None:
            if account_lock.locked():
                account_lock.release()

        # 清理后台客户端
        try:
            await close_client_by_name(account_name, workdir=self.session_dir)
        except Exception:
            pass

        gc.collect()

        # API credentials
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
            _release_account_lock()
            raise ValueError("Telegram API ID / API Hash 未配置或无效")

        proxy_dict = build_proxy_dict(proxy) if proxy else None

        # 清理旧 session 文件（与手机号登录保持一致）
        if session_mode == "file":
            session_file = self.session_dir / f"{account_name}.session"
            if session_file.exists():
                try:
                    session_file.unlink()
                    for ext in [".session-journal", ".session-wal", ".session-shm"]:
                        aux_file = self.session_dir / f"{account_name}{ext}"
                        if aux_file.exists():
                            aux_file.unlink()
                except OSError:
                    pass

        session_path = str(self.session_dir / account_name)
        client_kwargs = {
            "name": session_path,
            "api_id": api_id,
            "api_hash": api_hash,
            "proxy": proxy_dict,
            "in_memory": session_mode == "string",
        }
        if session_mode == "string":
            client_kwargs["no_updates"] = no_updates
        client = Client(**client_kwargs)

        try:
            async with global_semaphore:
                await client.connect()

                if hasattr(client, "storage") and getattr(client.storage, "conn", None):
                    try:
                        client.storage.conn.execute("PRAGMA journal_mode=WAL")
                        client.storage.conn.execute("PRAGMA busy_timeout=30000")
                    except Exception:
                        pass

                result = await client.invoke(
                    raw.functions.auth.ExportLoginToken(
                        api_id=api_id, api_hash=api_hash, except_ids=[]
                    )
                )

            token_bytes = getattr(result, "token", None)
            if not token_bytes:
                raise ValueError("获取二维码 token 失败")

            token_expires = getattr(result, "expires", None)
            expires_ts = (
                int(token_expires)
                if token_expires
                else int(time.time()) + 300
            )
            expires_at = datetime.utcfromtimestamp(expires_ts).isoformat() + "Z"
            qr_uri = "tg://login?token=" + base64.urlsafe_b64encode(
                token_bytes
            ).decode("utf-8")

            login_id = secrets.token_urlsafe(16)

            session_data = {
                "account_name": account_name,
                "proxy": proxy,
                "client": client,
                "token": token_bytes,
                "expires_ts": expires_ts,
                "expires_at": expires_at,
                "status": "waiting_scan",
                "scan_seen": False,
                "lock": account_lock,
                "migrate_dc_id": getattr(result, "dc_id", None),
                "handler": None,
            }
            _qr_login_sessions[login_id] = session_data

            # 监听扫码更新
            try:
                def _filter(_, __, update):
                    return isinstance(update, raw.types.UpdateLoginToken)

                async def _raw_handler(_, __, ___, ____):
                    data = _qr_login_sessions.get(login_id)
                    if data and data.get("status") in ("waiting_scan", "scanned_wait_confirm"):
                        data["scan_seen"] = True
                        data["status"] = "scanned_wait_confirm"

                handler = client.add_handler(
                    handlers.RawUpdateHandler(
                        _raw_handler, filters=filters.create(_filter)
                    )
                )
                session_data["handler"] = handler
                await client.dispatcher.start()
            except Exception:
                pass

            asyncio.create_task(self._expire_qr_login(login_id, expires_ts))

            return {
                "login_id": login_id,
                "qr_uri": qr_uri,
                "expires_at": expires_at,
            }

        except FloodWait as e:
            try:
                await client.disconnect()
            except Exception:
                pass
            _release_account_lock()
            raise ValueError(f"请求过于频繁，请等待 {e.value} 秒后重试")
        except Exception as e:
            try:
                await client.disconnect()
            except Exception:
                pass
            _release_account_lock()
            raise ValueError(f"获取二维码失败: {str(e)}")

    async def get_qr_login_status(self, login_id: str) -> Dict[str, Any]:
        from pyrogram import raw, types
        from pyrogram.errors import FloodWait, Unauthorized
        from pyrogram.methods.messages.inline_session import get_session

        data = _qr_login_sessions.get(login_id)
        if not data:
            return {
                "status": "expired",
                "message": "二维码已过期或不存在",
            }

        if time.time() >= data.get("expires_ts", 0):
            await self._cleanup_qr_login(login_id)
            return {
                "status": "expired",
                "message": "二维码已过期",
            }

        client = data.get("client")
        token = data.get("token")
        migrate_dc_id = data.get("migrate_dc_id")

        try:
            if not client.is_connected:
                await client.connect()

            result = None
            # 尝试导入 token（处理 DC 迁移）
            for _ in range(2):
                if migrate_dc_id:
                    session = await get_session(client, migrate_dc_id)
                    result = await session.invoke(
                        raw.functions.auth.ImportLoginToken(token=token)
                    )
                else:
                    result = await client.invoke(
                        raw.functions.auth.ImportLoginToken(token=token)
                    )

                if isinstance(result, raw.types.auth.LoginTokenMigrateTo):
                    migrate_dc_id = result.dc_id
                    token = result.token
                    data["migrate_dc_id"] = migrate_dc_id
                    data["token"] = token
                    data["status"] = "scanned_wait_confirm"
                    continue
                break

            if isinstance(result, raw.types.auth.LoginTokenSuccess):
                # 标记授权用户
                user = types.User._parse(client, result.authorization.user)
                await client.storage.user_id(user.id)
                await client.storage.is_bot(False)

                # 获取用户信息并持久化会话
                try:
                    me = await client.get_me()
                except Exception:
                    me = user

                await self._persist_client_session(
                    client, data.get("account_name"), data.get("proxy")
                )

                try:
                    await client.disconnect()
                except Exception:
                    pass

                account_name = data.get("account_name")
                await self._cleanup_qr_login(login_id)

                account = None
                try:
                    accounts = self.list_accounts(force_refresh=True)
                    account = next(
                        (acc for acc in accounts if acc.get("name") == account_name),
                        None,
                    )
                except Exception:
                    account = None

                return {
                    "status": "success",
                    "message": "登录成功",
                    "account": account,
                    "user_id": me.id,
                    "first_name": me.first_name,
                    "username": me.username,
                }

            if isinstance(result, raw.types.auth.LoginToken):
                token_expires = getattr(result, "expires", None)
                if token_expires:
                    data["expires_ts"] = int(token_expires)
                    data["expires_at"] = datetime.utcfromtimestamp(
                        data["expires_ts"]
                    ).isoformat() + "Z"
                if data.get("token") != result.token:
                    data["status"] = "scanned_wait_confirm"
                data["token"] = result.token

            status = (
                "scanned_wait_confirm"
                if data.get("scan_seen")
                else data.get("status", "waiting_scan")
            )
            return {
                "status": status,
                "expires_at": data.get("expires_at"),
            }

        except FloodWait as e:
            await self._cleanup_qr_login(login_id)
            return {
                "status": "failed",
                "message": f"请求过于频繁，请等待 {e.value} 秒后重试",
            }
        except Unauthorized:
            await self._cleanup_qr_login(login_id)
            return {
                "status": "failed",
                "message": "登录失败，请重试",
            }
        except Exception:
            await self._cleanup_qr_login(login_id)
            return {
                "status": "failed",
                "message": "登录失败，请重试",
            }

    async def cancel_qr_login(self, login_id: str) -> bool:
        if login_id not in _qr_login_sessions:
            return False
        await self._cleanup_qr_login(login_id)
        return True

    def login_sync(
        self,
        account_name: str,
        phone_number: str,
        phone_code: Optional[str] = None,
        phone_code_hash: Optional[str] = None,
        password: Optional[str] = None,
        proxy: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        同步版本的登录方法（用于 FastAPI）

        如果只提供 phone_number，则发送验证码
        如果提供了 phone_code，则验证登录
        """

        try:
            if phone_code is None:
                # 发送验证码
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    result = loop.run_until_complete(
                        self.start_login(account_name, phone_number, proxy)
                    )
                finally:
                    loop.close()
            else:
                # 验证登录
                if not phone_code_hash:
                    raise ValueError("缺少 phone_code_hash")

                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    result = loop.run_until_complete(
                        self.verify_login(
                            account_name,
                            phone_number,
                            phone_code,
                            phone_code_hash,
                            password,
                            proxy,
                        )
                    )
                finally:
                    loop.close()

            return result
        except Exception as e:
            # 重新抛出异常，保留原始错误信息
            raise e


# 创建全局实例
_telegram_service: Optional[TelegramService] = None


def get_telegram_service() -> TelegramService:
    global _telegram_service
    if _telegram_service is None:
        _telegram_service = TelegramService()
    return _telegram_service
