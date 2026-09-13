"""Everything from the environment. Terraform sets these on every task definition."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

DEFS = Path(__file__).resolve().parents[1] / "defs"


@dataclass(frozen=True)
class Config:
    agent_name: str = os.environ.get("AGENT_NAME", "scout")
    lab_name: str = os.environ.get("LAB_NAME", "atlas-agentic-lab")
    aws_region: str = os.environ.get("AWS_REGION", "ap-southeast-2")
    event_bus: str = os.environ.get("EVENT_BUS", "")
    queue_url: str = os.environ.get("QUEUE_URL", "")
    queue_url_prod_errors: str = os.environ.get("QUEUE_URL_PROD_ERRORS", "")
    alb_dns: str = os.environ.get("ALB_DNS", "localhost")
    board_url: str = os.environ.get("BOARD_URL", f"http://{os.environ.get('ALB_DNS', 'localhost')}:8081")
    platform_url: str = os.environ.get("PLATFORM_URL", f"http://{os.environ.get('ALB_DNS', 'localhost')}:8082")
    basic_auth_user: str = os.environ.get("BASIC_AUTH_USER", "")
    basic_auth_pass: str = os.environ.get("BASIC_AUTH_PASS", "")
    anthropic_api_key: str = os.environ.get("ANTHROPIC_API_KEY", "")
    model: str = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")
    github_org: str = os.environ.get("GITHUB_ORG", "chu-labs")
    github_repo: str = os.environ.get("GITHUB_REPO", "atlas-platform")
    secret_github_app: str = os.environ.get("SECRET_GITHUB_APP", "")
    db_host: str = os.environ.get("DB_HOST", "")
    db_user: str = os.environ.get("DB_USER", "")
    db_password: str = os.environ.get("DB_PASSWORD", "")
    workdir: Path = field(default_factory=lambda: Path(os.environ.get("AGENT_WORKDIR", "/work")))

    @property
    def basic_auth(self) -> tuple[str, str] | None:
        return (self.basic_auth_user, self.basic_auth_pass) if self.basic_auth_user else None


@lru_cache
def config() -> Config:
    return Config()
