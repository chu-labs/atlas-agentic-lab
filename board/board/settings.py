"""Runtime configuration. Everything comes from the environment; nothing is hardcoded."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "atlas-board"
    environment: str = "local"
    log_level: str = "INFO"
    lab_name: str = "atlas-agentic-lab"

    # Postgres
    db_host: str = "localhost"
    db_port: int = 5432
    db_user: str = "atlas"
    db_password: str = "atlas"
    db_name: str = "board"

    # Basic auth for every route except /health. Empty user disables it.
    basic_auth_user: str = ""
    basic_auth_pass: str = ""

    # EventBridge bus. Empty means log only (local dev, tests).
    aws_region: str = "ap-southeast-2"
    event_bus: str = ""

    @property
    def dsn(self) -> str:
        return (
            f"host={self.db_host} port={self.db_port} user={self.db_user} "
            f"password={self.db_password} dbname={self.db_name}"
        )

    @property
    def admin_dsn(self) -> str:
        return (
            f"host={self.db_host} port={self.db_port} user={self.db_user} "
            f"password={self.db_password} dbname=postgres"
        )


@lru_cache
def settings() -> Settings:
    return Settings()
