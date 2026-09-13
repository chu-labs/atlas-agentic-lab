"""Runtime configuration. Everything comes from the environment; nothing is hardcoded."""
from __future__ import annotations

import json
import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_BASELINES = {
    "human_days_error_to_pr": 3.5,
    "human_days_error_to_closed": 9,
    "human_hourly_rate_aud": 185,
    "notes": "placeholder until supplied",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "mission-control"
    environment: str = "local"
    log_level: str = "INFO"
    lab_name: str = "atlas-agentic-lab"

    # Postgres
    db_host: str = "localhost"
    db_port: int = 5432
    db_user: str = "atlas"
    db_password: str = "atlas"
    db_name: str = "mission"

    # Basic auth for every route except /health and /ws. Empty user disables it.
    basic_auth_user: str = ""
    basic_auth_pass: str = ""
    # Signs the short-lived WebSocket tokens. Defaults derive from the basic-auth secret.
    ws_secret: str = ""

    # AWS: the bus we emit to and the queue we consume. Empty means local (log / do not poll).
    aws_region: str = "ap-southeast-2"
    event_bus: str = ""
    queue_url_mission_events: str = ""
    queue_url_prod_errors: str = ""

    # GitHub, as the human. Only the approve/reject endpoints use the token.
    github_org: str = "chu-labs"
    github_repo: str = "atlas-platform"
    github_human_token: str = ""
    github_human_login: str = ""
    github_human_display_name: str = "Maroun"

    board_url: str = ""
    platform_url: str = ""
    human_baselines_json: str = ""

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

    @property
    def signing_secret(self) -> str:
        return self.ws_secret or f"mission-control:{self.basic_auth_user}:{self.basic_auth_pass}"

    @property
    def baselines(self) -> dict:
        out = dict(DEFAULT_BASELINES)
        if self.human_baselines_json:
            try:
                out.update(json.loads(self.human_baselines_json))
            except ValueError:
                pass
        return out

    def queue_urls(self) -> dict[str, str]:
        """Every QUEUE_URL_* in the environment, keyed by queue name (QUEUE_URL_PROD_ERRORS -> prod-errors)."""
        out: dict[str, str] = {}
        for k, v in os.environ.items():
            if k.startswith("QUEUE_URL_") and v:
                out[k[len("QUEUE_URL_"):].lower().replace("_", "-")] = v
        return out


@lru_cache
def settings() -> Settings:
    return Settings()
