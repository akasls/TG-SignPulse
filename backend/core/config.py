from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from backend.utils.storage import get_writable_base_dir
try:
    from pydantic.v1 import BaseSettings
except ImportError:
    from pydantic import BaseSettings


# 生成或获取持久化的密钥
def get_default_secret_key() -> str:
    """获取默认密钥，优先使用环境变量，否则使用固定默认值"""
    # 如果设置了环境变量，使用环境变量
    env_secret = os.getenv("APP_SECRET_KEY")
    if env_secret and env_secret.strip():
        return env_secret.strip()

    # 否则使用固定的默认值（生产环境应该设置环境变量）
    # 这个默认值确保应用能启动，但不够安全
    return "tg-signer-default-secret-key-please-change-in-production-2024"


class Settings(BaseSettings):
    app_name: str = "tg-signer-panel"
    host: str = "0.0.0.0"
    port: int = 3000

    # 使用函数获取默认密钥
    secret_key: str = get_default_secret_key()
    access_token_expire_hours: int = 12

    timezone: str = os.getenv("TZ", "Asia/Hong_Kong")
    data_dir: Path = Path("/data")
    db_path: Optional[Path] = None
    signer_workdir: Optional[Path] = None
    session_dir: Optional[Path] = None
    logs_dir: Optional[Path] = None

    class Config:
        env_file = ".env"
        env_prefix = "APP_"
        case_sensitive = False

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.resolve_db_path()}?check_same_thread=False"

    def resolve_db_path(self) -> Path:
        return self.db_path or self.resolve_base_dir() / "db.sqlite"

    def resolve_workdir(self) -> Path:
        return self.signer_workdir or self.resolve_base_dir() / ".signer"

    def resolve_session_dir(self) -> Path:
        return self.session_dir or self.resolve_base_dir() / "sessions"

    def resolve_logs_dir(self) -> Path:
        return self.logs_dir or self.resolve_base_dir() / "logs"

    def resolve_base_dir(self) -> Path:
        if self.data_dir and str(self.data_dir) != "/data":
            return self.data_dir
        return get_writable_base_dir()


@lru_cache()
def get_settings() -> Settings:
    return Settings()
