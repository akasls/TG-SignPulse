from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.core import auth as auth_core
from backend.core.auth import authenticate_user, create_access_token, verify_totp
from backend.core.database import get_db
from backend.core.security import hash_password
from backend.models.user import User
from backend.schemas.auth import LoginRequest, TokenResponse, UserOut
from backend.services.users import ensure_admin

router = APIRouter()


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    ensure_admin(db)  # make sure admin exists
    user = authenticate_user(db, payload.username, payload.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )
    if user.totp_secret:
        if not payload.totp_code or not verify_totp(user.totp_secret, payload.totp_code):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing TOTP code",
            )
    access_token = create_access_token(
        data={"sub": user.username},
        expires_delta=timedelta(hours=12),
    )
    return TokenResponse(access_token=access_token)


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(auth_core.get_current_user)):
    return current_user


