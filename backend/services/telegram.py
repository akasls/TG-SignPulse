"""
Telegram 服务层
提供 Telegram 账号管理和操作的核心功能
"""
from __future__ import annotations

import asyncio
import os
from typing import Any, Dict, List, Optional

from backend.core.config import get_settings

settings = get_settings()

# 全局存储临时的登录 session
_login_sessions = {}


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
            for session_file in self.session_dir.glob("*.session"):
                account_name = session_file.stem  # 文件名（不含扩展名）

                accounts.append({
                    "name": account_name,
                    "session_file": str(session_file),
                    "exists": session_file.exists(),
                    "size": session_file.stat().st_size if session_file.exists() else 0,
                })

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

        if not session_file.exists():
            return False

        try:
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

            # 更新缓存
            if self._accounts_cache is not None:
                self._accounts_cache = [acc for acc in self._accounts_cache if acc["name"] != account_name]

            return True
        except OSError:
            return False

    async def start_login(
        self,
        account_name: str,
        phone_number: str,
        proxy: Optional[str] = None
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
        from pyrogram import Client
        from pyrogram.errors import FloodWait, PhoneNumberInvalid
        from tg_signer.core import close_client_by_name
        import gc

        # 1. 清理全局 _login_sessions 中可能存在的残留连接
        # _login_sessions key 格式: f"{account_name}_{phone_number}"
        keys_to_remove = []
        for key, value in _login_sessions.items():
            if key.startswith(f"{account_name}_"):
                old_client = value.get("client")
                if old_client:
                    try:
                        await old_client.disconnect()
                    except Exception:
                        pass
                keys_to_remove.append(key)
        
        for key in keys_to_remove:
            _login_sessions.pop(key, None)

        # 2. 确保没有后台任务占用
        try:
            await close_client_by_name(account_name, workdir=self.session_dir)
        except Exception as e:
            print(f"DEBUG: start_login 清理后台客户端失败: {e}")

        # 3. 强制垃圾回收，释放可能的未关闭文件句柄 (Windows 特性)
        gc.collect()

        # 获取 API credentials
        from backend.services.config import config_service
        tg_config = config_service.get_telegram_config()
        api_id = tg_config.get("api_id")
        api_hash = tg_config.get("api_hash")

        if os.getenv("TG_API_ID"):
            api_id = os.getenv("TG_API_ID")
        if os.getenv("TG_API_HASH"):
            api_hash = os.getenv("TG_API_HASH")

        proxy_dict = None
        if proxy:
            from urllib.parse import urlparse
            parsed = urlparse(proxy)
            proxy_dict = {
                "scheme": parsed.scheme,
                "hostname": parsed.hostname,
                "port": parsed.port,
            }

        # 4. 如果是重新登录，尝试先清理旧的 session 文件 (避免 SQLite 锁或损坏)
        # 注意: 如果 session 有效但用户只是想重登，删除也没问题，因为反正要重新验证
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
        client = Client(
            name=session_path,
            api_id=int(api_id),
            api_hash=api_hash,
            proxy=proxy_dict,
            in_memory=False,
        )

        try:
            await client.connect()
            
            self._accounts_cache = None

            sent_code = await client.send_code(phone_number)

            session_key = f"{account_name}_{phone_number}"
            _login_sessions[session_key] = {
                "client": client,
                "phone_code_hash": sent_code.phone_code_hash,
                "phone_number": phone_number,
            }

            # 断开连接，避免长时间占用数据库锁
            try:
                await client.disconnect()
            except Exception:
                pass

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
            raise ValueError("手机号格式无效，请使用国际格式（如 +8613800138000）")
        except FloodWait as e:
            try:
                await client.disconnect()
            except Exception:
                pass
            raise ValueError(f"请求过于频繁，请等待 {e.value} 秒后重试")
        except Exception as e:
            import traceback
            traceback.print_exc()
            try:
                await client.disconnect()
            except Exception:
                pass
            
            error_details = str(e)
            if "database is locked" in error_details or "unable to open database file" in error_details:
                raise ValueError(f"会话文件被占用，请稍后重试或重启程序。错误: {error_details}")
            
            raise ValueError(f"发送验证码失败: {error_details}")

    async def verify_login(
        self,
        account_name: str,
        phone_number: str,
        phone_code: str,
        phone_code_hash: str,
        password: Optional[str] = None,
        proxy: Optional[str] = None
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

        try:
            # 重新连接 (因为 start_login 中断开了)
            if not client.is_connected:
                await client.connect()

            # 移除验证码中的空格和横线
            phone_code = phone_code.strip().replace(" ", "").replace("-", "")

            # 尝试使用验证码登录
            try:
                await client.sign_in(
                    phone_number,
                    phone_code_hash,
                    phone_code
                )

                # 登录成功，获取用户信息
                me = await client.get_me()

                # 断开连接并清理
                await client.disconnect()
                _login_sessions.pop(session_key, None)

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

                    # 断开连接并清理
                    await client.disconnect()
                    _login_sessions.pop(session_key, None)

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
            raise ValueError("验证码错误，请检查验证码是否正确")
        except PhoneCodeExpired:
            # 清理 session
            try:
                await client.disconnect()
            except Exception:
                pass
            _login_sessions.pop(session_key, None)
            raise ValueError("验证码已过期，请重新获取")
        except ValueError as e:
            # 如果是 2FA 错误，不清理 session
            if "两步验证" not in str(e):
                try:
                    await client.disconnect()
                except Exception:
                    pass
                _login_sessions.pop(session_key, None)
            raise e
        except Exception as e:
            # 清理 session
            try:
                await client.disconnect()
            except Exception:
                pass
            _login_sessions.pop(session_key, None)

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

    def login_sync(
        self,
        account_name: str,
        phone_number: str,
        phone_code: Optional[str] = None,
        phone_code_hash: Optional[str] = None,
        password: Optional[str] = None,
        proxy: Optional[str] = None
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
                            proxy
                        )
                    )
                finally:
                    loop.close()

            return result
        except Exception as e:
            # 重新抛出异常，保留原始错误信息
            raise e


# 创建全局实例
telegram_service = TelegramService()
