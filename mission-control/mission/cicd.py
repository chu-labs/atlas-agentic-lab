"""GitHub Actions and pull requests for the CI/CD tab. Cached for 15 s; degrades to an empty view.

Prefers the human token; falls back to unauthenticated calls (fine for a public repo).
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import UTC, datetime

import httpx

from .settings import settings

log = logging.getLogger(__name__)
API = "https://api.github.com"
CACHE_SECONDS = 15
transport: httpx.BaseTransport | None = None  # tests inject an httpx.MockTransport
_cache: dict = {"at": 0.0, "data": None}
_lock = threading.Lock()


def _headers() -> dict:
    h = {"Accept": "application/vnd.github+json", "User-Agent": "atlas-mission-control"}
    if settings().github_human_token:
        h["Authorization"] = f"Bearer {settings().github_human_token}"
    return h


def _client() -> httpx.Client:
    return httpx.Client(base_url=API, headers=_headers(), timeout=20, transport=transport)


def _ts(v: str | None) -> datetime | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return None


def _dur(a: str | None, b: str | None) -> float | None:
    x, y = _ts(a), _ts(b)
    if not x:
        return None
    return round(((y or datetime.now(UTC)) - x).total_seconds(), 1)


def _repo() -> str:
    s = settings()
    return f"/repos/{s.github_org}/{s.github_repo}"


def _shape_run(c: httpx.Client, run: dict) -> dict:
    jobs: list[dict] = []
    pending: list[dict] = []
    try:
        jr = c.get(f"{_repo()}/actions/runs/{run['id']}/jobs", params={"per_page": 30})
        if jr.status_code < 400:
            jobs = [
                {
                    "id": j["id"], "name": j["name"], "status": j["status"], "conclusion": j.get("conclusion"),
                    "started_at": j.get("started_at"), "completed_at": j.get("completed_at"),
                    "duration_seconds": _dur(j.get("started_at"), j.get("completed_at")) if j.get("started_at") else None,
                    "url": j.get("html_url"),
                }
                for j in jr.json().get("jobs", [])
            ]
    except httpx.HTTPError:
        log.warning("jobs fetch failed for run %s", run["id"])
    if run.get("status") in {"waiting", "in_progress", "queued", "pending"}:
        try:
            pr = c.get(f"{_repo()}/actions/runs/{run['id']}/pending_deployments")
            if pr.status_code < 400:
                pending = [
                    {"environment": (p.get("environment") or {}).get("name"), "environment_id": (p.get("environment") or {}).get("id"),
                     "wait_timer": p.get("wait_timer"), "current_user_can_approve": p.get("current_user_can_approve")}
                    for p in pr.json()
                ]
        except httpx.HTTPError:
            pass
    name = (run.get("name") or run.get("display_title") or "").lower()
    return {
        "id": run["id"], "name": run.get("name"), "title": run.get("display_title"),
        "workflow": "deploy" if "deploy" in (run.get("path") or "").lower() or name.startswith("deploy") else "ci",
        "status": run.get("status"), "conclusion": run.get("conclusion"), "event": run.get("event"),
        "branch": run.get("head_branch"), "sha": run.get("head_sha"), "actor": (run.get("actor") or {}).get("login"),
        "started_at": run.get("run_started_at") or run.get("created_at"), "updated_at": run.get("updated_at"),
        "duration_seconds": _dur(run.get("run_started_at") or run.get("created_at"), run.get("updated_at") if run.get("status") == "completed" else None),
        "url": run.get("html_url"), "attempt": run.get("run_attempt"), "jobs": jobs, "pending_deployments": pending,
    }


def _shape_pull(c: httpx.Client, pr: dict) -> dict:
    checks = {"total": 0, "success": 0, "failure": 0, "pending": 0}
    reviews: list[dict] = []
    try:
        cr = c.get(f"{_repo()}/commits/{pr['head']['sha']}/check-runs", params={"per_page": 50})
        if cr.status_code < 400:
            for run in cr.json().get("check_runs", []):
                checks["total"] += 1
                if run.get("status") != "completed":
                    checks["pending"] += 1
                elif run.get("conclusion") in {"success", "neutral", "skipped"}:
                    checks["success"] += 1
                else:
                    checks["failure"] += 1
        rr = c.get(f"{_repo()}/pulls/{pr['number']}/reviews", params={"per_page": 30})
        if rr.status_code < 400:
            reviews = [{"user": (r.get("user") or {}).get("login"), "state": r.get("state"), "at": r.get("submitted_at")} for r in rr.json()]
    except httpx.HTTPError:
        pass
    return {
        "number": pr["number"], "title": pr.get("title"), "url": pr.get("html_url"), "author": (pr.get("user") or {}).get("login"),
        "branch": (pr.get("head") or {}).get("ref"), "sha": (pr.get("head") or {}).get("sha"), "draft": pr.get("draft"),
        "created_at": pr.get("created_at"), "checks": checks, "reviews": reviews,
    }


def fetch(force: bool = False) -> dict:
    with _lock:
        if not force and _cache["data"] is not None and time.time() - _cache["at"] < CACHE_SECONDS:
            return _cache["data"]
        s = settings()
        out: dict = {
            "repo": f"{s.github_org}/{s.github_repo}", "url": f"https://github.com/{s.github_org}/{s.github_repo}",
            "fetched_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "authenticated": bool(s.github_human_token), "runs": [], "pulls": [], "deploying": None, "error": None,
        }
        try:
            with _client() as c:
                r = c.get(f"{_repo()}/actions/runs", params={"per_page": 10})
                r.raise_for_status()
                out["runs"] = [_shape_run(c, run) for run in r.json().get("workflow_runs", [])]
                p = c.get(f"{_repo()}/pulls", params={"state": "open", "per_page": 10})
                if p.status_code < 400:
                    out["pulls"] = [_shape_pull(c, pr) for pr in p.json()]
        except httpx.HTTPStatusError as e:
            out["error"] = f"GitHub {e.response.status_code}: {e.response.text[:160]}"
        except httpx.HTTPError as e:
            out["error"] = f"GitHub unreachable: {e}"
        out["deploying"] = next((r for r in out["runs"] if r["workflow"] == "deploy" and r["status"] != "completed"), None)
        _cache.update(at=time.time(), data=out)
        return out


def approve_run(run_id: int) -> dict:
    """Approve every pending environment deployment on a run, as the human."""
    from .github_human import HumanGitHub

    gh = HumanGitHub()
    pending = gh.pending_deployments(run_id)
    ids = [p["environment"]["id"] for p in pending if p.get("environment")]
    if not ids:
        return {"ok": True, "approved": [], "note": "nothing pending on this run"}
    gh.approve_pending(run_id, ids, "Approved from Mission Control (CI/CD tab)")
    with _lock:
        _cache["at"] = 0.0
    return {"ok": True, "approved": ids}
