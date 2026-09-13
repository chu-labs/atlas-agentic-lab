from __future__ import annotations

from datetime import timedelta

from mission.state import State, normalise

from .script import HUMAN, PR, SCRIPT, T0, agent, ev


def test_pipeline_walks_the_script():
    st = State()
    followups = []
    for i, (expected, raw) in enumerate(SCRIPT, start=1):
        followups += st.apply(normalise(raw, event_id=i))
        rows = {r["ticket"]: r for r in st.snapshot()["pipeline"]}
        row = rows.get("ATLAS-142") or rows.get(None)
        assert row is not None, raw["detail-type"]
        assert row["stage"] == expected, f"after {raw['detail-type']} expected {expected}, got {row['stage']}"

    snap = st.snapshot()
    row = snap["pipeline"][0]
    assert row["ticket"] == "ATLAS-142" and row["closed"] is True
    assert row["title"] == "Null customer on invoice"
    # the pending error's timestamps were inherited by the ticket row
    assert row["stages"]["error"].startswith("2026-09-17T10:00:00")
    assert row["error"]["count"] == 2
    assert set(row["stages"]) == {"error", "triage", "ticket", "code", "test", "pr", "human_gate", "merge", "deploy", "verify", "closed"}
    # only one pending-error row was created and it was absorbed
    assert len(snap["pipeline"]) == 1
    # the gate was raised once, then released by the human
    assert [f[0] for f in followups] == ["human.gate_waiting"]
    assert followups[0][1]["pr"]["number"] == 17
    assert snap["gate"]["waiting"] is False
    # nothing is active once the ticket is closed
    assert snap["active_ticket"] is None


def test_gate_and_telemetry_midway():
    st = State()
    for i, (_, raw) in enumerate(SCRIPT[:9], start=1):  # up to review.posted
        st.apply(normalise(raw, event_id=i))
    now = T0 + timedelta(seconds=180 + 102)
    snap = st.snapshot(now=now)
    assert snap["active_ticket"] == "ATLAS-142"
    assert snap["gate"]["waiting"] is True and snap["gate"]["pr"]["number"] == 17
    assert snap["gate"]["ticket"] == "ATLAS-142" and int(snap["gate"]["waited_seconds"]) == 102

    tel = snap["telemetry"]
    # max per agent, summed across agents: forge 12000 + scout 1000 + sentinel 4000
    assert tel["tokens_in"] == 17000
    assert tel["tokens_out"] == 2000 + 200 + 600
    assert tel["model_calls"] == 9 + 2 + 2
    assert abs(tel["usd"] - (0.12 + 0.01 + 0.03)) < 1e-9
    assert tel["error_to_pr_seconds"] == 120  # error at t=0, PR at t=120
    assert tel["error_to_closed_seconds"] == 282  # still open: measured to `now`
    assert tel["closed"] is False

    forge = next(c for c in snap["fleet"] if c["handle"] == "forge")
    assert forge["status"] == "working" and forge["thinking"] == "Opened PR #17"  # latest line wins
    assert forge["ticket"] == "ATLAS-142" and forge["authority"]["can_merge"] is False
    sentinel = next(c for c in snap["fleet"] if c["handle"] == "sentinel")
    assert sentinel["last_seen"] is not None


def test_changes_requested_goes_back_to_code_and_rework_returns():
    st = State()
    for i, (_, raw) in enumerate(SCRIPT[:8], start=1):  # up to pr.opened
        st.apply(normalise(raw, event_id=i))
    st.apply(normalise(ev("atlas.sentinel", "review.changes_requested", 150, agent("sentinel"), "ATLAS-142", "Changes requested", pr=PR)))
    assert st.rows["ATLAS-142"]["stage"] == "code"
    st.apply(normalise(ev("atlas.forge", "agent.status", 160, agent("forge"), "ATLAS-142", "pytest again", status="working", thinking="pytest -q")))
    assert st.rows["ATLAS-142"]["stage"] == "test"
    st.apply(normalise(ev("atlas.forge", "pr.updated", 170, agent("forge"), "ATLAS-142", "Pushed rework", pr=PR)))
    assert st.rows["ATLAS-142"]["stage"] == "pr"
    st.apply(normalise(ev("atlas.sentinel", "review.posted", 180, agent("sentinel"), "ATLAS-142", "ok", pr=PR)))
    assert st.rows["ATLAS-142"]["stage"] == "human_gate" and st.gate["waiting"]
    st.apply(normalise(ev("atlas.mission-control", "human.rejected", 200, HUMAN, "ATLAS-142", "no", pr=PR, reason="no")))
    assert st.rows["ATLAS-142"]["stage"] == "code" and not st.gate["waiting"]


def test_escalation_is_terminal_and_teammates_come_and_go():
    st = State()
    for i, (_, raw) in enumerate(SCRIPT[:6], start=1):
        st.apply(normalise(raw, event_id=i))
    st.apply(normalise(ev("atlas.forge", "escalation.raised", 70, agent("forge"), "ATLAS-142", "Refused: business rule change", category="business_rule_change", assigned_to="tom")))
    row = st.snapshot()["pipeline"][0]
    assert row["escalated"] is True and row["escalation"]["category"] == "business_rule_change"
    assert next(c for c in st.snapshot()["fleet"] if c["handle"] == "forge")["status"] == "escalated"

    st.apply(normalise(ev("atlas.workbench", "teammate.spawned", 80, None, "ATLAS-142", "Spawned tester", role="tester", worktree="wt/tester")))
    cards = {c["handle"]: c for c in st.snapshot()["fleet"]}
    assert cards["teammate:tester"]["mode"] == "supervised" and cards["teammate:tester"]["authority"]["can_merge"] is False
    st.apply(normalise(ev("atlas.workbench", "teammate.finished", 90, None, "ATLAS-142", "Tester done", role="tester")))
    assert "teammate:tester" not in {c["handle"] for c in st.snapshot()["fleet"]}
    assert len(st.snapshot()["fleet"]) == 5
