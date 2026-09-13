"""Write real values into the Secrets Manager secrets Terraform created with placeholders."""
from __future__ import annotations

import json

from .aws import client
from .config import github_app, outputs


def put(name: str, value: dict) -> str:
    arn = outputs().secrets[name]
    client("secretsmanager").put_secret_value(SecretId=arn, SecretString=json.dumps(value))
    return arn


def push_anthropic(api_key: str) -> str:
    return put("anthropic-api-key", {"api_key": api_key})


def push_basic_auth(username: str, password: str) -> str:
    return put("basic-auth", {"username": username, "password": password})


def push_github_app() -> str:
    app = github_app()
    if not app.get("installation_id"):
        raise SystemExit("github-app.json has no installation_id; run tools/github_app_token.py --check")
    return put(
        "github-app",
        {"id": str(app["id"]), "slug": app["slug"], "installation_id": str(app["installation_id"]), "pem": app["pem"]},
    )


def status() -> dict[str, bool]:
    """True when a secret no longer holds the Terraform placeholder."""
    sm = client("secretsmanager")
    out = {}
    for name, arn in outputs().secrets.items():
        val = sm.get_secret_value(SecretId=arn)["SecretString"]
        out[name] = "REPLACE_ME" not in val
    return out
