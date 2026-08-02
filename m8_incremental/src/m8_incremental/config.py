"""Configuration for m8_incremental service."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_PACKAGE_ROOT = Path(__file__).resolve().parents[2]
_ENV_FILE = _PACKAGE_ROOT / ".env"


def _default_database_url() -> str:
    try:
        from data_staging.config import settings as connect_settings

        return str(connect_settings.DATABASE_URL)
    except Exception:
        return os.getenv("DATABASE_URL", "postgresql://localhost/m8_connect")


class IncrementalSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE) if _ENV_FILE.is_file() else ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATABASE_URL: str = Field(default_factory=_default_database_url)
    UPLOAD_PATH: str = Field("./data/uploads")
    INCREMENTAL_SOURCE_ROOT: Optional[str] = Field(None)
    INCREMENTAL_ADMIN_EMAIL: Optional[str] = Field(None)
    ALERT_EMAIL_ENABLED: bool = Field(False)
    SMTP_SERVER: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_USE_TLS: bool = True
    EMAIL_FROM: Optional[str] = None
    SCHEDULER_RESYNC_SECONDS: int = 300


def get_settings() -> IncrementalSettings:
    return IncrementalSettings()


settings = get_settings()


def upload_root() -> Path:
    try:
        from data_staging.config import settings as connect_settings

        return Path(connect_settings.UPLOAD_PATH).resolve()
    except Exception:
        return Path(settings.UPLOAD_PATH).resolve()


def default_source_root() -> Optional[Path]:
    raw = settings.INCREMENTAL_SOURCE_ROOT or os.getenv("INCREMENTAL_SOURCE_ROOT")
    if not raw:
        return None
    return Path(raw).resolve()
