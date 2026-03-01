from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

_BASE_DIR: Optional[Path] = None
_DATA_DIR_OVERRIDE_FILE_ENV = "APP_DATA_DIR_OVERRIDE_FILE"
_DEFAULT_DATA_DIR_OVERRIDE_FILE = Path.cwd() / ".tg_signpulse_data_dir"


def _probe_writable_dir(base: Path) -> bool:
    probe_dir = base / ".probe"
    test_file = probe_dir / ".write_test"
    try:
        probe_dir.mkdir(parents=True, exist_ok=True)
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink()
        return True
    except Exception:
        return False
    finally:
        try:
            if test_file.exists():
                test_file.unlink()
        except Exception:
            pass
        try:
            if probe_dir.exists() and not any(probe_dir.iterdir()):
                probe_dir.rmdir()
        except Exception:
            pass


def is_writable_dir(path: Path) -> bool:
    return _probe_writable_dir(path)


def get_data_dir_override_file() -> Path:
    raw = (os.getenv(_DATA_DIR_OVERRIDE_FILE_ENV) or "").strip()
    if raw:
        return Path(raw).expanduser()
    return _DEFAULT_DATA_DIR_OVERRIDE_FILE


def load_data_dir_override() -> Optional[Path]:
    override_file = get_data_dir_override_file()
    if not override_file.exists():
        return None
    try:
        value = override_file.read_text(encoding="utf-8").strip()
    except Exception:
        return None
    if not value:
        return None
    return Path(value).expanduser()


def save_data_dir_override(path: Path | str) -> Path:
    target = Path(path).expanduser()
    override_file = get_data_dir_override_file()
    override_file.parent.mkdir(parents=True, exist_ok=True)
    override_file.write_text(str(target), encoding="utf-8")
    return target


def clear_data_dir_override() -> None:
    override_file = get_data_dir_override_file()
    if override_file.exists():
        override_file.unlink()


def get_initial_data_dir() -> Path:
    env_data_dir = (os.getenv("APP_DATA_DIR") or "").strip()
    if env_data_dir:
        return Path(env_data_dir).expanduser()
    override = load_data_dir_override()
    if override:
        return override
    return Path("/data")


def get_writable_base_dir() -> Path:
    global _BASE_DIR
    if _BASE_DIR is not None:
        return _BASE_DIR

    preferred = Path("/data")
    if _probe_writable_dir(preferred):
        _BASE_DIR = preferred
        return _BASE_DIR

    fallback = Path("/tmp/tg-signpulse")
    fallback.mkdir(parents=True, exist_ok=True)
    message = (
        "WARNING: /data is not writable. Falling back to /tmp/tg-signpulse; "
        "data may be non-persistent."
    )
    print(message)
    logging.getLogger("backend.storage").warning(message)
    _BASE_DIR = fallback
    return _BASE_DIR
