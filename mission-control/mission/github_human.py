"""GitHub as the human, with a fine-grained PAT. Only the approve/reject endpoints call this.

Approve: review APPROVE -> squash merge -> (background) find the deploy.yml run for the merge
commit and approve its pending environment deployments. Reject: REQUEST_CHANGES with the reason.
"""
from __future__ import annotations

import logging
import threading
import time

import httpx

from .settings import settings

log = logging.getLogger(__name__)
API = "https://api.github.com"


class HumanGitHub:
    def __init__(self):
        s = settings()
        self.token = s.github_human_token
        self.org = s.github_org
        self.repo = s.github_repo

    @property
    def configured(self) -> bool:
        return bool(self.token)

    def _h(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "atlas-mission-control",
        }

    def api(self, method: str, path: str, **kw):
        r = httpx.request(method, f"{API}{path}", headers=self._h(), timeout=30, **kw)
        if r.status_code >= 400:
            log.error("github %s %s -> %s %s", method, path, r.status_code, r.text[:300])
        r.raise_for_status()
        return r.json() if r.content else None

    # --- pull requests ----------------------------------------------------
    def review(self, number: int, event: str, body: str) -> dict:
        return self.api("POST", f"/repos/{self.org}/{self.repo}/pulls/{number}/reviews", json={"event": event, "body": body})

    def merge(self, number: int, method: str = "squash") -> dict:
        return self.api("PUT", f"/repos/{self.org}/{self.repo}/pulls/{number}/merge", json={"merge_method": method})

    # --- actions ----------------------------------------------------------
    def workflow_runs(self, workflow: str = "deploy.yml", branch: str = "main") -> list[dict]:
        return self.api(
            "GET", f"/repos/{self.org}/{self.repo}/actions/workflows/{workflow}/runs",
            params={"branch": branch, "per_page": 10},
        )["workflow_runs"]

    def pending_deployments(self, run_id: int) -> list[dict]:
        return self.api("GET", f"/repos/{self.org}/{self.repo}/actions/runs/{run_id}/pending_deployments") or []

    def approve_pending(self, run_id: int, environment_ids: list[int], comment: str) -> None:
        self.api(
            "POST", f"/repos/{self.org}/{self.repo}/actions/runs/{run_id}/pending_deployments",
            json={"environment_ids": environment_ids, "state": "approved", "comment": comment},
        )

    # --- the two human actions -------------------------------------------
    def approve_and_merge(self, number: int) -> str:
        """Approve, squash-merge, and start the deploy-gate watcher. Returns the merge sha."""
        self.review(number, "APPROVE", "Approved from Mission Control")
        merged = self.merge(number, "squash")
        sha = merged.get("sha", "")
        threading.Thread(target=self._approve_deploy, args=(sha, number), name=f"deploy-gate:{number}", daemon=True).start()
        return sha

    def reject(self, number: int, reason: str) -> None:
        self.review(number, "REQUEST_CHANGES", reason)

    def _approve_deploy(self, sha: str, number: int, timeout: float = 240.0) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                run = next((r for r in self.workflow_runs() if r.get("head_sha") == sha), None)
                if run:
                    pending = self.pending_deployments(run["id"])
                    if pending:
                        ids = [p["environment"]["id"] for p in pending if p.get("environment")]
                        self.approve_pending(run["id"], ids, f"Approved from Mission Control for PR #{number}")
                        log.info("deploy approved", extra={"run_id": run["id"], "pr": number, "environments": ids})
                        return
                    if run.get("status") == "completed":
                        log.info("deploy run finished without a pending gate", extra={"run_id": run["id"]})
                        return
            except Exception:
                log.exception("deploy gate poll failed")
            time.sleep(6)
        log.warning("gave up waiting for the deploy gate", extra={"sha": sha, "pr": number})
