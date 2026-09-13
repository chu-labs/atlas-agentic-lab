FORGE = {"X-Actor": "forge"}
SCOUT = {"X-Actor": "scout"}


def _create(client, **over):
    body = {
        "type": "Bug",
        "title": "Test bug",
        "description": "## Repro\n\nsteps",
        "priority": "High",
        "labels": ["test"],
        "status": "Triage",
    }
    body.update(over)
    r = client.post("/api/issues", json=body, headers=SCOUT)
    assert r.status_code == 201, r.text
    return r.json()


def test_health_is_open(client, monkeypatch):
    from board.settings import settings

    r = client.get("/health")
    assert r.status_code == 200 and r.json()["db"] is True
    monkeypatch.setattr(settings(), "basic_auth_user", "u")
    monkeypatch.setattr(settings(), "basic_auth_pass", "p")
    assert client.get("/health").status_code == 200
    assert client.get("/api/stats").status_code == 401
    assert client.get("/api/stats", auth=("u", "p")).status_code == 200


def test_create_list_get(client, events):
    issue = _create(client, assignee="forge")
    assert issue["key"].startswith("ATLAS-") and issue["reporter"]["handle"] == "scout"
    assert issue["assignee"]["handle"] == "forge" and issue["sprint"]["state"] == "active"
    assert [e[0] for e in events] == ["issue.created", "issue.assigned"]
    detail = events[0][1]
    assert detail["actor"]["handle"] == "scout" and detail["ticket"] == issue["key"]
    assert detail["issue"]["assignee"] == "forge" and "summary" in detail and "ts" in detail
    assert detail["authority"]["can_read_production_telemetry"] is True

    listed = client.get("/api/issues", params={"assignee": "forge", "q": "Test bug"}).json()
    assert listed[0]["key"] == issue["key"]  # newest first

    full = client.get(f"/api/issues/{issue['key']}").json()
    assert [a["kind"] for a in full["activity"]] == ["created", "assigned"]
    assert full["counts"]["created"] == 1


def test_unknown_actor_is_404_and_missing_actor_is_400(client):
    r = client.post("/api/issues", json={"type": "Task", "title": "x"}, headers={"X-Actor": "nobody"})
    assert r.status_code == 404
    r = client.post("/api/issues", json={"type": "Task", "title": "x"})
    assert r.status_code == 400
    # actor in the body works too
    r = client.post("/api/issues", json={"type": "Task", "title": "x", "actor": "tom"})
    assert r.status_code == 201 and r.json()["reporter"]["handle"] == "tom"


def test_transition_flow_is_validated(client, events):
    key = _create(client)["key"]
    bad = client.post(f"/api/issues/{key}/transition", json={"status": "Done"}, headers=FORGE)
    assert bad.status_code == 422 and "allowed" in bad.json()["detail"]
    same = client.post(f"/api/issues/{key}/transition", json={"status": "Triage"}, headers=FORGE)
    assert same.status_code == 409
    for nxt in ["In Progress", "In Review", "Done"]:
        r = client.post(f"/api/issues/{key}/transition", json={"status": nxt}, headers=FORGE)
        assert r.status_code == 200 and r.json()["status"] == nxt
    assert r.json()["resolved_at"] is not None
    # reopen, send back, and back to backlog from anywhere
    assert client.post(f"/api/issues/{key}/transition", json={"status": "In Progress"}, headers=FORGE).status_code == 200
    assert client.post(f"/api/issues/{key}/transition", json={"status": "In Review"}, headers=FORGE).status_code == 200
    assert client.post(f"/api/issues/{key}/transition", json={"status": "In Progress"}, headers=FORGE).status_code == 200
    r = client.post(f"/api/issues/{key}/transition", json={"status": "Backlog"}, headers=FORGE)
    assert r.status_code == 200 and r.json()["resolved_at"] is None
    trans = [d for t, d in events if t == "issue.transitioned"]
    assert trans[0]["from"] == "Triage" and trans[0]["to"] == "In Progress"
    assert trans[0]["actor"]["mode"] == "supervised"


def test_comment_and_reasoning(client, events):
    key = _create(client)["key"]
    r = client.post(f"/api/issues/{key}/comments", json={"body": "Opened PR #99\n\nmore"}, headers=FORGE)
    assert r.status_code == 201
    r = client.post(f"/api/issues/{key}/reasoning", json={"body": "Reading CLAUDE.md…"}, headers=FORGE)
    assert r.status_code == 201
    full = r.json()
    assert [a["kind"] for a in full["activity"]] == ["created", "commented", "reasoning"]
    assert full["counts"]["commented"] == 1 and full["counts"]["reasoning"] == 1
    assert len(full["comments"]) == 1
    assert [t for t, _ in events] == ["issue.created", "issue.commented"]  # reasoning emits nothing
    assert events[1][1]["summary"].startswith(f"Commented on {key}: Opened PR #99")


def test_patch_records_changes_and_emits(client, events):
    key = _create(client)["key"]
    events.clear()
    r = client.patch(
        f"/api/issues/{key}",
        json={"priority": "Highest", "pr_url": "https://github.com/chu-labs/atlas-platform/pull/1", "assignee": "forge"},
        headers=FORGE,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["priority"] == "Highest" and body["assignee"]["handle"] == "forge"
    kinds = [a["kind"] for a in body["activity"]]
    assert kinds.count("field_changed") == 2 and "assigned" in kinds
    assert [t for t, _ in events] == ["issue.assigned", "issue.updated"]
    assert set(events[1][1]["fields"]) == {"priority", "pr_url"}
    assert client.patch(f"/api/issues/{key}", json={}, headers=FORGE).status_code == 400


def test_escalate(client, events):
    key = _create(client, assignee="forge")["key"]
    client.post(f"/api/issues/{key}/transition", json={"status": "In Progress"}, headers=FORGE)
    events.clear()
    r = client.post(
        f"/api/issues/{key}/escalate",
        json={"body": "This asks for a different business outcome. Needs an underwriting decision.", "to": "alex"},
        headers=FORGE,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "Triage" and body["assignee"]["handle"] == "alex"
    esc = [a for a in body["activity"] if a["kind"] == "escalated"][0]
    assert esc["from_value"] == "forge" and esc["to_value"] == "alex"
    assert [t for t, _ in events] == ["issue.assigned", "issue.updated"]
    assert events[0][1]["escalation"] is True and events[0][1]["to"] == "alex"
    assert client.post(f"/api/issues/{key}/escalate", json={"body": "x", "to": "ghost"}, headers=FORGE).status_code == 404


def test_board_and_stats(client):
    b = client.get("/api/board").json()
    assert [c["status"] for c in b["columns"]] == ["Backlog", "Triage", "In Progress", "In Review", "Done"]
    assert b["sprint"]["name"] == "Sprint 15" and b["sprint"]["state"] == "active"
    assert sum(b["counts"].values()) == sum(len(c["issues"]) for c in b["columns"]) > 0
    s = client.get("/api/stats").json()
    assert s["total"] >= 34 and "Done" in s["by_status"]


def test_users_upsert(client):
    r = client.post(
        "/api/users",
        json={"handle": "forge", "display_name": "Forge", "kind": "agent", "avatar": "⚒️", "color": "#fb923c", "remit": "Engineering", "authority": {"can_merge": False}, "mode": "supervised"},
    )
    assert r.status_code == 201 and r.json()["authority"] == {"can_merge": False}
    assert len(client.get("/api/users").json()) == 9


def test_admin_reset_reseeds(client):
    _create(client, title="will be wiped")
    r = client.post("/api/admin/reset")
    assert r.status_code == 200 and r.json()["users"] == 9
    assert not client.get("/api/issues", params={"q": "will be wiped"}).json()


def test_unknown_issue_404(client):
    assert client.get("/api/issues/ATLAS-99999").status_code == 404
