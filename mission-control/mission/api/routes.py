"""HTTP routes. Thin: read the hub, or ask it to do one thing, and return JSON."""
from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, HTTPException, Query

from .. import board_proxy, cicd, dora, system
from ..bus import envelope, human_actor, publish
from ..db import repo
from ..db.pool import conn
from ..github_human import HumanGitHub
from ..hub import hub
from ..settings import settings
from .auth import WS_TOKEN_TTL, make_ws_token
from .schemas import (
    AssignIn,
    BoardIssueIn,
    GateApproveIn,
    GateRejectIn,
    InjectIn,
    RecordingIn,
    ReplayIn,
    TransitionIn,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


# ---------------------------------------------------------------- state / events


@router.get("/state")
def get_state():
    s = settings()
    return {
        **hub().snapshot(),
        "links": {"board": s.board_url, "platform": s.platform_url, "github": f"https://github.com/{s.github_org}/{s.github_repo}"},
        "human": {"login": s.github_human_login, "display_name": s.github_human_display_name, "configured": bool(s.github_human_token)},
    }


@router.get("/events")
def get_events(after: int = Query(0, ge=0), limit: int = Query(500, ge=1, le=2000)):
    with conn() as c:
        rows = repo.events_after(c, after, limit)
    return [repo.serialise_event(r) for r in rows]


@router.get("/ws-token")
def ws_token():
    return {"token": make_ws_token(), "ttl": WS_TOKEN_TTL}


# ---------------------------------------------------------------- the human gate


def _gh_or_503() -> HumanGitHub:
    gh = HumanGitHub()
    if not gh.configured:
        raise HTTPException(503, "GITHUB_HUMAN_TOKEN is not set: Mission Control cannot act as the human on GitHub")
    return gh


def _gate_context(pr: int) -> tuple[str | None, dict | None, float]:
    snap = hub().snapshot()
    gate = snap["gate"]
    if gate.get("pr") and gate["pr"].get("number") == pr:
        return gate.get("ticket"), gate["pr"], float(gate.get("waited_seconds") or 0)
    for row in snap["pipeline"]:
        if row.get("pr") and row["pr"].get("number") == pr:
            return row["ticket"], row["pr"], 0.0
    return None, {"number": pr}, 0.0


@router.post("/gate/approve")
def gate_approve(body: GateApproveIn):
    gh = _gh_or_503()
    ticket, pr, waited = _gate_context(body.pr)
    try:
        sha = gh.approve_and_merge(body.pr)
    except httpx.HTTPStatusError as e:
        raise HTTPException(502, f"GitHub refused: {e.response.status_code} {e.response.text[:200]}") from e
    except httpx.HTTPError as e:
        raise HTTPException(502, f"GitHub unreachable: {e}") from e
    publish(
        "human.approved",
        envelope(
            human_actor(), ticket,
            f"{settings().github_human_display_name} approved and merged PR #{body.pr} after waiting {int(waited)}s",
            pr={**pr, "merge_sha": sha}, waited_seconds=int(waited),
        ),
    )
    return {"ok": True, "pr": body.pr, "ticket": ticket, "merge_sha": sha, "waited_seconds": int(waited)}


@router.post("/gate/reject")
def gate_reject(body: GateRejectIn):
    gh = _gh_or_503()
    ticket, pr, waited = _gate_context(body.pr)
    try:
        gh.reject(body.pr, body.reason)
    except httpx.HTTPStatusError as e:
        raise HTTPException(502, f"GitHub refused: {e.response.status_code} {e.response.text[:200]}") from e
    except httpx.HTTPError as e:
        raise HTTPException(502, f"GitHub unreachable: {e}") from e
    publish(
        "human.rejected",
        envelope(
            human_actor(), ticket,
            f"{settings().github_human_display_name} rejected PR #{body.pr}: {body.reason[:140]}",
            pr=pr, reason=body.reason, waited_seconds=int(waited),
        ),
    )
    return {"ok": True, "pr": body.pr, "ticket": ticket, "waited_seconds": int(waited)}


# ---------------------------------------------------------------- recordings / replay


@router.get("/recordings")
def list_recordings():
    with conn() as c:
        return [repo.serialise_event(r) for r in repo.list_recordings(c)]


@router.post("/recordings", status_code=201)
def save_recording(body: RecordingIn):
    if body.events is not None:
        with conn() as c:
            return repo.serialise_event(repo.save_recording(c, body.name, body.events))
    return hub().record(body.name, body.since_event_id)


@router.get("/recordings/{name}")
def get_recording(name: str):
    with conn() as c:
        rec = repo.get_recording(c, name)
    if not rec:
        raise HTTPException(404, f"no recording named {name}")
    return repo.serialise_event(rec)


@router.delete("/recordings/{name}")
def delete_recording(name: str):
    with conn() as c:
        if not repo.delete_recording(c, name):
            raise HTTPException(404, f"no recording named {name}")
    return {"ok": True}


@router.post("/replay", status_code=202)
def replay(body: ReplayIn):
    try:
        n = hub().replay(body.name, body.speed)
    except KeyError as e:
        raise HTTPException(404, f"no recording named {body.name}") from e
    return {"ok": True, "name": body.name, "speed": body.speed, "events": n}


# ---------------------------------------------------------------- admin


@router.post("/admin/reset")
def admin_reset():
    hub().reset()
    return {"ok": True}


@router.post("/admin/inject", status_code=201)
def admin_inject(body: InjectIn):
    out = [hub().ingest(raw) for raw in body.as_events()]
    return {"ok": True, "ingested": len(out), "last_event_id": out[-1]["id"] if out else None}


# ---------------------------------------------------------------- board (proxied to atlas-board as the human)


@router.get("/board/issues")
def board_issues(limit: int = Query(200, ge=1, le=1000)):
    return board_proxy.list_issues(limit)


@router.get("/board/users")
def board_users():
    return board_proxy.list_users()


@router.get("/board/issues/{key}")
def board_issue(key: str):
    return board_proxy.get_issue(key)


@router.post("/board/issues", status_code=201)
def board_create(body: BoardIssueIn):
    return board_proxy.create_issue(body.model_dump(exclude_none=True))


@router.post("/board/issues/{key}/assign")
def board_assign(key: str, body: AssignIn):
    return board_proxy.assign(key, body.handle)


@router.post("/board/issues/{key}/transition")
def board_transition(key: str, body: TransitionIn):
    return board_proxy.transition(key, body.status, body.body)


# ---------------------------------------------------------------- CI/CD, DORA, system


@router.get("/cicd")
def get_cicd(refresh: bool = False):
    return cicd.fetch(force=refresh)


@router.post("/cicd/runs/{run_id}/approve")
def approve_run(run_id: int):
    _gh_or_503()
    try:
        return cicd.approve_run(run_id)
    except httpx.HTTPStatusError as e:
        raise HTTPException(502, f"GitHub refused: {e.response.status_code} {e.response.text[:200]}") from e
    except httpx.HTTPError as e:
        raise HTTPException(502, f"GitHub unreachable: {e}") from e


@router.get("/dora")
def get_dora(window: str = Query("7d", pattern="^(24h|7d|all)$")):
    return {**dora.compute(hub().state, window), "baselines": settings().baselines.get("dora", {})}


@router.get("/system")
def get_system():
    return system.fetch()
