from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from backend.core.database import Base


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    cron = Column(String(64), nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, index=True)
    last_run_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    account = relationship("Account", back_populates="tasks")
    logs = relationship("TaskLog", back_populates="task", cascade="all,delete")


