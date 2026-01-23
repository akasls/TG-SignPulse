from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class AccountBase(BaseModel):
    account_name: str
    api_id: str
    api_hash: str
    proxy: Optional[str] = None  # JSON string


class AccountCreate(AccountBase):
    pass


class AccountUpdate(BaseModel):
    api_id: Optional[str] = None
    api_hash: Optional[str] = None
    proxy: Optional[str] = None
    status: Optional[str] = None


class AccountLoginVerify(BaseModel):
    code: Optional[str] = None
    password: Optional[str] = None


class AccountOut(AccountBase):
    id: int
    status: str
    last_login_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
