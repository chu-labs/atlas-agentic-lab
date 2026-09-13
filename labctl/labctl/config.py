"""Lab configuration resolved from Terraform outputs and local files."""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TF_DIR = REPO_ROOT / "infra" / "terraform"
LOCAL_CFG = Path.home() / ".config" / "atlas-lab"
GITHUB_APP_FILE = LOCAL_CFG / "github-app.json"

AWS_PROFILE = os.environ.get("ATLAS_AWS_PROFILE", "chu-ai")
AWS_REGION = os.environ.get("ATLAS_AWS_REGION", "ap-southeast-2")
LAB_NAME = "atlas-agentic-lab"
GITHUB_ORG = os.environ.get("ATLAS_GH_ORG", "chu-labs")


@dataclass
class Outputs:
    alb_dns: str
    urls: dict[str, str]
    db_host: str
    db_master_secret_arn: str
    ecr: dict[str, str]
    queues: dict[str, str]
    event_bus: str
    secrets: dict[str, str]
    cluster: str
    gha_deploy_role_arn: str
    services: list[str] = field(default_factory=list)


@lru_cache
def outputs() -> Outputs:
    raw = subprocess.run(
        ["terraform", "output", "-json"], cwd=TF_DIR, capture_output=True, text=True, check=True
    ).stdout
    data = {k: v["value"] for k, v in json.loads(raw).items()}
    if not data:
        raise SystemExit("No Terraform outputs. Run `terraform apply` in infra/terraform first.")
    return Outputs(**data)


def github_app() -> dict:
    if not GITHUB_APP_FILE.exists():
        raise SystemExit(f"{GITHUB_APP_FILE} missing; run tools/github_app_manifest.py")
    return json.loads(GITHUB_APP_FILE.read_text())
