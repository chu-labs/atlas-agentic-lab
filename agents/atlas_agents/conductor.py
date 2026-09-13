"""Conductor: after the human merges, watch the deploy, smoke-check production, prove the error
signature is gone, and close the ticket. If verification fails, reopen and escalate."""
from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

import httpx

from . import base
from .github import GitHub

log = logging.getLogger(__name__)


class Agent(base.Agent):
    def __init__(self):
        super().__init__()
        self.gh = GitHub()
        self.http = httpx.Client(base_url=self.cfg.platform_url, auth=self.cfg.basic_auth, timeout=15)
        self.handled: set[str] = set()

    def handle(self, source: str, detail_type: str, detail: dict) -> None:
        if detail_type == "human.approved":
            key = detail.get("ticket")
            self.think(key, f"A human approved and merged PR #{detail.get('pr', {}).get('number')}. Watching the production deploy.")
            self.emitter.status("working", "Waiting for the deploy workflow", ticket=key)
        elif detail_type == "deploy.completed":
            sha = detail.get("sha")
            if not sha or sha in self.handled:
                return
            self.handled.add(sha)
            self.verify_deploy(sha, detail)

    def verify_deploy(self, sha: str, detail: dict) -> None:
        if not self.guard("can_deploy", "verify a production deploy"):
            return
        prs = self.gh.api("GET", f"/repos/{self.gh.org}/{self.gh.repo}/commits/{sha}/pulls")
        pr = prs[0] if prs else None
        key = self._ticket_for(pr)
        deployed_at = datetime.now(UTC)
        self.think(key, f"Deploy of {sha[:12]} finished (run {detail.get('run_id')}). Smoke-checking production before I believe it.")
        checks = self._smoke(key)
        failed = [c for c in checks if not c["ok"]]
        if failed:
            self._reopen(key, pr, "Smoke checks failed after deploy: " + "; ".join(f"{c['name']} -> {c['detail']}" for c in failed))
            return
        self.think(key, "Smoke checks pass: " + ", ".join(c["name"] for c in checks) + ". Now confirming the original error signature has stopped.")
        signature = ((self.board.get(key).get("source") or {}).get("signature") if key else None)
        seen = self._signature_seen_since(signature, deployed_at) if signature else 0
        if seen:
            self._reopen(key, pr, f"The original error signature `{signature}` recurred {seen} times after the deploy.")
            return
        self.emitter.emit("verify.passed", key, f"Verified: deploy healthy and `{signature or 'n/a'}` has not recurred since {deployed_at:%H:%M:%S} UTC",
                          smoke={"ok": True, "checks": checks}, signature_seen_after_deploy=0, sha=sha)
        if key and self.guard("can_close_tickets", f"close {key}", key):
            self.board.comment(key, "Deployed to production and verified:\n" + "\n".join(f"- {c['name']}: {c['detail']}" for c in checks) +
                               (f"\n- error signature `{signature}` not seen since deploy" if signature else "\n- human-reported ticket: no production error signature to check; reproduction endpoint healthy")
                               + "\n\nClosing.")
            self.board.move(key, "Done")
            self.emitter.emit("ticket.closed", key, f"Closed {key}: fix deployed and verified in production", sha=sha, pr={"number": pr["number"], "url": pr["html_url"]} if pr else {})
        self.emitter.status("idle", f"{key or sha[:12]} verified and closed." if key else "Deploy verified.", ticket=key)

    def _ticket_for(self, pr: dict | None) -> str | None:
        import re

        if not pr:
            return None
        m = re.search(r"ATLAS-\d+", pr.get("title", "") + " " + (pr.get("head", {}).get("ref") or ""))
        return m.group(0) if m else None

    def _smoke(self, key: str | None) -> list[dict]:
        checks = []

        def check(name, fn):
            try:
                ok, detail = fn()
            except Exception as e:  # noqa: BLE001
                ok, detail = False, f"{type(e).__name__}: {e}"
            checks.append({"name": name, "ok": ok, "detail": detail})

        def health():
            return self.http.get("/health").json().get("status") == "ok", "status ok, db reachable"

        def stats():
            return self.http.get("/api/stats").status_code == 200, "portfolio stats served"

        def reconcile():
            r = self.http.get("/api/renewals/reconcile")
            return r.status_code == 200, f"{r.status_code} {r.text[:120]}"

        def quote():
            # quote an active policy that is due soon, so the check never trips a business rule itself
            due = self.http.get("/api/policies", params={"due_within_days": 30, "limit": 1}).json()
            if not due:
                return True, "no policies due; skipped"
            pn = due[0]["policy_number"]
            r = self.http.post(f"/api/policies/{pn}/quote")
            return r.status_code == 200, f"{pn} -> {r.status_code}"

        check("health", health)
        check("stats", stats)
        check("renewals reconcile", reconcile)
        check("quote sample", quote)
        if key:
            src = self.board.get(key).get("source") or {}
            ep = src.get("endpoint")
            if ep and "{" not in ep:

                def repro():
                    r = self.http.get(ep)
                    rule_failure = r.status_code == 422 and src.get("kind") == "business_rule"
                    return r.status_code < 500 and not rule_failure, f"{r.status_code}"

                check(f"reproduction {ep}", repro)
        return checks

    def _signature_seen_since(self, signature: str, since: datetime, settle: int = 30) -> int:
        """Wait for traffic to exercise the fix, then count the signature in the platform's logs."""
        import boto3

        time.sleep(settle)
        logs = boto3.client("logs", region_name=self.cfg.aws_region)
        resp = logs.filter_log_events(
            logGroupName=f"/{self.cfg.lab_name}/atlas-platform",
            startTime=int(since.timestamp() * 1000),
            filterPattern=f'"{signature}"',
            limit=50,
        )
        return len(resp.get("events", []))

    def _reopen(self, key: str | None, pr: dict | None, why: str) -> None:
        self.emitter.emit("verify.failed", key, f"Verification failed: {why[:140]}", smoke={"ok": False})
        if key and self.guard("can_reopen_tickets", f"reopen {key}", key):
            self.board.comment(key, f"**Verification failed after deploy.** {why}\n\nReopening and escalating to a human; a rollback may be needed.")
            self.board.move(key, "In Progress")
            self.board.escalate(key, "maroun", f"Post-deploy verification failed: {why}")
        self.emitter.status("blocked", f"Verification failed for {key or 'deploy'}: {why[:100]}", ticket=key)
