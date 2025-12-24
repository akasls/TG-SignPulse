"""
Telegram 服务层
提供 Telegram 账号管理和操作的核心功能
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Dict, List, Optional

from backend.core.config import get_settings

settings = get_settings()

# 全局存储临时的登录 session
_login_sessions = {}


class TelegramService:
    """Telegram 服务类"""

    def __init__(self):
        self.session_dir = settings.resolve_session_dir()
        self.session_dir.mkdir(parents=True, exist_ok=True)

    def list_accounts(self) -> List[Dict[str, any]]:
        """
        获取所有账号列表（基于 session 文件）
        
        Returns:
            账号列表，每个账号包含：
            - name: 账号名称
            - session_file: session 文件路径
            - exists: session 文件是否存在
            - size: 文件大小（字节）
        """
        accounts = []
        
        # 扫描 session 目录
        for session_file in self.session_dir.glob("*.session"):
            account_name = session_file.stem  # 文件名（不含扩展名）
            
            accounts.append({
                "name": account_name,
                "session_file": str(session_file),
                "exists": session_file.exists(),
                "size": session_file.stat().st_size if session_file.exists() else 0,
            })
        
        return sorted(accounts, key=lambda x: x["name"])

    def account_exists(self, account_name: str) -> bool:
        """检查账号是否存在"""
        session_file = self.session_dir / f"{account_name}.session"
        return session_file.exists()

    def delete_account(self, account_name: str) -> bool:
        """
        删除账号（删除 session 文件）
        
        Args:
            account_name: 账号名称
            
        Returns:
            是否成功删除
        """
        session_file = self.session_dir / f"{account_name}.session"
        
        if not session_file.exists():
            return False
        
        try:
            session_file.unlink()
            
            # 同时删除可能存在的 .session-journal 文件
            journal_file = self.session_dir / f"{account_name}.session-journal"
            if journal_file.exists():
                journal_file.unlink()
            
            return True
        except OSError:
            return False

    async def start_login(
        self,
        account_name: str,
        phone_number: str,
        proxy: Optional[str] = None
    ) -> Dict[str, any]:
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
        from pyrogram.errors import PhoneNumberInvalid, FloodWait
        
        # 从环境变量获取 API credentials
        # 如果未设置，使用默认的公共 API 凭证
        api_id = os.getenv("TG_API_ID", "611335")
        api_hash = os.getenv("TG_API_HASH", "d524b414d21f4d37f08684c1df41ac9c")
        
        # 解析代理
        proxy_dict = None
        if proxy:
            # 格式: socks5://127.0.0.1:1080
            from urllib.parse import urlparse
            parsed = urlparse(proxy)
            proxy_dict = {
                "scheme": parsed.scheme,
                "hostname": parsed.hostname,
                "port": parsed.port,
            }
        
        # 创建客户端
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
            
            # 发送验证码
            sent_code = await client.send_code(phone_number)
            
            # 保存 client 到全局字典，不要断开连接
            session_key = f"{account_name}_{phone_number}"
            _login_sessions[session_key] = {
                "client": client,
                "phone_code_hash": sent_code.phone_code_hash,
                "phone_number": phone_number,
            }
            
            return {
                "phone_code_hash": sent_code.phone_code_hash,
                "phone_number": phone_number,
                "account_name": account_name,
            }
            
        except PhoneNumberInvalid:
            await client.disconnect()
            raise ValueError("手机号格式无效，请使用国际格式（如 +8613800138000）")
        except FloodWait as e:
            await client.disconnect()
            raise ValueError(f"请求过于频繁，请等待 {e.value} 秒后重试")
        except Exception as e:
            await client.disconnect()
            raise ValueError(f"发送验证码失败: {str(e)}")

    async def verify_login(
        self,
        account_name: str,
        phone_number: str,
        phone_code: str,
        phone_code_hash: str,
        password: Optional[str] = None,
        proxy: Optional[str] = None
    ) -> Dict[str, any]:
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
            PhoneCodeInvalid,
            PhoneCodeExpired,
            SessionPasswordNeeded,
            PasswordHashInvalid,
        )
        
        # 尝试从全局字典获取之前的 client
        session_key = f"{account_name}_{phone_number}"
        session_data = _login_sessions.get(session_key)
        
        if not session_data:
            raise ValueError("登录会话已过期，请重新发送验证码")
        
        client = session_data["client"]
        
        try:
            # 移除验证码中的空格和横线
            phone_code = phone_code.strip().replace(" ", "").replace("-", "")
            
            # 尝试使用验证码登录
            try:
                signed_in = await client.sign_in(
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
            except:
                pass
            _login_sessions.pop(session_key, None)
            raise ValueError("验证码错误，请检查验证码是否正确")
        except PhoneCodeExpired:
            # 清理 session
            try:
                await client.disconnect()
            except:
                pass
            _login_sessions.pop(session_key, None)
            raise ValueError("验证码已过期，请重新获取")
        except ValueError as e:
            # 如果是 2FA 错误，不清理 session
            if "两步验证" not in str(e):
                try:
                    await client.disconnect()
                except:
                    pass
                _login_sessions.pop(session_key, None)
            raise e
        except Exception as e:
            # 清理 session
            try:
                await client.disconnect()
            except:
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
    ) -> Dict[str, any]:
        """
        同步版本的登录方法（用于 FastAPI）
        
        如果只提供 phone_number，则发送验证码
        如果提供了 phone_code，则验证登录
        """
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            if phone_code is None:
                # 发送验证码
                result = loop.run_until_complete(
                    self.start_login(account_name, phone_number, proxy)
                )
            else:
                # 验证登录
                if not phone_code_hash:
                    raise ValueError("缺少 phone_code_hash")
                
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
            
            return result
        finally:
            loop.close()


# 创建全局实例
telegram_service = TelegramService()
