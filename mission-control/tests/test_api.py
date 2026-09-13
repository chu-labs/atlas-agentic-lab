from __future__ import annotations

import time

from mission.api.auth import make_ws_token, verify_ws_token

from .script import SCRIPT


def test_health_open_and_state_seeded(client, monkeypatch):
    from mission.settings import settings

    assert client.get("/health").status_code == 200
    state = client.get("/api/state").json()
    assert [c["handle"] for c in state["fleet"]] == ["scout", "forge", "sentinel", "conductor", "watchtower"]
    assert all(c["authority"]["can_merge"] is False for c in state["fleet"])
    assert state["baselines"]["human_days_error_to_pr"] == 3.5
    assert state["gate"]["waiting"] is False and state["pipeline"] == []

    monkeypatch.setattr(settings(), "basic_auth_user", "u")
    monkeypatch.setattr(settings(), "basic_auth_pass", "p")
    assert client.get("/health").status_code == 200
    assert client.get("/api/state").status_code == 401
    assert client.get("/api/state", auth=("u", "p")).status_code == 200


def test_inject_walks_pipeline_and_persists(client):
    for expected, raw in SCRIPT[:9]:
        r = client.post("/api/admin/inject", json=raw)
        assert r.status_code == 201, r.text
        state = client.get("/api/state").json()
        if expected in {"error", "triage"}:
            assert state["pipeline"] == [] and state["signal"]["untracked_count"] >= 1
            continue
        assert state["pipeline"][0]["stage"] == expected
    state = client.get("/api/state").json()
    assert state["gate"]["waiting"] is True and state["active_ticket"] == "ATLAS-142"
    # the dashboard emitted human.gate_waiting into its own timeline (no bus configured)
    events = client.get("/api/events", params={"after": 0}).json()
    types = [e["detail_type"] for e in events]
    assert types[-1] == "human.gate_waiting" and events[-1]["source"] == "atlas.mission-control"
    assert len(events) == 10

    # a restart rebuilds the same state from the database
    from mission.hub import hub

    hub().state.reset()
    assert client.get("/api/state").json()["pipeline"] == []
    assert hub().rebuild() == 10
    again = client.get("/api/state").json()
    assert again["pipeline"][0]["stage"] == "human_gate" and again["gate"]["waiting"] is True
    assert again["telemetry"]["tokens_in"] == 17000


def test_recording_round_trip(client):
    for _, raw in SCRIPT[:4]:
        client.post("/api/admin/inject", json=raw)
    last = client.get("/api/state").json()["last_event_id"]
    for _, raw in SCRIPT[4:8]:
        client.post("/api/admin/inject", json=raw)
    r = client.post("/api/recordings", json={"name": "t-rec", "since_event_id": last})
    assert r.status_code == 201 and r.json()["count"] == 4
    assert [x["name"] for x in client.get("/api/recordings").json()] == ["t-rec"]

    client.post("/api/admin/reset")
    assert client.get("/api/state").json()["pipeline"] == []
    assert client.get("/api/recordings").json()[0]["name"] == "t-rec"  # reset keeps recordings

    r = client.post("/api/replay", json={"name": "t-rec", "speed": 1000})
    assert r.status_code == 202 and r.json()["events"] == 4
    deadline = time.time() + 10
    events = []
    while time.time() < deadline and len(events) < 4:
        time.sleep(0.1)
        events = client.get("/api/events").json()
    assert [e["detail_type"] for e in events] == ["branch.created", "agent.status", "agent.status", "pr.opened"]
    assert all(e["replay"] is True for e in events)
    assert client.get("/api/state").json()["pipeline"][0]["stage"] == "pr"
    assert client.get("/api/state").json()["replaying"] is True
    assert client.delete("/api/recordings/t-rec").status_code == 200
    assert client.delete("/api/recordings/t-rec").status_code == 404


def test_ws_token_validation(client):
    tok = client.get("/api/ws-token").json()["token"]
    assert verify_ws_token(tok)
    assert not verify_ws_token(tok + "x")
    assert not verify_ws_token("garbage")
    assert not verify_ws_token(None)
    assert not verify_ws_token(make_ws_token(ttl=-1))
    exp, _, _ = tok.partition(".")
    assert not verify_ws_token(f"{int(exp) + 1}.{tok.partition('.')[2]}")  # tampered expiry

    with client.websocket_connect(f"/ws?token={tok}") as ws:
        first = ws.receive_json()
        assert first["type"] == "state" and len(first["fleet"]) == 5
        client.post("/api/admin/inject", json=SCRIPT[0][1])
        msg = ws.receive_json()
        assert msg["type"] == "event" and msg["event"]["detail_type"] == "error.raised"
        assert ws.receive_json()["type"] == "state"


def test_ws_rejects_bad_token(client):
    from starlette.websockets import WebSocketDisconnect

    try:
        with client.websocket_connect("/ws?token=nope") as ws:
            ws.receive_text()
        raise AssertionError("expected the socket to be closed")
    except WebSocketDisconnect as e:
        assert e.code == 4401


def test_gate_without_token_is_503(client):
    r = client.post("/api/gate/approve", json={"pr": 17})
    assert r.status_code == 503 and "GITHUB_HUMAN_TOKEN" in r.json()["detail"]
    r = client.post("/api/gate/reject", json={"pr": 17, "reason": "nope"})
    assert r.status_code == 503


def test_recording_upload_and_download(client):
    events = [{"source": "atlas.scout", "detail-type": "agent.status", "time": "2026-09-13T04:00:00Z", "detail": {"summary": "hi", "actor": {"handle": "scout", "kind": "agent"}}}]
    r = client.post("/api/recordings", json={"name": "up", "events": events})
    assert r.status_code == 201
    got = client.get("/api/recordings/up").json()
    assert got["name"] == "up" and len(got["events"]) == 1
