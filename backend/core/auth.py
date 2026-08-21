from __future__ import annotations

import os
from datetime import timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

import pyotp
from backend.core.config import get_settings
from backend.core.database import get_db
from backend.core.security import verify_password
from backend.models.user import User
from backend.utils.time import utc_now
from jose import JWTError, jwt

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

settings = get_settings()


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = utc_now() + (
        expires_delta or timedelta(hours=settings.access_token_expire_hours)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.secret_key, algorithm="HS256")


def verify_totp(secret: str, code: str) -> bool:
    try:
        if not isinstance(code, str):
            return False
        code = code.strip().replace(" ", "")
        if not code:
            return False
        totp = pyotp.TOTP(secret)
        raw_window = os.getenv("APP_TOTP_VALID_WINDOW")
        raw_window = raw_window.strip() if isinstance(raw_window, str) else ""
        try:
            valid_window = int(raw_window) if raw_window else 1
        except ValueError:
            valid_window = 1
        if valid_window < 0:
            valid_window = 0
        return totp.verify(code, valid_window=valid_window)
    except Exception:
        return False


_DUMMY_BCRYPT_HASH = "$2b$12$e8uq5eGqK.G2qFjX7eA7.OF5c9G5g6s8D7.yZ9u7b.F9i.wK9.e2a"


def authenticate_user(db: Session, username: str, password: str) -> Optional[User]:
    user = db.query(User).filter(User.username == username).first()
    if not user:
        # Perform constant-time computation to prevent timing attacks on username enumeration
        verify_password(password, _DUMMY_BCRYPT_HASH)
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        username: str = payload.get("sub")  # type: ignore[assignment]
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception
    return user


# OAuth2 scheme that doesn't auto-error on missing token
oauth2_scheme_optional = OAuth2PasswordBearer(
    tokenUrl="/api/auth/login", auto_error=False
)


def get_current_user_optional(
    token: Optional[str] = Depends(oauth2_scheme_optional),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """获取当前用户，如果无法认证则返回 None（不抛出异常）"""
    if not token:
        return None
    return verify_token(token, db)


def verify_token(token: str, db: Session) -> Optional[User]:
    """验证 Token 并返回用户对象"""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        username: str = payload.get("sub")  # type: ignore[assignment]
        if username is None:
            return None
    except JWTError:
        return None
    user = db.query(User).filter(User.username == username).first()
    return user
