"""Push a branch and open a pull request as the lab's GitHub App, so a human's approval counts."""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import httpx
import jwt

CFG = Path.home() / ".config" / "atlas-lab" / "github-app.json"
API = "https://api.github.com"


def _installation_token() -> str:
    cfg = json.loads(CFG.read_text())
    now = int(time.time())
    app_jwt = jwt.encode({"iat": now - 30, "exp": now + 540, "iss": str(cfg["id"])}, cfg["pem"], algorithm="RS256")
    r = httpx.post(
        f"{API}/app/installations/{cfg['installation_id']}/access_tokens",
        headers={"Authorization": f"Bearer {app_jwt}", "Accept": "application/vnd.github+json"},
        timeout=20,
    )
    r.raise_for_status()
    return r.json()["token"]


def push_and_open_pr(repo_dir: Path, branch: str, title: str, body: str, org: str = "chu-labs", repo: str = "atlas-platform") -> dict:
    token = _installation_token()
    url = f"https://x-access-token:{token}@github.com/{org}/{repo}.git"
    subprocess.run(["git", "push", "--force", "--quiet", url, f"{branch}:{branch}"], cwd=repo_dir, check=True, capture_output=True)
    r = httpx.post(
        f"{API}/repos/{org}/{repo}/pulls",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"title": title, "head": branch, "base": "main", "body": body},
        timeout=30,
    )
    if r.status_code == 422 and "already exists" in r.text:
        existing = httpx.get(f"{API}/repos/{org}/{repo}/pulls", params={"head": f"{org}:{branch}", "state": "open"}, headers={"Authorization": f"Bearer {token}"}, timeout=30).json()
        return existing[0]
    r.raise_for_status()
    return r.json()
