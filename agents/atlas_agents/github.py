"""GitHub as the atlas agents App: installation tokens and the REST calls the fleet needs."""
from __future__ import annotations

import json
import logging
import time
from functools import lru_cache

import httpx
import jwt

from .config import config

log = logging.getLogger(__name__)
API = "https://api.github.com"


@lru_cache
def app_secret() -> dict:
    """{id, slug, installation_id, pem} from Secrets Manager, or GITHUB_APP_JSON for local runs."""
    import os

    if os.environ.get("GITHUB_APP_JSON"):
        return json.loads(os.environ["GITHUB_APP_JSON"])
    import boto3

    raw = boto3.client("secretsmanager", region_name=config().aws_region).get_secret_value(SecretId=config().secret_github_app)
    return json.loads(raw["SecretString"])


class GitHub:
    def __init__(self):
        self._token: str | None = None
        self._expires = 0.0
        self.org = config().github_org
        self.repo = config().github_repo

    # --- auth -------------------------------------------------------------
    def token(self) -> str:
        if self._token and time.time() < self._expires - 120:
            return self._token
        s = app_secret()
        now = int(time.time())
        app_jwt = jwt.encode({"iat": now - 30, "exp": now + 540, "iss": str(s["id"])}, s["pem"], algorithm="RS256")
        r = httpx.post(
            f"{API}/app/installations/{s['installation_id']}/access_tokens",
            headers={"Authorization": f"Bearer {app_jwt}", "Accept": "application/vnd.github+json"},
            timeout=20,
        )
        r.raise_for_status()
        self._token = r.json()["token"]
        self._expires = time.time() + 3600
        return self._token

    def _h(self) -> dict:
        return {"Authorization": f"Bearer {self.token()}", "Accept": "application/vnd.github+json", "User-Agent": "atlas-agents"}

    def api(self, method: str, path: str, **kw):
        r = httpx.request(method, f"{API}{path}", headers=self._h(), timeout=30, **kw)
        if r.status_code >= 400:
            log.error("github %s %s -> %s %s", method, path, r.status_code, r.text[:300])
        r.raise_for_status()
        return r.json() if r.content else None

    def clone_url(self) -> str:
        return f"https://x-access-token:{self.token()}@github.com/{self.org}/{self.repo}.git"

    # --- pull requests ----------------------------------------------------
    def open_pr(self, head: str, title: str, body: str, base: str = "main") -> dict:
        return self.api("POST", f"/repos/{self.org}/{self.repo}/pulls", json={"title": title, "head": head, "base": base, "body": body})

    def pr(self, number: int) -> dict:
        return self.api("GET", f"/repos/{self.org}/{self.repo}/pulls/{number}")

    def pr_files(self, number: int) -> list[dict]:
        return self.api("GET", f"/repos/{self.org}/{self.repo}/pulls/{number}/files")

    def pr_diff(self, number: int) -> str:
        r = httpx.get(
            f"{API}/repos/{self.org}/{self.repo}/pulls/{number}",
            headers={**self._h(), "Accept": "application/vnd.github.diff"},
            timeout=30,
        )
        r.raise_for_status()
        return r.text

    def review(self, number: int, event: str, body: str) -> dict:
        """event: COMMENT or REQUEST_CHANGES. APPROVE is refused here on purpose."""
        if event == "APPROVE":
            raise PermissionError("agents do not approve pull requests")
        return self.api("POST", f"/repos/{self.org}/{self.repo}/pulls/{number}/reviews", json={"event": event, "body": body})

    def comment(self, number: int, body: str) -> dict:
        return self.api("POST", f"/repos/{self.org}/{self.repo}/issues/{number}/comments", json={"body": body})

    def merge(self, number: int, method: str = "squash") -> dict:
        return self.api("PUT", f"/repos/{self.org}/{self.repo}/pulls/{number}/merge", json={"merge_method": method})

    def check_runs(self, sha: str) -> list[dict]:
        return self.api("GET", f"/repos/{self.org}/{self.repo}/commits/{sha}/check-runs").get("check_runs", [])

    # --- actions ----------------------------------------------------------
    def workflow_runs(self, workflow: str = "deploy.yml", branch: str = "main", per_page: int = 5) -> list[dict]:
        return self.api("GET", f"/repos/{self.org}/{self.repo}/actions/workflows/{workflow}/runs", params={"branch": branch, "per_page": per_page})["workflow_runs"]

    def run(self, run_id: int) -> dict:
        return self.api("GET", f"/repos/{self.org}/{self.repo}/actions/runs/{run_id}")

    def pending_deployments(self, run_id: int) -> list[dict]:
        return self.api("GET", f"/repos/{self.org}/{self.repo}/actions/runs/{run_id}/pending_deployments")
