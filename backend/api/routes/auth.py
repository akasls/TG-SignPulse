from __future__ import annotations

import logging
import os
import secrets
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core import auth as auth_core
from backend.core.auth import authenticate_user, create_access_token, verify_totp
from backend.core.database import get_db
from backend.core.rate_limit import compose_rate_limit_key, get_rate_limiter
from backend.core.security import verify_password
from backend.models.login_log import LoginLog
from backend.models.user import User
from backend.schemas.auth import LoginRequest, TokenResponse, UserOut

router = APIRouter()
logger = logging.getLogger("backend.auth")
rate_limiter = get_rate_limiter()

LOGIN_RATE_LIMIT_DETAIL = "Too many login attempts. Please try again later."
RESET_TOTP_RATE_LIMIT_DETAIL = (
    "Too many TOTP reset attempts. Please try again later."
)


def _resolve_request_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        first_hop = forwarded_for.split(",", 1)[0].strip()
        if first_hop:
            return first_hop

    real_ip = request.headers.get("x-real-ip", "").strip()
    if real_ip:
        return real_ip

    if request.client and request.client.host:
        return request.client.host
    return ""


def _append_login_log(
    db: Session,
    *,
    username: str,
    request: Request,
    success: bool,
    detail: str,
) -> None:
    try:
        db.add(
            LoginLog(
                username=(username or "").strip() or "unknown",
                ip_address=_resolve_request_ip(request) or None,
                user_agent=(request.headers.get("user-agent", "") or "").strip()[:255] or None,
                detail=(detail or "").strip()[:255] or None,
                success=success,
            )
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning("Failed to persist login log: %s", exc)


class ResetTOTPRequest(BaseModel):
    """重置 TOTP 请求"""

    username: str
    password: str
    emergency_key: Optional[str] = None


class ResetTOTPResponse(BaseModel):
    """重置 TOTP 响应"""

    success: bool
    message: str


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    login_key = compose_rate_limit_key(request, payload.username)
    try:
        rate_limiter.hit(
            scope="auth.login",
            key=login_key,
            max_attempts=5,
            window_seconds=300,
            block_seconds=900,
            detail=LOGIN_RATE_LIMIT_DETAIL,
        )
    except HTTPException:
        _append_login_log(
            db,
            username=payload.username,
            request=request,
            success=False,
            detail="RATE_LIMITED",
        )
        raise
    user = authenticate_user(db, payload.username, payload.password)
    if not user:
        _append_login_log(
            db,
            username=payload.username,
            request=request,
            success=False,
            detail="INVALID_USERNAME_OR_PASSWORD",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    if user.totp_secret:
        if not payload.totp_code or not verify_totp(
            user.totp_secret, payload.totp_code
        ):
            _append_login_log(
                db,
                username=user.username,
                request=request,
                success=False,
                detail="TOTP_REQUIRED_OR_INVALID",
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="TOTP_REQUIRED_OR_INVALID",
            )
    rate_limiter.reset("auth.login", login_key)
    access_token = create_access_token(
        data={"sub": user.username},
    )
    try:
        from backend.services.config import get_config_service
        from backend.services.push_notifications import send_login_notification

        ip_address = _resolve_request_ip(request)
        config_settings = get_config_service().get_global_settings()
        background_tasks.add_task(
            send_login_notification,
            config_settings,
            username=user.username,
            ip_address=ip_address,
        )
    except Exception as exc:
        logger.warning("Failed to queue login notification: %s", exc)
    _append_login_log(
        db,
        username=user.username,
        request=request,
        success=True,
        detail="LOGIN_SUCCESS",
    )
    return TokenResponse(access_token=access_token)


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(auth_core.get_current_user)):
    return current_user


@router.post("/reset-totp", response_model=ResetTOTPResponse)
def reset_totp(
    request: ResetTOTPRequest,
    http_request: Request,
    db: Session = Depends(get_db),
):
    """
    应急重置 TOTP 两步验证。
    为了保障双因素认证安全，必须提供正确的密码以及服务端配置的应急密钥 APP_EMERGENCY_RESET_KEY。
    若未配置应急密钥，请在服务器终端使用命令行工具重置：python -m backend.cli reset-totp <username>
    """
    reset_key = compose_rate_limit_key(http_request, request.username)
    rate_limiter.hit(
        scope="auth.reset_totp",
        key=reset_key,
        max_attempts=5,
        window_seconds=600,
        block_seconds=1800,
        detail=RESET_TOTP_RATE_LIMIT_DETAIL,
    )

    configured_emergency_key = (os.getenv("APP_EMERGENCY_RESET_KEY") or "").strip()
    if not configured_emergency_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="出于安全考虑，未配置 APP_EMERGENCY_RESET_KEY 时禁止通过 API 重置两步验证。请登录服务器终端执行 CLI 命令: python -m backend.cli reset-totp <username>",
        )

    provided_emergency_key = (request.emergency_key or "").strip()
    if not provided_emergency_key or not secrets.compare_digest(
        provided_emergency_key, configured_emergency_key
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="应急重置密钥无效",
        )

    user = db.query(User).filter(User.username == request.username).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误"
        )

    if not verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误"
        )

    had_totp_enabled = bool(user.totp_secret)
    user.totp_secret = None
    db.commit()
    try:
        from backend.api.routes.user import clear_pending_totp_secret

        clear_pending_totp_secret(user.id)
    except Exception:
        pass
    rate_limiter.reset("auth.reset_totp", reset_key)

    if not had_totp_enabled:
        return ResetTOTPResponse(
            success=True,
            message="该用户未启用两步验证，待确认设置已清理",
        )

    return ResetTOTPResponse(success=True, message="两步验证已安全重置，现在可以正常登录")
