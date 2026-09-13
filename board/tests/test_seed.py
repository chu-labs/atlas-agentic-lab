def test_seed_counts(db):
    assert db["users"] == 9
    assert db["sprints"] == 3
    assert 34 <= db["issues"] <= 38


def test_seed_shape(client):
    users = client.get("/api/users").json()
    assert {u["handle"] for u in users} == {
        "maroun", "priya", "tom", "alex", "scout", "forge", "sentinel", "conductor", "watchtower"
    }
    agents = [u for u in users if u["kind"] == "agent"]
    assert len(agents) == 5 and all(u["authority"] for u in agents)
    forge = next(u for u in agents if u["handle"] == "forge")
    assert forge["authority"]["can_write_code"] is True and forge["authority"]["can_merge"] is False

    sprints = client.get("/api/sprints").json()
    assert [s["state"] for s in sprints] == ["closed", "active", "future"]

    # Sprint 14 is all Done; at least 8 Done tickets carry the full agent history.
    s14 = client.get("/api/issues", params={"sprint": sprints[0]["id"]}).json()
    assert s14 and all(i["status"] == "Done" for i in s14)
    agent_fixed = client.get("/api/issues", params={"label": "agent-fixed", "status": "Done"}).json()
    assert len(agent_fixed) >= 8
    detail = client.get(f"/api/issues/{agent_fixed[0]['key']}").json()
    kinds = {a["kind"] for a in detail["activity"]}
    actors = {a["actor"]["handle"] for a in detail["activity"]}
    assert {"created", "reasoning", "commented", "transitioned"} <= kinds
    assert {"scout", "forge", "sentinel", "maroun", "conductor"} <= actors
    assert detail["pr_url"].startswith("https://github.com/chu-labs/atlas-platform/pull/")

    incidents = client.get("/api/issues", params={"type": "Incident"}).json()
    assert len(incidents) == 1 and incidents[0]["assignee"]["handle"] == "watchtower"


def test_first_issue_exists(client):
    assert client.get("/api/issues/ATLAS-1").status_code == 200
