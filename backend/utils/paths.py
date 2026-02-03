from pathlib import Path

from backend.core.config import Settings


def ensure_data_dirs(settings: Settings) -> None:
    base = settings.resolve_base_dir()
    base.mkdir(parents=True, exist_ok=True)
    (settings.resolve_workdir()).mkdir(parents=True, exist_ok=True)
    (settings.resolve_session_dir()).mkdir(parents=True, exist_ok=True)
    (settings.resolve_logs_dir()).mkdir(parents=True, exist_ok=True)

    db_path: Path = settings.resolve_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
