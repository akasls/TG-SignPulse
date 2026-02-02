from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from backend.core.config import get_settings

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
        raw = (os.getenv("TG_GLOBAL_CONCURRENCY") or "1").strip()
        try:
            limit = int(raw)
        except ValueError:
            limit = 1
        if limit < 1:
            limit = 1
        _GLOBAL_SEMAPHORE = asyncio.Semaphore(limit)
    return _GLOBAL_SEMAPHORE


def _account_store_path() -> Path:
    settings = get_settings()
    session_dir = settings.resolve_session_dir()
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir / "accounts.json"


def _load_account_store() -> dict:
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


def _save_account_store(data: dict) -> None:
    path = _account_store_path()
    tmp_path = path.with_suffix(".json.tmp")
    tmp_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    tmp_path.replace(path)


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
    data = _load_account_store()
    accounts = data.get("accounts")
    if not isinstance(accounts, dict):
        accounts = {}
        data["accounts"] = accounts
    accounts[account_name] = {
        "session_string": session_string.strip(),
        "updated_at": datetime.utcnow().isoformat(),
    }
    _save_account_store(data)


def delete_account_session_string(account_name: str) -> None:
    data = _load_account_store()
    accounts = data.get("accounts")
    if isinstance(accounts, dict) and account_name in accounts:
        accounts.pop(account_name, None)
        _save_account_store(data)


def session_string_file_path(session_dir: Path, account_name: str) -> Path:
    return session_dir / f"{account_name}.session_string"


def load_session_string_file(session_dir: Path, account_name: str) -> Optional[str]:
    path = session_string_file_path(session_dir, account_name)
    if not path.exists():
        return None
    try:
        content = path.read_text(encoding="utf-8").strip()
    except Exception:
        return None
    return content or None


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
