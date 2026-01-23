from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.orm import relationship

from backend.core.database import Base


class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    account_name = Column(String(100), unique=True, nullable=False, index=True)
    api_id = Column(String(64), nullable=False)
    api_hash = Column(String(128), nullable=False)
    proxy = Column(Text, nullable=True)  # store JSON string for proxy config
    status = Column(String(32), default="idle", nullable=False)
    last_login_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    tasks = relationship("Task", back_populates="account", cascade="all,delete")
