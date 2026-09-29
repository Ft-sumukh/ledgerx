"""
LEDGER-ORBIT: Configuration Package
=====================================
Centralized, type-safe settings loaded from environment variables.
Application refuses to start with invalid configuration.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="ORBIT_",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    environment: Environment = Environment.DEVELOPMENT
    app_name: str = "ledger-orbit"
    app_version: str = "0.1.0"
    debug: bool = False

    # API Server
    api_host: str = "0.0.0.0"
    api_port: int = Field(default=8000, ge=1, le=65535)
    api_workers: int = Field(default=1, ge=1, le=32)
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:3001"]

    # Database — SQLite default for zero-dependency local development
    database_url: str = "sqlite+aiosqlite:///./ledger_orbit_dev.db"
    database_pool_size: int = Field(default=5, ge=1, le=50)
    database_max_overflow: int = Field(default=10, ge=0, le=100)
    database_echo: bool = False

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    redis_enabled: bool = False

    # Queue
    queue_default_visibility_timeout_seconds: int = 30
    queue_max_receive_count: int = 5

    # Security
    secret_key: str = "CHANGE_ME_IN_PRODUCTION_USE_32_BYTE_RANDOM_SECRET"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7

    # Idempotency
    idempotency_key_ttl_hours: int = 24

    # Observability
    log_level: str = "INFO"
    log_format: str = "json"

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        if len(v) < 32:
            import warnings
            warnings.warn(
                "ORBIT_SECRET_KEY is too short (< 32 chars). Use a strong random secret in production.",
                stacklevel=2,
            )
        return v

    @property
    def is_production(self) -> bool:
        return self.environment == Environment.PRODUCTION

    @property
    def is_test(self) -> bool:
        return self.environment == Environment.TEST

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings singleton."""
    return Settings()
