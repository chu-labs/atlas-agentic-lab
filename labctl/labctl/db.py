"""Direct Postgres access from the laptop (the DB security group allows admin_cidr)."""
from __future__ import annotations

import json
import os
import subprocess
from functools import lru_cache

from .aws import client
from .config import outputs
from .ecs import PLATFORM_REPO, REPO_ROOT

APPS = {
    "platform": {"cwd": PLATFORM_REPO, "module": "atlas.db", "db_name": "atlas"},
    "board": {"cwd": REPO_ROOT / "board", "module": "board.db", "db_name": "board"},
    "mission": {"cwd": REPO_ROOT / "mission-control", "module": "mission.db", "db_name": "mission"},
}


@lru_cache
def master_password() -> str:
    raw = client("secretsmanager").get_secret_value(SecretId=outputs().db_master_secret_arn)["SecretString"]
    return json.loads(raw)["password"]


def env_for(app: str) -> dict[str, str]:
    o = outputs()
    return {
        "DB_HOST": o.db_host,
        "DB_PORT": "5432",
        "DB_USER": "atlas_admin",
        "DB_PASSWORD": master_password(),
        "DB_NAME": APPS[app]["db_name"],
        "QUEUE_URL_PROD_ERRORS": "",
        "EVENT_BUS": "",
    }


def run_module(app: str, *args: str) -> int:
    spec = APPS[app]
    env = {**os.environ, **env_for(app)}
    return subprocess.run(["uv", "run", "python", "-m", spec["module"], *args], cwd=spec["cwd"], env=env).returncode


def psql_args(app: str) -> list[str]:
    e = env_for(app)
    return [f"postgresql://{e['DB_USER']}:{e['DB_PASSWORD']}@{e['DB_HOST']}:5432/{e['DB_NAME']}"]
