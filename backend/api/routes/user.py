"""
用户设置 API 路由
提供修改密码、2FA 设置等功能
"""
from __future__ import annotations

import io
from typing import Optional

import pyotp
import qrcode
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core.auth import get_current_user, get_current_user_optional
from backend.core.database import get_db
from backend.core.security import hash_password, verify_password
from backend.models.user import User

router = APIRouter()


# ============ Schemas ============

class ChangePasswordRequest(BaseModel):
    """修改密码请求"""
    old_password: str
    new_password: str


class ChangePasswordResponse(BaseModel):
    """修改密码响应"""
    success: bool
    message: str


class ChangeUsernameRequest(BaseModel):
    """修改用户名请求"""
    new_username: str
    password: str  # 需要密码确认


class ChangeUsernameResponse(BaseModel):
    """修改用户名响应"""
    success: bool
    message: str
    access_token: Optional[str] = None


class EnableTOTPRequest(BaseModel):
    """启用2FA请求"""
    totp_code: str  # 用户输入的验证码，用于验证


class EnableTOTPResponse(BaseModel):
    """启用2FA响应"""
    success: bool
    message: str


class DisableTOTPRequest(BaseModel):
    """禁用2FA请求"""
    totp_code: str  # 需要验证码确认


class DisableTOTPResponse(BaseModel):
    """禁用2FA响应"""
    success: bool
    message: str


class TOTPStatusResponse(BaseModel):
    """2FA状态响应"""
    enabled: bool
    secret: Optional[str] = None  # 只在首次设置时返回


# ============ API Routes ============

@router.put("/password", response_model=ChangePasswordResponse)
def change_password(
    request: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    修改密码
    
    需要提供旧密码进行验证
    """
    # 验证旧密码
    if not verify_password(request.old_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="旧密码错误"
        )
    
    # 验证新密码
    if len(request.new_password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="新密码长度至少为 6 个字符"
        )
    
    # 更新密码
    current_user.password_hash = hash_password(request.new_password)
    db.commit()
    
    return ChangePasswordResponse(
        success=True,
        message="密码修改成功"
    )


@router.put("/username", response_model=ChangeUsernameResponse)
def change_username(
    request: ChangeUsernameRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    修改用户名
    
    需要提供密码进行验证
    """
    # 验证密码
    if not verify_password(request.password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="密码错误"
        )
    
    # 验证新用户名
    new_username = request.new_username.strip()
    if len(new_username) < 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名长度至少为 3 个字符"
        )
    
    if len(new_username) > 50:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名长度最多为 50 个字符"
        )
    
    # 检查用户名是否已存在
    existing_user = db.query(User).filter(User.username == new_username).first()
    if existing_user and existing_user.id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该用户名已被使用"
        )
    
    # 更新用户名
    current_user.username = new_username
    db.commit()
    
    # 生成新 Token，因为原来的 Token 基于旧用户名
    from backend.core.auth import create_access_token
    new_token = create_access_token(data={"sub": new_username})
    
    return ChangeUsernameResponse(
        success=True,
        message="用户名修改成功",
        access_token=new_token
    )


@router.get("/totp/status", response_model=TOTPStatusResponse)
def get_totp_status(current_user: User = Depends(get_current_user)):
    """
    获取2FA状态
    """
    return TOTPStatusResponse(
        enabled=bool(current_user.totp_secret),
        secret=None  # 不返回 secret
    )


# 临时存储待验证的 TOTP secrets (用户ID -> secret)
# 注意：在生产环境中应该使用 Redis 或其他持久化缓存
_pending_totp_secrets: dict[int, str] = {}


@router.post("/totp/setup", response_model=TOTPStatusResponse)
def setup_totp(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    设置2FA（生成密钥）
    
    返回 secret，用户需要用此 secret 生成二维码
    注意：此时 TOTP 尚未启用，需要调用 /totp/enable 验证后才会启用
    """
    if current_user.totp_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA 已启用，如需重新设置请先禁用"
        )
    
    # 生成新的 TOTP secret
    secret = pyotp.random_base32()
    
    # 暂存到内存缓存（不保存到数据库），等待用户验证
    _pending_totp_secrets[current_user.id] = secret
    
    return TOTPStatusResponse(
        enabled=False,
        secret=secret
    )


@router.get("/totp/qrcode")
def get_totp_qrcode(
    token: Optional[str] = None,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """
    获取2FA二维码
    
    返回二维码图片（PNG 格式）
    支持通过 query parameter 传递 token（用于 img src）
    """
    from jose import jwt, JWTError
    from backend.core.config import get_settings
    
    settings = get_settings()
    
    # 如果没有通过 header 获取用户，尝试从 query param 获取
    if current_user is None and token:
        try:
            payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
            username: str = payload.get("sub")
            if username:
                current_user = db.query(User).filter(User.username == username).first()
        except JWTError:
            pass
    
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="认证失败"
        )
    
    # 优先使用待验证的 secret，否则使用已启用的 secret
    secret = _pending_totp_secrets.get(current_user.id) or current_user.totp_secret
    
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请先调用 /totp/setup 设置2FA"
        )
    
    # 生成 TOTP URI
    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(
        name=current_user.username,
        issuer_name="tg-signer"
    )
    
    # 生成二维码
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(uri)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    # 转换为字节流
    img_io = io.BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)
    
    return StreamingResponse(img_io, media_type="image/png")


@router.post("/totp/enable", response_model=EnableTOTPResponse)
def enable_totp(
    request: EnableTOTPRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    启用2FA
    
    需要提供验证码以确认设置正确
    """
    # 获取待验证的 secret
    pending_secret = _pending_totp_secrets.get(current_user.id)
    
    if not pending_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请先调用 /totp/setup 设置2FA"
        )
    
    # 验证 TOTP 码
    totp = pyotp.TOTP(pending_secret)
    if not totp.verify(request.totp_code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="验证码错误"
        )
    
    # 验证通过，将 secret 保存到数据库
    current_user.totp_secret = pending_secret
    db.commit()
    
    # 清除临时缓存
    del _pending_totp_secrets[current_user.id]
    
    return EnableTOTPResponse(
        success=True,
        message="两步验证已启用"
    )


@router.post("/totp/cancel", response_model=DisableTOTPResponse)
def cancel_totp_setup(current_user: User = Depends(get_current_user)):
    """
    取消 TOTP 设置
    
    如果用户在 setup 后不想继续，可以调用此接口取消
    """
    if current_user.id in _pending_totp_secrets:
        del _pending_totp_secrets[current_user.id]
    
    return DisableTOTPResponse(
        success=True,
        message="2FA 设置已取消"
    )


@router.post("/totp/disable", response_model=DisableTOTPResponse)
def disable_totp(
    request: DisableTOTPRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    禁用2FA
    
    需要提供验证码以确认
    """
    if not current_user.totp_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA 未启用"
        )
    
    # 验证 TOTP 码
    totp = pyotp.TOTP(current_user.totp_secret)
    if not totp.verify(request.totp_code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="验证码错误"
        )
    
    # 禁用2FA
    current_user.totp_secret = None
    db.commit()
    
    return DisableTOTPResponse(
        success=True,
        message="两步验证已禁用"
    )


@router.post("/totp/reset", response_model=DisableTOTPResponse)
def reset_totp(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    强制重置 TOTP（不需要验证码）
    
    用于解决用户无法登录的问题
    注意：此接口只有在用户已登录时才能调用
    """
    # 清除数据库中的 TOTP secret
    current_user.totp_secret = None
    db.commit()
    
    # 清除待验证的 secret
    if current_user.id in _pending_totp_secrets:
        del _pending_totp_secrets[current_user.id]
    
    return DisableTOTPResponse(
        success=True,
        message="两步验证已重置"
    )
