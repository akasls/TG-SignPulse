from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class TaskBase(BaseModel):
    name: str  # 对应 tg-signer 的 task_name
    cron: str
    account_id: int


class TaskCreate(TaskBase):
    enabled: bool = True


class TaskUpdate(BaseModel):
    name: Optional[str] = None
    cron: Optional[str] = None
    enabled: Optional[bool] = None
    account_id: Optional[int] = None


class TaskOut(TaskBase):
    id: int
    enabled: bool
    last_run_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
