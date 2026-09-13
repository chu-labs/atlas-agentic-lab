"""Runtime configuration. Everything comes from the environment; nothing is hardcoded."""
from __future__ import annotations

import json
import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# A SMALL production bug on a traditional team, calendar days per stage (owner-supplied).
DEFAULT_BASELINES = {
    "human_days_error_to_pr": 10.5,  # detect + triage + backlog wait + code + test
    "human_days_error_to_closed": 14,
    "human_hourly_rate_aud": 185,
    # Engineering hours a traditional team would book on the same fix (drives the cost comparison).
    "human_engineering_hours": 13,
    # The "then" lane of Then vs now. backlog_wait has no agentic counterpart and is drawn as a gap.
    "stage_days": {
        "detect": 1,  # reactive: a customer notices and reports
        "triage": 0.5,  # support validates: 10 minutes to hours (triage + ticket)
        "ticket": 0,
        "backlog_wait": 7,  # BAU backlog, picked up in a fortnightly sprint
        "code": 1,
        "test": 1,
        "pr": 0,
        "review": 1,
        "gate": 0,
        "deploy": 2,  # change approval / release cadence
        "verify": 0.5,  # verify + close
    },
    "lane_label": "Traditional SDLC · small bug · typical",
    # DORA benchmarks for the traditional team (illustrative until supplied) shown under the agentic tiles.
    "dora": {
        "deployment_frequency": "fortnightly",
        "deployment_frequency_per_day": 1 / 14,
        "lead_time_days": 14,
        "change_failure_rate": 0.15,
        "time_to_restore_days": 2,
        "notes": "illustrative until supplied",
    },
    "footnote": "Small fix; an XL fix runs to a quarter. Review and testing wait the same way.",
    "notes": "typical small bug",
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
    board_actor: str = "maroun"  # the board handle the dashboard acts as (GitHub login is not a board user)
    github_human_display_name: str = "Maroun"
    # ECS names for the footer strip (GET /api/system); read with the task role, degrade gracefully locally.
    ecs_cluster: str = ""
    image_tag: str = ""
    # The ops health poller (ECS/ALB/CloudWatch every 15 s). Off in tests.
    ops_poll: bool = True
    # ALB identifiers from the task definition: the CloudWatch LoadBalancer dimension and, per service, the
    # TargetGroup dimension ("svc=targetgroup/name/id,svc2=..."). Empty => discover by name (best effort).
    alb_arn_suffix: str = ""
    target_group_suffixes: str = ""

    def target_groups(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for part in self.target_group_suffixes.split(","):
            name, _, suffix = part.strip().partition("=")
            if name and suffix:
                out[name.strip()] = suffix.strip()
        return out

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
        out = {**DEFAULT_BASELINES, "stage_days": dict(DEFAULT_BASELINES["stage_days"]), "dora": dict(DEFAULT_BASELINES["dora"])}
        if self.human_baselines_json:
            try:
                override = json.loads(self.human_baselines_json)
            except ValueError:
                override = {}
            stage_days = override.pop("stage_days", None)
            dora = override.pop("dora", None)
            out.update(override)
            if isinstance(stage_days, dict):
                out["stage_days"].update(stage_days)
            out["dora"] = dict(DEFAULT_BASELINES["dora"])
            if isinstance(dora, dict):
                out["dora"].update(dora)
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
