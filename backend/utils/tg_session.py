from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Optional

from backend.core.config import get_settings
from backend.utils.time import utc_now_iso
from tg_signer.utils import atomic_write_json

_SESSION_MODE_ENV = "TG_SESSION_MODE"
_SESSION_MODE_FILE = "file"
_SESSION_MODE_STRING = "string"

_GLOBAL_SEMAPHORE: Optional[asyncio.Semaphore] = None


def get_session_mode() -> str:
    mode = os.getenv(_SESSION_MODE_ENV, _SESSION_MODE_FILE).strip().lower()
    return _SESSION_MODE_STRING if mode == _SESSION_MODE_STRING else _SESSION_MODE_FILE


def is_string_session_mode() -> bool:
    return get_session_mode() == _SESSION_MODE_STRING


def get_no_updates_flag() -> bool:
    raw = os.getenv("TG_SESSION_NO_UPDATES") or os.getenv("TG_NO_UPDATES") or ""
    raw = raw.strip().lower()
    return raw in {"1", "true", "yes", "on"}


def get_global_semaphore() -> asyncio.Semaphore:
    global _GLOBAL_SEMAPHORE
    if _GLOBAL_SEMAPHORE is None:
        limit = _resolve_concurrency_limit()
        _GLOBAL_SEMAPHORE = asyncio.Semaphore(limit)
    return _GLOBAL_SEMAPHORE


def _resolve_concurrency_limit() -> int:
    # Priority: env var > global settings > default 1
    raw = (os.getenv("TG_GLOBAL_CONCURRENCY") or "").strip()
    if raw:
        try:
            return max(int(raw), 1)
        except ValueError:
            pass
    try:
        from backend.services.config import get_config_service
        settings = get_config_service().get_global_settings()
        val = settings.get("tg_global_concurrency")
        if val is not None:
            return max(int(val), 1)
    except Exception:
        pass
    return 1


def update_global_semaphore(new_limit: int) -> None:
    """Update the global semaphore with a new concurrency limit at runtime."""
    global _GLOBAL_SEMAPHORE
    if new_limit < 1:
        new_limit = 1
    _GLOBAL_SEMAPHORE = asyncio.Semaphore(new_limit)


from threading import Lock

_ACCOUNT_STORE_LOCK = Lock()


def _account_store_path() -> Path:
    settings = get_settings()
    session_dir = settings.resolve_session_dir()
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir / "accounts.json"


def _load_account_store_unlocked() -> dict:
    path = _account_store_path()
    if not path.exists():
        return {"accounts": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"accounts": {}}
    if not isinstance(data, dict):
        return {"accounts": {}}
    accounts = data.get("accounts")
    if not isinstance(accounts, dict):
        data["accounts"] = {}
    return data


def _load_account_store() -> dict:
    with _ACCOUNT_STORE_LOCK:
        return _load_account_store_unlocked()


def _save_account_store_unlocked(data: dict) -> None:
    path = _account_store_path()
    atomic_write_json(path, data, indent=2)


def _save_account_store(data: dict) -> None:
    with _ACCOUNT_STORE_LOCK:
        _save_account_store_unlocked(data)


def list_account_names() -> list[str]:
    data = _load_account_store()
    accounts = data.get("accounts", {})
    if not isinstance(accounts, dict):
        return []
    return sorted(accounts.keys())


def get_account_session_string(account_name: str) -> Optional[str]:
    data = _load_account_store()
    entry = data.get("accounts", {}).get(account_name)
    if not isinstance(entry, dict):
        return None
    session_string = entry.get("session_string")
    if isinstance(session_string, str) and session_string.strip():
        return session_string.strip()
    return None


def set_account_session_string(account_name: str, session_string: str) -> None:
    with _ACCOUNT_STORE_LOCK:
        data = _load_account_store_unlocked()
        accounts = data.get("accounts")
        if not isinstance(accounts, dict):
            accounts = {}
            data["accounts"] = accounts
        entry = accounts.get(account_name)
        if not isinstance(entry, dict):
            entry = {}
        entry["session_string"] = session_string.strip()
        entry["updated_at"] = utc_now_iso()
        accounts[account_name] = entry
        _save_account_store_unlocked(data)


def delete_account_session_string(account_name: str) -> None:
    with _ACCOUNT_STORE_LOCK:
        data = _load_account_store_unlocked()
        accounts = data.get("accounts")
        if isinstance(accounts, dict) and account_name in accounts:
            accounts.pop(account_name, None)
            _save_account_store_unlocked(data)


def rename_account_entry(old_account_name: str, new_account_name: str) -> None:
    if old_account_name == new_account_name:
        return

    with _ACCOUNT_STORE_LOCK:
        data = _load_account_store_unlocked()
        accounts = data.get("accounts")
        if not isinstance(accounts, dict):
            accounts = {}
            data["accounts"] = accounts

        entry = accounts.pop(old_account_name, None)
        if entry is None:
            return
        if new_account_name in accounts:
            raise ValueError(f"account_name {new_account_name} already exists")

        if not isinstance(entry, dict):
            entry = {}
        entry["updated_at"] = utc_now_iso()
        accounts[new_account_name] = entry
        _save_account_store_unlocked(data)


def get_account_profile(account_name: str) -> dict[str, Any]:
    data = _load_account_store()
    entry = data.get("accounts", {}).get(account_name)
    if not isinstance(entry, dict):
        return {}
    return {
        "remark": entry.get("remark"),
        "proxy": entry.get("proxy"),
        "status": entry.get("status"),
        "status_message": entry.get("status_message"),
        "status_code": entry.get("status_code"),
        "status_checked_at": entry.get("status_checked_at"),
        "needs_relogin": bool(entry.get("needs_relogin", False)),
        "invalid_notified_at": entry.get("invalid_notified_at"),
    }


def get_account_proxy(account_name: str) -> Optional[str]:
    profile = get_account_profile(account_name)
    proxy = profile.get("proxy")
    if isinstance(proxy, str) and proxy.strip():
        return proxy.strip()
    return None


def get_account_remark(account_name: str) -> Optional[str]:
    profile = get_account_profile(account_name)
    remark = profile.get("remark")
    if isinstance(remark, str) and remark.strip():
        return remark.strip()
    return None


def set_account_profile(
    account_name: str, *, remark: Optional[str] = None, proxy: Optional[str] = None
) -> None:
    with _ACCOUNT_STORE_LOCK:
        data = _load_account_store_unlocked()
        accounts = data.get("accounts")
        if not isinstance(accounts, dict):
            accounts = {}
            data["accounts"] = accounts
        entry = accounts.get(account_name)
        if not isinstance(entry, dict):
            entry = {}
        if remark is not None:
            entry["remark"] = remark.strip() if isinstance(remark, str) else remark
        if proxy is not None:
            entry["proxy"] = proxy.strip() if isinstance(proxy, str) else proxy
        entry["updated_at"] = utc_now_iso()
        accounts[account_name] = entry
        _save_account_store_unlocked(data)


def get_account_status(account_name: str) -> dict[str, Any]:
    profile = get_account_profile(account_name)
    status = profile.get("status")
    return {
        "status": status if isinstance(status, str) and status else "connected",
        "message": profile.get("status_message") or "",
        "code": profile.get("status_code"),
        "checked_at": profile.get("status_checked_at"),
        "needs_relogin": bool(profile.get("needs_relogin", False)),
        "invalid_notified_at": profile.get("invalid_notified_at"),
    }


def set_account_status(
    account_name: str,
    *,
    status: str,
    message: str = "",
    code: Optional[str] = None,
    needs_relogin: bool = False,
    invalid_notified_at: Optional[str] = None,
) -> None:
    with _ACCOUNT_STORE_LOCK:
        data = _load_account_store_unlocked()
        accounts = data.get("accounts")
        if not isinstance(accounts, dict):
            accounts = {}
            data["accounts"] = accounts
        entry = accounts.get(account_name)
        if not isinstance(entry, dict):
            entry = {}
        entry["status"] = status
        entry["status_message"] = message or ""
        entry["status_code"] = code
        entry["status_checked_at"] = utc_now_iso()
        entry["needs_relogin"] = bool(needs_relogin)
        if invalid_notified_at is not None:
            entry["invalid_notified_at"] = invalid_notified_at
        if status != "invalid":
            entry.pop("invalid_notified_at", None)
        entry["updated_at"] = utc_now_iso()
        accounts[account_name] = entry
        _save_account_store_unlocked(data)


def session_string_file_path(session_dir: Path, account_name: str) -> Path:
    return session_dir / f"{account_name}.session_string"


def load_session_string_file(session_dir: Path, account_name: str) -> Optional[str]:
    path = session_string_file_path(session_dir, account_name)
    if not path.exists():
        # Try to export session string from .session SQLite file
        return _export_session_string_from_file(session_dir, account_name)
    try:
        content = path.read_text(encoding="utf-8").strip()
    except Exception:
        return None
    return content or None


def _export_session_string_from_file(session_dir: Path, account_name: str) -> Optional[str]:
    """Extract session string from .session SQLite file and cache it."""
    import sqlite3
    import struct
    import base64

    session_file = session_dir / f"{account_name}.session"
    if not session_file.exists():
        return None

    try:
        conn = sqlite3.connect(str(session_file), timeout=10, check_same_thread=False)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=10000")
        except Exception:
            pass

        try:
            row = conn.execute(
                "SELECT dc_id, api_id, test_mode, auth_key, user_id, is_bot FROM sessions"
            ).fetchone()
        except Exception:
            conn.close()
            return None

        if not row:
            conn.close()
            return None

        dc_id, api_id, test_mode, auth_key, user_id, is_bot = row
        conn.close()

        if not auth_key or not user_id:
            return None

        # Pack into pyrogram session string format (version 1)
        packed = struct.pack(
            ">B?256sQ?",
            dc_id,
            bool(test_mode),
            auth_key,
            user_id,
            bool(is_bot),
        )
        session_string = base64.urlsafe_b64encode(packed).decode("ascii").rstrip("=")
        session_string = "1" + session_string  # Version prefix

        # Cache it to .session_string file for future use
        try:
            cache_path = session_string_file_path(session_dir, account_name)
            cache_path.write_text(session_string, encoding="utf-8")
        except Exception:
            pass

        return session_string
    except Exception:
        return None


def save_session_string_file(
    session_dir: Path, account_name: str, session_string: str
) -> None:
    path = session_string_file_path(session_dir, account_name)
    path.write_text(session_string.strip(), encoding="utf-8")


def delete_session_string_file(session_dir: Path, account_name: str) -> None:
    path = session_string_file_path(session_dir, account_name)
    if path.exists():
        try:
            path.unlink()
        except Exception:
            pass
