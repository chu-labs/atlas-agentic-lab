from __future__ import annotations

import json
from datetime import timedelta

import httpx

from mission import board_proxy, cicd, dora
from mission.state import State, normalise

from .script import PR, SCRIPT, T0, agent, ev

SIG = "/api/renewals/reconcile:BusinessRuleViolation"


def _err(sec: float, msg: str) -> dict:
    return ev("atlas.platform", "error.raised", sec, None, None, "422", kind="business_rule", signature=SIG,
              endpoint="/api/renewals/reconcile", method="POST", status_code=422, error_type="BusinessRuleViolation", message=msg)


def test_observing_row_becomes_the_ticket_row_in_place():
    st = State()
    now = T0 + timedelta(seconds=30)
    assert st.snapshot(now=now)["pipeline"] == []
    st.apply(normalise(_err(0, "2 policies missing from the 14-day run")))
    st.apply(normalise(_err(3, "9 policies missing from the 60-day run")))
    rows = st.snapshot(now=now)["pipeline"]
    assert len(rows) == 1 and rows[0]["observing"] is True and rows[0]["ticket"] is None
    assert rows[0]["stage"] == "error" and rows[0]["error"]["count"] == 2 and rows[0]["signature"] == SIG
    assert rows[0]["title"] == "9 policies missing from the 60-day run"  # latest message of the dominant signature
    assert rows[0]["stages"]["error"].startswith("2026-09-17T10:00:00")
    # Scout starts working: Triage lights up on the same row
    st.apply(normalise(ev("atlas.scout", "agent.status", 5, agent("scout"), None, "assessing", status="working", thinking="assessing")))
    rows = st.snapshot(now=now)["pipeline"]
    assert rows[0]["observing"] and rows[0]["stage"] == "triage" and rows[0]["stages"]["triage"].startswith("2026-09-17T10:00:05")
    # the ticket opens: same signature, now a real row, no observing row left
    st.apply(normalise(ev("atlas.scout", "incident.opened", 10, agent("scout"), "ATLAS-37", "Opened ATLAS-37",
                          incident={"signature": SIG, "count": 2}, issue={"key": "ATLAS-37", "title": "Reconcile drops policies"})))
    snap = st.snapshot(now=now)
    assert [r["ticket"] for r in snap["pipeline"]] == ["ATLAS-37"]
    row = snap["pipeline"][0]
    assert row["observing"] is False and row["signature"] == SIG and row["error"]["count"] == 2
    assert row["stages"]["error"].startswith("2026-09-17T10:00:00") and row["stages"]["triage"].startswith("2026-09-17T10:00:05")
    assert snap["signal"]["last_error_ts"].startswith("2026-09-17T10:00:03")


def test_dora_maths_on_the_scripted_incident():
    st = State()
    for i, (_, raw) in enumerate(SCRIPT, start=1):
        st.apply(normalise(raw, event_id=i))
    # a second ticket that deployed but failed verification
    st.apply(normalise(ev("atlas.scout", "incident.opened", 1000, agent("scout"), "ATLAS-143", "Opened", incident={"signature": "sig-9"}, issue={"key": "ATLAS-143", "title": "Other"})))
    st.apply(normalise(ev("atlas.forge", "pr.opened", 1100, agent("forge"), "ATLAS-143", "PR", pr={**PR, "number": 18})))
    st.apply(normalise(ev("atlas.sentinel", "review.posted", 1150, agent("sentinel"), "ATLAS-143", "ok", pr={**PR, "number": 18})))
    st.apply(normalise(ev("atlas.mission-control", "human.approved", 1200, {"handle": "maroun", "kind": "human", "display_name": "Maroun", "mode": None}, "ATLAS-143", "ok", pr={**PR, "number": 18})))
    st.apply(normalise(ev("atlas.github", "deploy.completed", 1400, None, "ATLAS-143", "deployed", sha="def")))
    st.apply(normalise(ev("atlas.conductor", "verify.failed", 1500, agent("conductor"), "ATLAS-143", "failed", smoke={"ok": False})))

    now = T0 + timedelta(hours=1)
    d = dora.compute(st, "24h", now=now)
    assert d["deployment_frequency"] == {"count": 2, "per_day": 2.0}
    # ATLAS-142: pr 120 -> deploy 420 = 300 s; ATLAS-143: pr 1100 -> deploy 1400 = 300 s
    assert d["lead_time"]["median_seconds"] == 300 and d["lead_time"]["samples"] == 2
    assert d["change_failure_rate"] == {"failures": 1, "deploys": 2, "rate": 0.5}
    # only ATLAS-142 restored: error 0 -> verify 480
    assert d["time_to_restore"]["median_seconds"] == 480 and d["time_to_restore"]["samples"] == 1
    t142 = next(t for t in d["tickets"] if t["ticket"] == "ATLAS-142")
    assert (t142["error_to_pr"], t142["pr_to_deploy"], t142["deploy_to_verified"], t142["total"]) == (120, 300, 60, 490)
    assert abs(t142["usd"] - 0.165) < 1e-9 and t142["closed"] is True
    assert len(d["trend"]) == 24 and sum(b["deploys"] for b in d["trend"]) == 2
    # the 7-day window normalises per day
    assert dora.compute(st, "7d", now=now)["deployment_frequency"]["per_day"] == round(2 / 7, 3)
    # outside the window nothing counts
    assert dora.compute(st, "24h", now=now + timedelta(days=3))["deployment_frequency"]["count"] == 0


def test_board_proxy_acts_as_the_human(client, monkeypatch):
    from mission.settings import settings

    monkeypatch.setattr(settings(), "board_url", "http://board.test")
    monkeypatch.setattr(settings(), "github_human_login", "maroun")
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        if req.method == "GET" and req.url.path == "/api/issues":
            return httpx.Response(200, json=[{"key": "ATLAS-1", "title": "x", "status": "Backlog"}])
        if req.method == "PATCH" and req.url.path == "/api/issues/ATLAS-1":
            return httpx.Response(200, json={"key": "ATLAS-1", "assignee": json.loads(req.content)["assignee"]})
        if req.method == "POST" and req.url.path == "/api/issues":
            body = json.loads(req.content)
            return httpx.Response(201, json={"key": "ATLAS-2", **body})
        if req.method == "POST" and req.url.path == "/api/issues/ATLAS-1/transition":
            return httpx.Response(422, json={"detail": "transition not allowed"})
        return httpx.Response(404, json={"detail": "nope"})

    monkeypatch.setattr(board_proxy, "transport", httpx.MockTransport(handler))
    assert client.get("/api/board/issues").json()[0]["key"] == "ATLAS-1"
    assert seen[-1].headers["x-actor"] == "maroun"
    r = client.post("/api/board/issues/ATLAS-1/assign", json={"handle": "forge"})
    assert r.status_code == 200 and r.json()["assignee"] == "forge" and seen[-1].method == "PATCH"
    r = client.post("/api/board/issues", json={"title": "Add CSV export", "type": "Story", "priority": "High", "assignee": "forge"})
    assert r.status_code == 201 and r.json()["key"] == "ATLAS-2" and json.loads(seen[-1].content)["assignee"] == "forge"
    r = client.post("/api/board/issues/ATLAS-1/transition", json={"status": "Done"})
    assert r.status_code == 422 and "transition not allowed" in r.json()["detail"]
    monkeypatch.setattr(settings(), "board_url", "")
    assert client.get("/api/board/issues").status_code == 503


def test_cicd_shapes_runs_and_degrades(client, monkeypatch):
    def handler(req: httpx.Request) -> httpx.Response:
        p = req.url.path
        if p.endswith("/actions/runs"):
            return httpx.Response(200, json={"workflow_runs": [
                {"id": 1, "name": "deploy", "path": ".github/workflows/deploy.yml", "status": "waiting", "conclusion": None, "event": "push",
                 "head_branch": "main", "head_sha": "abc", "actor": {"login": "maroun"}, "run_started_at": "2026-09-17T10:00:00Z",
                 "updated_at": "2026-09-17T10:01:00Z", "html_url": "https://github.com/x/y/actions/runs/1", "run_attempt": 1},
                {"id": 2, "name": "ci", "path": ".github/workflows/ci.yml", "status": "completed", "conclusion": "success", "event": "pull_request",
                 "head_branch": "forge/x", "head_sha": "def", "actor": {"login": "atlas-agents[bot]"}, "run_started_at": "2026-09-17T09:00:00Z",
                 "updated_at": "2026-09-17T09:03:00Z", "html_url": "u", "run_attempt": 1},
            ]})
        if p.endswith("/runs/1/jobs") or p.endswith("/runs/2/jobs"):
            return httpx.Response(200, json={"jobs": [{"id": 9, "name": "test", "status": "completed", "conclusion": "success",
                                                        "started_at": "2026-09-17T10:00:00Z", "completed_at": "2026-09-17T10:00:40Z", "html_url": "j"}]})
        if p.endswith("/runs/1/pending_deployments"):
            return httpx.Response(200, json=[{"environment": {"id": 5, "name": "production"}, "wait_timer": 0, "current_user_can_approve": True}])
        if p.endswith("/pulls"):
            return httpx.Response(200, json=[{"number": 17, "title": "Fix", "html_url": "p", "user": {"login": "atlas-agents[bot]"},
                                              "head": {"ref": "forge/x", "sha": "def"}, "draft": False, "created_at": "2026-09-17T09:00:00Z"}])
        if "/check-runs" in p:
            return httpx.Response(200, json={"check_runs": [{"status": "completed", "conclusion": "success"}, {"status": "in_progress"}]})
        if p.endswith("/reviews"):
            return httpx.Response(200, json=[{"user": {"login": "sentinel"}, "state": "COMMENTED", "submitted_at": "2026-09-17T09:05:00Z"}])
        return httpx.Response(404)

    monkeypatch.setattr(cicd, "transport", httpx.MockTransport(handler))
    d = client.get("/api/cicd", params={"refresh": "true"}).json()
    assert [r["workflow"] for r in d["runs"]] == ["deploy", "ci"]
    assert d["runs"][0]["pending_deployments"][0]["environment"] == "production" and d["deploying"]["id"] == 1
    assert d["runs"][1]["duration_seconds"] == 180 and d["runs"][1]["jobs"][0]["duration_seconds"] == 40
    assert d["pulls"][0]["checks"] == {"total": 2, "success": 1, "failure": 0, "pending": 1} and d["pulls"][0]["reviews"][0]["user"] == "sentinel"
    # unreachable GitHub degrades to an empty, explained view
    monkeypatch.setattr(cicd, "transport", httpx.MockTransport(lambda req: (_ for _ in ()).throw(httpx.ConnectError("down"))))
    d = client.get("/api/cicd", params={"refresh": "true"}).json()
    assert d["runs"] == [] and "unreachable" in d["error"]
    assert client.post("/api/cicd/runs/1/approve").status_code == 503  # no human token in tests


def test_system_degrades_locally(client):
    d = client.get("/api/system").json()
    assert d["region"] and [s["name"] for s in d["services"]] == ["mission-control", "atlas-board", "atlas-platform"]
