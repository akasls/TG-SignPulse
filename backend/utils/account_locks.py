from __future__ import annotations

import asyncio
from typing import Dict

_ACCOUNT_LOCKS: Dict[str, asyncio.Lock] = {}


def get_account_lock(account_name: str) -> asyncio.Lock:
    lock = _ACCOUNT_LOCKS.get(account_name)
    if lock is None:
        lock = asyncio.Lock()
        _ACCOUNT_LOCKS[account_name] = lock
    return lock
