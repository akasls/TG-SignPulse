from __future__ import annotations

import io
import time
from dataclasses import dataclass
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

import pyotp
from backend.core.auth import (
    create_access_token,
    get_current_user,
    get_current_user_optional,
    verify_totp,
)
from backend.core.config import get_settings
from backend.core.database import get_db
from backend.core.security import hash_password, verify_password
from backend.models.user import User
from jose import JWTError, jwt

try:
    import qrcode
except Exception:  # pragma: no cover - optional dependency fallback
    qrcode = None

router = APIRouter()

_FALLBACK_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc`\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)
from threading import Lock

_PENDING_TOTP_TTL_SECONDS = 10 * 60
_pending_totp_lock = Lock()


@dataclass
class PendingTOTPSecret:
    secret: str
    created_at: float


_pending_totp_secrets: dict[int, PendingTOTPSecret] = {}


def _cleanup_expired_pending_totp_secrets(now: Optional[float] = None) -> None:
    current = time.monotonic() if now is None else now
    with _pending_totp_lock:
        expired_user_ids = [
            user_id
            for user_id, entry in _pending_totp_secrets.items()
            if current - entry.created_at >= _PENDING_TOTP_TTL_SECONDS
        ]
        for user_id in expired_user_ids:
            _pending_totp_secrets.pop(user_id, None)


def _set_pending_totp_secret(user_id: int, secret: str) -> None:
    _cleanup_expired_pending_totp_secrets()
    with _pending_totp_lock:
        _pending_totp_secrets[user_id] = PendingTOTPSecret(
            secret=secret,
            created_at=time.monotonic(),
        )


def get_pending_totp_secret(user_id: int) -> Optional[str]:
    _cleanup_expired_pending_totp_secrets()
    with _pending_totp_lock:
        entry = _pending_totp_secrets.get(user_id)
        if entry is None:
            return None
        return entry.secret


def clear_pending_totp_secret(user_id: int) -> None:
    with _pending_totp_lock:
        _pending_totp_secrets.pop(user_id, None)


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class ChangePasswordResponse(BaseModel):
    success: bool
    message: str


class ChangeUsernameRequest(BaseModel):
    new_username: str
    password: str


class ChangeUsernameResponse(BaseModel):
    success: bool
    message: str
    access_token: Optional[str] = None


class EnableTOTPRequest(BaseModel):
    totp_code: str


class EnableTOTPResponse(BaseModel):
    success: bool
    message: str


class DisableTOTPRequest(BaseModel):
    totp_code: str


class DisableTOTPResponse(BaseModel):
    success: bool
    message: str


class TOTPStatusResponse(BaseModel):
    enabled: bool
    secret: Optional[str] = None


@router.put("/password", response_model=ChangePasswordResponse)
def change_password(
    request: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(request.old_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="旧密码错误",
        )

    if len(request.new_password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="新密码长度至少为 6 个字符",
        )

    current_user.password_hash = hash_password(request.new_password)
    db.commit()

    return ChangePasswordResponse(success=True, message="密码修改成功")


@router.put("/username", response_model=ChangeUsernameResponse)
def change_username(
    request: ChangeUsernameRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(request.password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="密码错误",
        )

    new_username = request.new_username.strip()
    if len(new_username) < 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名长度至少为 3 个字符",
        )
    if len(new_username) > 50:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名长度最多为 50 个字符",
        )

    existing_user = db.query(User).filter(User.username == new_username).first()
    if existing_user and existing_user.id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该用户名已被使用",
        )

    current_user.username = new_username
    db.commit()

    new_token = create_access_token(data={"sub": new_username})
    return ChangeUsernameResponse(
        success=True,
        message="用户名修改成功",
        access_token=new_token,
    )


@router.get("/totp/status", response_model=TOTPStatusResponse)
def get_totp_status(current_user: User = Depends(get_current_user)):
    return TOTPStatusResponse(
        enabled=bool(current_user.totp_secret),
        secret=None,
    )


@router.post("/totp/setup", response_model=TOTPStatusResponse)
def setup_totp(current_user: User = Depends(get_current_user)):
    if current_user.totp_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA 已启用，如需重新设置请先禁用",
        )

    secret = pyotp.random_base32()
    _set_pending_totp_secret(current_user.id, secret)
    return TOTPStatusResponse(enabled=False, secret=secret)


@router.get("/totp/qrcode")
def get_totp_qrcode(
    token: Optional[str] = None,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    settings = get_settings()

    if current_user is None and token:
        try:
            payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
            username = payload.get("sub")
            if username:
                current_user = db.query(User).filter(User.username == username).first()
        except JWTError:
            current_user = None

    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="认证失败",
        )

    secret = get_pending_totp_secret(current_user.id) or current_user.totp_secret
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请先调用 /totp/setup 设置 2FA",
        )

    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(name=current_user.username, issuer_name="tg-signer")

    if qrcode is None:
        img_io = io.BytesIO(_FALLBACK_PNG)
    else:
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(uri)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        img_io = io.BytesIO()
        img.save(img_io, "PNG")
        img_io.seek(0)

    return StreamingResponse(img_io, media_type="image/png")


@router.post("/totp/enable", response_model=EnableTOTPResponse)
def enable_totp(
    request: EnableTOTPRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    pending_secret = get_pending_totp_secret(current_user.id)
    if not pending_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA 设置已过期，请重新执行 setup",
        )

    if not verify_totp(pending_secret, request.totp_code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="验证码错误",
        )

    current_user.totp_secret = pending_secret
    db.commit()
    clear_pending_totp_secret(current_user.id)

    return EnableTOTPResponse(success=True, message="两步验证已启用")


@router.post("/totp/cancel", response_model=DisableTOTPResponse)
def cancel_totp_setup(current_user: User = Depends(get_current_user)):
    clear_pending_totp_secret(current_user.id)
    return DisableTOTPResponse(success=True, message="2FA 设置已取消")


@router.post("/totp/disable", response_model=DisableTOTPResponse)
def disable_totp(
    request: DisableTOTPRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not current_user.totp_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA 未启用",
        )

    if not verify_totp(current_user.totp_secret, request.totp_code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="验证码错误",
        )

    current_user.totp_secret = None
    db.commit()
    clear_pending_totp_secret(current_user.id)

class ResetUserTOTPRequest(BaseModel):
    password: str


@router.post("/totp/reset", response_model=DisableTOTPResponse)
def reset_totp(
    request: ResetUserTOTPRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(request.password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="密码错误",
        )
    current_user.totp_secret = None
    db.commit()
    clear_pending_totp_secret(current_user.id)
    return DisableTOTPResponse(success=True, message="两步验证已重置")
