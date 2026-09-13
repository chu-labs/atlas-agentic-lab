"""The scripted incident every test walks through: one error, one ticket, one PR, one human."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

T0 = datetime(2026, 9, 17, 10, 0, 0, tzinfo=UTC)
AUTH_FORGE = {"can_write_code": True, "can_review": False, "can_merge": False, "can_deploy": False}
PR = {"number": 17, "url": "https://github.com/chu-labs/atlas-platform/pull/17", "branch": "forge/ATLAS-142", "title": "Fix ATLAS-142: null customer on invoice"}


def ev(source: str, detail_type: str, seconds: float, actor: dict | None, ticket: str | None, summary: str, **extra) -> dict:
    ts = (T0 + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")
    detail = {"ts": ts, "actor": actor, "summary": summary}
    if ticket:
        detail["ticket"] = ticket
    detail.update(extra)
    return {"source": source, "detail-type": detail_type, "time": ts, "detail": detail}


def agent(handle: str, mode: str = "autonomous") -> dict:
    return {"handle": handle, "kind": "agent", "display_name": handle.title(), "mode": mode}


HUMAN = {"handle": "maroun", "kind": "human", "display_name": "Maroun", "mode": None}

# (expected stage after this event, event)
SCRIPT: list[tuple[str, dict]] = [
    ("error", ev("atlas.platform", "error.raised", 0, None, None, "500 on POST /invoices", signature="sig-1", message="NoneType has no attribute 'id'", endpoint="/invoices")),
    ("error", ev("atlas.platform", "error.raised", 2, None, None, "500 on POST /invoices", signature="sig-1", message="NoneType has no attribute 'id'", endpoint="/invoices")),
    ("triage", ev("atlas.scout", "agent.status", 5, agent("scout"), None, "Clustering 2 errors", status="working", thinking="Two errors share signature sig-1")),
    ("ticket", ev("atlas.scout", "incident.opened", 20, agent("scout"), "ATLAS-142", "Opened ATLAS-142: null customer on invoice",
                  incident={"signature": "sig-1", "count": 2}, issue={"key": "ATLAS-142", "title": "Null customer on invoice"},
                  telemetry={"tokens_in": 1000, "tokens_out": 200, "model_calls": 2, "seconds": 8, "usd": 0.01})),
    ("code", ev("atlas.forge", "branch.created", 40, agent("forge"), "ATLAS-142", "Created branch forge/ATLAS-142", branch="forge/ATLAS-142", authority=AUTH_FORGE)),
    ("code", ev("atlas.forge", "agent.status", 60, agent("forge"), "ATLAS-142", "Reading invoices.py", status="working", thinking="Reading invoices.py",
                telemetry={"tokens_in": 5000, "tokens_out": 800, "model_calls": 4, "seconds": 30, "usd": 0.05})),
    ("test", ev("atlas.forge", "agent.status", 90, agent("forge"), "ATLAS-142", "Running pytest", status="working", thinking="Running pytest tests/test_invoices.py",
                telemetry={"tokens_in": 9000, "tokens_out": 1500, "model_calls": 7, "seconds": 60, "usd": 0.09})),
    ("pr", ev("atlas.forge", "pr.opened", 120, agent("forge"), "ATLAS-142", "Opened PR #17", pr=PR,
              telemetry={"tokens_in": 12000, "tokens_out": 2000, "model_calls": 9, "seconds": 90, "usd": 0.12})),
    ("human_gate", ev("atlas.sentinel", "review.posted", 180, agent("sentinel"), "ATLAS-142", "Sentinel reviewed PR #17: no blocking concerns", pr=PR, verdict="comment",
                      telemetry={"tokens_in": 4000, "tokens_out": 600, "model_calls": 2, "seconds": 20, "usd": 0.03})),
    ("merge", ev("atlas.mission-control", "human.approved", 300, HUMAN, "ATLAS-142", "Maroun approved and merged PR #17", pr=PR, waited_seconds=120)),
    ("deploy", ev("atlas.github", "deploy.completed", 420, None, None, "Deployed atlas-platform sha abc123", sha="abc123", service="atlas-platform")),
    ("verify", ev("atlas.conductor", "verify.passed", 480, agent("conductor"), "ATLAS-142", "Verified: sig-1 has not recurred", smoke={"ok": True},
                  telemetry={"tokens_in": 500, "tokens_out": 100, "model_calls": 1, "seconds": 5, "usd": 0.005})),
    ("closed", ev("atlas.conductor", "ticket.closed", 490, agent("conductor"), "ATLAS-142", "Closed ATLAS-142", pr={"number": 17})),
]
