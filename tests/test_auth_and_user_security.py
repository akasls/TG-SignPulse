import time
import pyotp
import pytest
from datetime import timedelta
from jose import jwt

from backend.core.auth import create_access_token, verify_totp
from backend.core.config import get_settings
from backend.core.security import hash_password, verify_password
from backend.api.routes.user import (
    _set_pending_totp_secret,
    get_pending_totp_secret,
    clear_pending_totp_secret,
    _cleanup_expired_pending_totp_secrets,
)


def test_password_hashing():
    pwd = "SuperSecretPassword123!"
    hashed = hash_password(pwd)
    assert hashed != pwd
    assert verify_password(pwd, hashed) is True
    assert verify_password("WrongPassword", hashed) is False


def test_jwt_token_expiry():
    settings = get_settings()
    token = create_access_token(data={"sub": "admin"}, expires_delta=timedelta(hours=2))
    payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    assert payload.get("sub") == "admin"
    assert "exp" in payload


def test_pending_totp_lifecycle():
    user_id = 999
    secret = pyotp.random_base32()
    _set_pending_totp_secret(user_id, secret)
    assert get_pending_totp_secret(user_id) == secret

    # Verify code generation & validation
    totp = pyotp.TOTP(secret)
    valid_code = totp.now()
    assert verify_totp(secret, valid_code) is True
    assert verify_totp(secret, "000000") is False

    # Clear secret
    clear_pending_totp_secret(user_id)
    assert get_pending_totp_secret(user_id) is None


def test_pending_totp_expiration():
    user_id = 888
    secret = pyotp.random_base32()
    _set_pending_totp_secret(user_id, secret)

    # Fast-forward monotonic clock beyond TTL
    future_time = time.monotonic() + 1000
    _cleanup_expired_pending_totp_secrets(now=future_time)
    assert get_pending_totp_secret(user_id) is None
