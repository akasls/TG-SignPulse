from __future__ import annotations

from sqlalchemy.orm import Session

from backend.core.security import hash_password
from backend.models.user import User


def ensure_admin(db: Session, username: str = "admin", password: str = "admin123"):
    """
    仅在用户表为空时创建一个默认管理员。
    防止用户修改用户名后，系统又自动创建一个默认的 admin 账号。
    """
    # 检查是否已有任何用户存在
    first_user = db.query(User).first()
    if first_user:
        return first_user

    # 如果没有任何用户，则创建默认管理员
    new_user = User(username=username, password_hash=hash_password(password))
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user
