from __future__ import annotations

from sqlalchemy.orm import Session

from backend.core.security import hash_password
from backend.models.user import User


def ensure_admin(db: Session, username: str = "admin", password: str = "admin123"):
    """
    Create a default admin user if none exists.
    In production, override via env/DB migration and rotate password.
    """
    user = db.query(User).filter(User.username == username).first()
    if user:
        return user
    new_user = User(username=username, password_hash=hash_password(password))
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


