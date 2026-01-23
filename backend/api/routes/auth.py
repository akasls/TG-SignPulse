from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core import auth as auth_core
from backend.core.auth import authenticate_user, create_access_token, verify_totp
from backend.core.database import get_db
from backend.core.security import verify_password
from backend.models.user import User
from backend.schemas.auth import LoginRequest, TokenResponse, UserOut

router = APIRouter()


class ResetTOTPRequest(BaseModel):
    """重置 TOTP 请求（通过密码验证）"""

    username: str
    password: str


class ResetTOTPResponse(BaseModel):
    """重置 TOTP 响应"""

    success: bool
    message: str


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    print(f"[DEBUG] Login attempt for user: {payload.username}")
    user = authenticate_user(db, payload.username, payload.password)
    if not user:
        print(f"[DEBUG] Authentication failed for user: {payload.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    print(f"[DEBUG] User authenticated: {user.username}, TOTP Secret: {bool(user.totp_secret)}")
    if user.totp_secret:
        if not payload.totp_code or not verify_totp(
            user.totp_secret, payload.totp_code
        ):
            print(f"[DEBUG] TOTP verification failed for user: {user.username}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="TOTP_REQUIRED_OR_INVALID",
            )
    access_token = create_access_token(
        data={"sub": user.username},
        expires_delta=timedelta(hours=12),
    )
    return TokenResponse(access_token=access_token)


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(auth_core.get_current_user)):
    return current_user


@router.post("/reset-totp", response_model=ResetTOTPResponse)
def reset_totp(request: ResetTOTPRequest, db: Session = Depends(get_db)):
    """
    强制重置 TOTP（不需要 TOTP 验证码，只需要密码）

    用于解决用户启用了 TOTP 但无法登录的问题。
    需要提供正确的用户名和密码。
    """
    # 验证用户名和密码
    user = db.query(User).filter(User.username == request.username).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误"
        )

    if not verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误"
        )

    # 如果没有启用 TOTP，提示无需重置
    if not user.totp_secret:
        return ResetTOTPResponse(success=True, message="该用户未启用两步验证，无需重置")

    # 清除 TOTP secret
    user.totp_secret = None
    db.commit()

    return ResetTOTPResponse(success=True, message="两步验证已重置，现在可以正常登录")
