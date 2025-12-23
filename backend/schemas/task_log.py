from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class TaskLogOut(BaseModel):
    id: int
    task_id: int
    status: str
    log_path: Optional[str] = None
    output: Optional[str] = None
    started_at: datetime
    finished_at: Optional[datetime] = None

    class Config:
        orm_mode = True



