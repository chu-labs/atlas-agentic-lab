from __future__ import annotations

from datetime import timedelta

from mission.state import State, normalise

from .script import HUMAN, PR, SCRIPT, T0, agent, ev


def tickets(snap: dict) -> list[dict]:
    """Ticket rows only: the observing row (errors, no ticket yet) is exercised in test_v3."""
    return [r for r in snap["pipeline"] if not r.get("observing")]


def test_pipeline_walks_the_script():
    st = State()
    followups = []
    for i, (expected, raw) in enumerate(SCRIPT, start=1):
        followups += st.apply(normalise(raw, event_id=i))
        snap = st.snapshot(now=T0 + timedelta(seconds=600))
        if expected in {"error", "triage"}:
            # errors never make a pipeline row: they live in the production signal until a ticket claims them
            assert tickets(snap) == [], raw["detail-type"]
            assert snap["signal"]["untracked_count"] == min(i, 2) and snap["signal"]["latest"]["signature"] == "sig-1"
            assert (snap["signal"]["triage_since"] is not None) == (expected == "triage")
            continue
        row = tickets(snap)[0]
        assert row["ticket"] == "ATLAS-142"
        assert row["stage"] == expected, f"after {raw['detail-type']} expected {expected}, got {row['stage']}"

    snap = st.snapshot()
    row = tickets(snap)[0]
    assert row["ticket"] == "ATLAS-142" and row["closed"] is True
    assert row["title"] == "Null customer on invoice"
    # the pending error's timestamps were inherited by the ticket row
    assert row["stages"]["error"].startswith("2026-09-17T10:00:00")
    assert row["error"]["count"] == 2 and row["error"]["first_seen"].startswith("2026-09-17T10:00:00")
    assert row["stages"]["triage"].startswith("2026-09-17T10:00:05")  # Scout started working at t=5
    assert set(row["stages"]) == {"error", "triage", "ticket", "code", "test", "pr", "human_gate", "merge", "deploy", "verify", "closed"}
    assert len(tickets(snap)) == 1 and snap["signal"]["untracked_count"] == 0
    # derived durations: triage 0-20, code 40-120, review 120-180, gate 180-300, deploy 300-420, verify 420-490
    d = row["durations"]
    assert d["segments"] == {"triage": 20, "code": 80, "review": 60, "gate": 120, "deploy": 120, "verify": 70}
    assert d["total"] == 490 and d["human"] == 120 and d["machine"] == 370
    assert d["open_segment"] is None and d["frozen"] is True
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

    d = tickets(snap)[0]["durations"]
    assert d["open_segment"] == "gate" and d["segments"]["gate"] == 102  # waiting on the human right now
    assert d["segments"]["review"] == 60 and d["total"] == 282 and d["human"] == 102 and d["machine"] == 180

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
    row = tickets(st.snapshot())[0]
    assert row["escalated"] is True and row["escalation"]["category"] == "business_rule_change"
    assert next(c for c in st.snapshot()["fleet"] if c["handle"] == "forge")["status"] == "escalated"

    st.apply(normalise(ev("atlas.workbench", "teammate.spawned", 80, None, "ATLAS-142", "Spawned tester", role="tester", worktree="wt/tester")))
    cards = {c["handle"]: c for c in st.snapshot()["fleet"]}
    assert cards["teammate:tester"]["mode"] == "supervised" and cards["teammate:tester"]["authority"]["can_merge"] is False
    st.apply(normalise(ev("atlas.workbench", "teammate.finished", 90, None, "ATLAS-142", "Tester done", role="tester")))
    assert "teammate:tester" not in {c["handle"] for c in st.snapshot()["fleet"]}
    assert len(st.snapshot()["fleet"]) == 5


def test_repeat_errors_count_on_the_open_ticket_not_a_new_row():
    st = State()
    for i, (_, raw) in enumerate(SCRIPT[:4], start=1):  # two errors, triage, incident.opened
        st.apply(normalise(raw, event_id=i))
    assert tickets(st.snapshot())[0]["error"]["count"] == 2
    # the same signature keeps arriving while Forge works: no stray "NEW ERROR" row
    st.apply(normalise(ev("atlas.platform", "error.raised", 25, None, None, "500 again", signature="sig-1", message="x")))
    st.apply(normalise(ev("atlas.platform", "error.raised", 26, None, None, "500 again", signature="sig-1", message="x")))
    rows = tickets(st.snapshot())
    assert len(rows) == 1 and rows[0]["ticket"] == "ATLAS-142" and rows[0]["error"]["count"] == 4
    # a different signature is a genuinely new, untracked error: it shows in the signal strip, never as a row
    st.apply(normalise(ev("atlas.platform", "error.raised", 27, None, None, "boom", signature="sig-2", message="y")))
    snap = st.snapshot(now=T0 + timedelta(seconds=30))
    assert [r["ticket"] for r in tickets(snap)] == ["ATLAS-142"]
    assert snap["signal"]["untracked_count"] == 1 and snap["signal"]["latest"]["signature"] == "sig-2"
    assert snap["signal"]["total_10m"] == 5 and sum(snap["signal"]["rate"]) == 5
    assert st.active_ticket() == "ATLAS-142"


def test_incident_attaches_every_pending_row_with_its_signature():
    st = State()
    st.apply(normalise(ev("atlas.platform", "error.raised", 0, None, None, "a", signature="sig-A", message="a")))
    st.apply(normalise(ev("atlas.platform", "error.raised", 1, None, None, "b", signature="sig-B", message="b")))
    st.apply(normalise(ev("atlas.platform", "error.raised", 2, None, None, "a", signature="sig-A", message="a")))
    snap = st.snapshot(now=T0 + timedelta(seconds=5))
    assert tickets(snap) == [] and snap["signal"]["untracked_signatures"] == 2 and snap["signal"]["untracked_count"] == 3
    st.apply(normalise(ev("atlas.scout", "agent.status", 3, agent("scout"), None, "triaging", status="working", thinking="hmm")))
    st.apply(normalise(ev("atlas.scout", "incident.opened", 10, agent("scout"), "ATLAS-7", "Opened ATLAS-7",
                          incident={"signature": "sig-A", "count": 2}, issue={"key": "ATLAS-7", "title": "A"})))
    snap = st.snapshot(now=T0 + timedelta(seconds=12))
    rows = {r["ticket"]: r for r in tickets(snap)}
    assert set(rows) == {"ATLAS-7"}
    assert rows["ATLAS-7"]["error"]["signature"] == "sig-A" and rows["ATLAS-7"]["error"]["count"] == 2
    assert rows["ATLAS-7"]["stages"]["error"].startswith("2026-09-17T10:00:00")  # earliest sig-A error
    assert rows["ATLAS-7"]["stages"]["triage"].startswith("2026-09-17T10:00:03")
    assert snap["signal"]["untracked_signatures"] == 1 and snap["signal"]["latest"]["signature"] == "sig-B"
    # sig-B's own ticket takes the remaining bucket and nothing is left behind
    st.apply(normalise(ev("atlas.scout", "incident.opened", 20, agent("scout"), "ATLAS-8", "Opened ATLAS-8",
                          incident={"signature": "sig-B", "count": 1}, issue={"key": "ATLAS-8", "title": "B"})))
    snap = st.snapshot(now=T0 + timedelta(seconds=22))
    rows = {r["ticket"]: r for r in tickets(snap)}
    assert set(rows) == {"ATLAS-7", "ATLAS-8"} and rows["ATLAS-8"]["error"]["count"] == 1
    assert snap["signal"]["untracked_count"] == 0


SIG = "/api/renewals/reconcile:BusinessRuleViolation"


def _err(sec: float, msg: str, **over) -> dict:
    fields = dict(kind="business_rule", signature=SIG, endpoint="/api/renewals/reconcile", method="POST",
                  error_type="BusinessRuleViolation", message=msg)
    fields.update(over)
    return ev("atlas.platform", "error.raised", sec, None, None, "422 on POST /api/renewals/reconcile", **fields)


def _scout_triage(sec: float) -> list[dict]:
    """What Scout really emits while triaging: status with no ticket, then LLM status/thinking on the 'triage' pseudo-ticket."""
    return [
        ev("atlas.scout", "agent.status", sec, agent("scout"), None, "Seen 3 business rule errors on POST /api/renewals/reconcile", status="working", thinking="assessing"),
        ev("atlas.scout", "agent.status", sec + 1, agent("scout"), "triage", "Calling the model", status="working", thinking="Calling the model",
           telemetry={"tokens_in": 900, "tokens_out": 100, "model_calls": 1, "seconds": 3, "usd": 0.01}),
        ev("atlas.scout", "agent.thinking", sec + 2, agent("scout"), "triage", "Two runs disagree; this is one signature", thinking="Two runs disagree; this is one signature"),
    ]


def _incident(sec: float, ticket: str = "ATLAS-37", signature: str | None = SIG) -> dict:
    return ev("atlas.scout", "incident.opened", sec, agent("scout"), ticket, f"Opened {ticket}: reconcile run drops policies",
              incident={"signature": signature, "count": 3, "customer_impact": 11},
              issue={"key": ticket, "title": "Reconcile run drops expiring policies", "priority": "High", "type": "Bug"})


def _only_ticket_row(st: State, ticket: str) -> dict:
    rows = tickets(st.snapshot())
    assert [r["ticket"] for r in rows] == [ticket], [(r["ticket"], r["stage"], r["title"]) for r in rows]
    return rows[0]


def test_varying_messages_before_and_after_incident_share_one_row():
    st = State()
    st.apply(normalise(_err(0, "2 active policies expiring on 2026-09-27 are missing from the 14-day run")))
    st.apply(normalise(_err(1, "9 policies missing from 60-day run")))
    for raw in _scout_triage(3):
        st.apply(normalise(raw))
    # the 'triage' pseudo-ticket must not become a pipeline row nor swallow the untracked errors
    snap = st.snapshot(now=T0 + timedelta(seconds=6))
    assert tickets(snap) == [] and snap["signal"]["untracked_count"] == 2 and snap["signal"]["triage_since"] is not None
    st.apply(normalise(_err(4, "1 policy missing from 30-day run")))
    st.apply(normalise(_incident(10)))
    row = _only_ticket_row(st, "ATLAS-37")
    assert row["error"]["count"] == 3 and row["stages"]["error"].startswith("2026-09-17T10:00:00")
    assert row["stages"]["triage"].startswith("2026-09-17T10:00:03")
    assert st.snapshot()["signal"]["untracked_count"] == 0
    # more of the same signature after the ticket exists, with yet another message
    st.apply(normalise(_err(12, "4 policies missing from 14-day run")))
    st.apply(normalise(_err(13, "7 policies missing from 90-day run")))
    row = _only_ticket_row(st, "ATLAS-37")
    assert row["error"]["count"] == 5 and row["stage"] == "ticket"
    # scout going back to work (no ticket) never resurrects an orphan
    st.apply(normalise(ev("atlas.scout", "agent.status", 14, agent("scout"), None, "watching", status="working", thinking="watching")))
    _only_ticket_row(st, "ATLAS-37")
    # scout's triage telemetry landed on the real ticket, not on 'triage'
    assert st.snapshot()["telemetry"]["tokens_in"] == 900
    assert next(c for c in st.snapshot()["fleet"] if c["handle"] == "scout")["ticket"] == "ATLAS-37"


def test_errors_arriving_after_incident_out_of_order_do_not_orphan():
    """SQS standard queues reorder: the incident can land before the errors that caused it."""
    st = State()
    st.apply(normalise(_incident(10)))
    st.apply(normalise(_err(0, "2 policies missing from the 14-day run")))
    st.apply(normalise(_err(1, "9 policies missing from 60-day run")))
    row = _only_ticket_row(st, "ATLAS-37")
    assert row["error"]["count"] == 2 and row["first_ts"].startswith("2026-09-17T10:00:00")
    assert row["stages"]["error"].startswith("2026-09-17T10:00:00") and row["stage"] == "ticket"
    for raw in _scout_triage(11):
        st.apply(normalise(raw))
    _only_ticket_row(st, "ATLAS-37")


def test_platform_without_signature_field_still_matches_scouts_fallback():
    st = State()
    st.apply(normalise(_err(0, "a", signature=None)))
    st.apply(normalise(ev("atlas.scout", "agent.status", 1, agent("scout"), None, "triaging", status="working", thinking="x")))
    st.apply(normalise(_err(2, "b", signature=None)))
    st.apply(normalise(_incident(5)))  # scout computed endpoint:error_type == SIG
    row = _only_ticket_row(st, "ATLAS-37")
    assert row["error"]["count"] == 2 and row["stage"] == "ticket"
    st.apply(normalise(_err(6, "c", signature=None)))
    assert _only_ticket_row(st, "ATLAS-37")["error"]["count"] == 3


def test_unmatched_pending_rows_are_absorbed_when_nothing_else_is_open():
    """Signatures that cannot be matched must still not leave a stray NEW ERROR row behind a lone ticket."""
    st = State()
    st.apply(normalise(_err(0, "a", signature="something-else")))
    st.apply(normalise(ev("atlas.scout", "agent.status", 1, agent("scout"), None, "triaging", status="working", thinking="x")))
    st.apply(normalise(_incident(5)))
    row = _only_ticket_row(st, "ATLAS-37")
    assert row["error"]["count"] == 1 and row["stages"]["triage"].startswith("2026-09-17T10:00:01")


def test_awaiting_human_counter_drops_on_every_way_out_of_the_gate():
    def to_gate() -> State:
        st = State()
        for i, (_, raw) in enumerate(SCRIPT[:9], start=1):  # up to review.posted
            st.apply(normalise(raw, event_id=i))
        assert st.snapshot()["gate"]["awaiting"] == 1 and st.snapshot()["gate"]["waiting"] is True
        return st

    st = to_gate()
    st.apply(normalise(SCRIPT[9][1]))  # human.approved
    snap = st.snapshot()
    assert snap["gate"]["awaiting"] == 0 and snap["gate"]["waiting"] is False and tickets(snap)[0]["stage"] == "merge"

    st = to_gate()
    st.apply(normalise(ev("atlas.mission-control", "human.rejected", 200, HUMAN, "ATLAS-142", "no", pr=PR, reason="no")))
    assert st.snapshot()["gate"]["awaiting"] == 0

    st = to_gate()  # merged straight on GitHub: no ticket on the event, matched by PR number
    st.apply(normalise(ev("atlas.github", "pr.merged", 200, None, None, "merged", pr={"number": 17}, sha="abc")))
    assert st.snapshot()["gate"]["awaiting"] == 0 and st.snapshot()["gate"]["waiting"] is False

    st = to_gate()
    st.apply(normalise(ev("atlas.conductor", "ticket.closed", 200, agent("conductor"), "ATLAS-142", "closed", pr={"number": 17})))
    assert st.snapshot()["gate"]["awaiting"] == 0 and st.snapshot()["gate"]["waiting"] is False


def test_stale_row_on_the_same_pr_leaves_the_gate_with_the_approval():
    """Two tickets ended up pointing at PR #17 (a re-triage); approving the PR must not leave a ghost at the gate."""
    st = State()
    for i, (_, raw) in enumerate(SCRIPT[:9], start=1):
        st.apply(normalise(raw, event_id=i))
    st.apply(normalise(ev("atlas.sentinel", "review.posted", 190, agent("sentinel"), "ATLAS-143", "reviewed", pr=PR)))
    assert st.snapshot()["gate"]["awaiting"] == 2
    st.apply(normalise(ev("atlas.mission-control", "human.approved", 300, HUMAN, "ATLAS-143", "approved", pr=PR, waited_seconds=110)))
    snap = st.snapshot()
    assert snap["gate"]["awaiting"] == 0 and snap["gate"]["waiting"] is False
    assert {r["stage"] for r in tickets(snap)} == {"merge"}
