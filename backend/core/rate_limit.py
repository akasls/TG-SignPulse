from __future__ import annotations

import math
import time
from collections import deque
from threading import Lock
from typing import Deque, Dict, Tuple

from fastapi import HTTPException, Request, status

BucketKey = Tuple[str, str]


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._lock = Lock()
        self._attempts: Dict[BucketKey, Deque[float]] = {}
        self._blocked_until: Dict[BucketKey, float] = {}
        self._last_prune = time.monotonic()

    def reset(self, scope: str, key: str) -> None:
        bucket = (scope, key)
        with self._lock:
            self._attempts.pop(bucket, None)
            self._blocked_until.pop(bucket, None)

    def reset_all(self) -> None:
        with self._lock:
            self._attempts.clear()
            self._blocked_until.clear()

    def _prune_expired_locked(self, now: float) -> None:
        if now - self._last_prune < 300 and len(self._attempts) < 500:
            return
        self._last_prune = now

        # Prune attempts with no entries or older than 1 hour
        stale_cutoff = now - 3600
        expired_buckets = [
            b for b, deq in self._attempts.items()
            if not deq or deq[-1] < stale_cutoff
        ]
        for b in expired_buckets:
            self._attempts.pop(b, None)

        # Prune expired block entries
        expired_blocks = [
            b for b, blocked_time in self._blocked_until.items()
            if blocked_time <= now
        ]
        for b in expired_blocks:
            self._blocked_until.pop(b, None)

    def hit(
        self,
        *,
        scope: str,
        key: str,
        max_attempts: int,
        window_seconds: int,
        block_seconds: int,
        detail: str,
    ) -> None:
        bucket = (scope, key)
        now = time.monotonic()

        with self._lock:
            self._prune_expired_locked(now)

            blocked_until = self._blocked_until.get(bucket, 0.0)
            if blocked_until > now:
                retry_after = max(int(math.ceil(blocked_until - now)), 1)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=detail,
                    headers={"Retry-After": str(retry_after)},
                )

            attempts = self._attempts.setdefault(bucket, deque())
            cutoff = now - max(window_seconds, 1)
            while attempts and attempts[0] <= cutoff:
                attempts.popleft()

            attempts.append(now)
            if len(attempts) <= max(max_attempts, 1):
                return

            retry_after = max(int(block_seconds), 1)
            self._blocked_until[bucket] = now + retry_after
            attempts.clear()
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=detail,
                headers={"Retry-After": str(retry_after)},
            )


import ipaddress


def _is_valid_ip(val: str) -> bool:
    if not val:
        return False
    try:
        ipaddress.ip_address(val)
        return True
    except ValueError:
        return False


def get_client_identifier(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        first_hop = forwarded_for.split(",", 1)[0].strip()
        if _is_valid_ip(first_hop):
            return first_hop

    real_ip = request.headers.get("x-real-ip", "").strip()
    if _is_valid_ip(real_ip):
        return real_ip

    if request.client and request.client.host and _is_valid_ip(request.client.host):
        return request.client.host
    return "unknown"


def compose_rate_limit_key(request: Request, *parts: str) -> str:
    normalized_parts = [part.strip().lower() for part in parts if isinstance(part, str) and part.strip()]
    return "|".join([get_client_identifier(request), *normalized_parts])


_rate_limiter: InMemoryRateLimiter | None = None


def get_rate_limiter() -> InMemoryRateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = InMemoryRateLimiter()
    return _rate_limiter
