#!/usr/bin/env python3
"""Feed a scripted incident into a running Mission Control without AWS.

Posts EventBridge-shaped events to POST /api/admin/inject with realistic pauses, so the projector
view can be rehearsed end to end. By default it stops at the human gate (so you can press Approve
on screen); pass --through to walk merge → deploy → verify → closed as well.

    uv run python scripts/demo_feed.py --url http://localhost:8767 --speed 4
    uv run python scripts/demo_feed.py --through --speed 8 --user u --password p
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import UTC, datetime

import httpx

TICKET = "ATLAS-142"
PR = {
    "number": 17,
    "url": "https://github.com/chu-labs/atlas-platform/pull/17",
    "branch": "forge/ATLAS-142-null-customer-on-invoice",
    "title": "Fix ATLAS-142: guard against invoices with no customer",
}
PR_BODY = """## Why
Archived customers are returned as `None` by `CustomerRepo.get()`; `create_invoice` dereferenced the result.

## What
- `tests/test_invoices.py::test_archived_customer_is_rejected` — **fails first**, then passes
- `app/invoices.py`: return `409 Conflict` with a clear message instead of a 500

## Scope
No schema changes, no business-rule changes, 2 files, +31 −4. Ticket: ATLAS-142.
"""
REVIEW_BODY = """**Verdict: no blocking concerns.** It is the human's call now; I cannot approve.

- Test reproduces the production error before the fix (confirmed by running it against `main`)
- Scope is tight: only the archived-customer path changes
- No schema, migration or business-rule change; no new dependencies
- Error handling returns 409 with a message the client can act on

Minor: consider logging the customer id at `warning` level. Not blocking."""
AUTH = {
    "scout": {"can_create_tickets": True, "can_write_code": False, "can_review": False, "can_merge": False, "can_deploy": False, "can_change_business_rules": False},
    "forge": {"can_write_code": True, "can_open_pull_requests": True, "can_review": False, "can_merge": False, "can_deploy": False, "can_change_business_rules": False},
    "sentinel": {"can_write_code": False, "can_review": True, "can_request_changes": True, "can_approve": False, "can_merge": False, "can_deploy": False, "can_change_business_rules": False},
    "conductor": {"can_write_code": False, "can_review": False, "can_merge": False, "can_deploy": True, "can_close_tickets": True, "can_change_business_rules": False},
}
NAMES = {"scout": "Scout", "forge": "Forge", "sentinel": "Sentinel", "conductor": "Conductor"}


def agent(handle: str) -> dict:
    return {"handle": handle, "kind": "agent", "display_name": NAMES[handle], "mode": "autonomous"}


HUMAN = {"handle": "maroun", "kind": "human", "display_name": "Maroun", "mode": None}


def tel(tokens_in: int, tokens_out: int, calls: int, seconds: float, usd: float) -> dict:
    return {"tokens_in": tokens_in, "tokens_out": tokens_out, "model_calls": calls, "seconds": seconds, "usd": usd}


def event(source: str, detail_type: str, actor: dict | None, ticket: str | None, summary: str, **extra) -> dict:
    ts = datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    detail = {"ts": ts, "actor": actor, "summary": summary, "lab": "atlas-agentic-lab"}
    if ticket:
        detail["ticket"] = ticket
    if actor and actor["kind"] == "agent" and actor["handle"] in AUTH:
        detail["authority"] = AUTH[actor["handle"]]
    detail.update(extra)
    return {"source": source, "detail-type": detail_type, "time": ts, "detail": detail}


def status(handle: str, st: str, thinking: str, ticket: str | None = None, **extra) -> dict:
    return event(f"atlas.{handle}", "agent.status", agent(handle), ticket, thinking, status=st, thinking=thinking, **extra)


def error(i: int) -> dict:
    return event(
        "atlas.platform", "error.raised", None, None, f"500 on POST /api/invoices (request {i})",
        request_id=f"req-{1000 + i}", endpoint="/api/invoices", method="POST", status_code=500, kind="unhandled",
        error_type="AttributeError", message="'NoneType' object has no attribute 'id'", signature="invoices.create:AttributeError",
        customer_impact="invoice not created",
    )


# (pause before, event)
TO_GATE: list[tuple[float, dict]] = [
    (0, error(1)),
    (1.5, error(2)),
    (1.0, error(3)),
    (2.0, status("scout", "working", "Three errors in 40 s share signature invoices.create:AttributeError. Reading the stack.")),
    (4.0, status("scout", "working", "Customer lookup returns None when the account was archived. Checking the board for an existing ticket.")),
    (4.0, event("atlas.board", "issue.created", agent("scout"), TICKET, f"Created {TICKET}: Invoice creation fails for archived customers",
                issue={"key": TICKET, "type": "Bug", "title": "Invoice creation fails for archived customers", "status": "Triage", "priority": "High", "assignee": "forge", "labels": ["production", "invoices"]})),
    (1.0, event("atlas.scout", "incident.opened", agent("scout"), TICKET, f"Opened {TICKET}: invoice creation fails for archived customers",
                incident={"signature": "invoices.create:AttributeError", "count": 3, "customer_impact": "invoice not created"},
                issue={"key": TICKET, "title": "Invoice creation fails for archived customers", "priority": "High", "type": "Bug"},
                telemetry=tel(6200, 900, 3, 22, 0.04))),
    (1.0, status("scout", "idle", f"Ticketed {TICKET}. Back to watching the queue.", TICKET, telemetry=tel(6200, 900, 3, 22, 0.04))),
    (3.0, status("forge", "working", f"Picked up {TICKET}. Cloning atlas-platform.", TICKET)),
    (3.0, event("atlas.forge", "branch.created", agent("forge"), TICKET, f"Created branch {PR['branch']} in a fresh clone", branch=PR["branch"])),
    (5.0, status("forge", "working", "Reading app/invoices.py and the customer repository. The archived path returns None and the caller dereferences it.", TICKET, telemetry=tel(21000, 1800, 6, 70, 0.14))),
    (6.0, status("forge", "working", "Writing tests/test_invoices.py::test_archived_customer_is_rejected — it must fail first.", TICKET, telemetry=tel(34000, 3200, 9, 120, 0.23))),
    (5.0, status("forge", "working", "Running pytest tests/test_invoices.py -q … 1 failed as expected.", TICKET, telemetry=tel(41000, 3900, 11, 150, 0.28))),
    (6.0, status("forge", "working", "Fix: return 409 with a clear message when the customer is archived. No business rule changes.", TICKET, telemetry=tel(55000, 5600, 14, 200, 0.38))),
    (5.0, status("forge", "working", "Running pytest -q … 84 passed.", TICKET, telemetry=tel(62000, 6100, 16, 230, 0.42))),
    (4.0, event("atlas.forge", "pr.opened", agent("forge"), TICKET, "Opened PR #17 after 4.2 min: failing test first, then the fix", pr=PR, body=PR_BODY, telemetry=tel(68000, 7000, 18, 250, 0.47))),
    (1.0, status("forge", "waiting_on_review", "PR #17 open. Waiting for Sentinel. I cannot merge this.", TICKET, telemetry=tel(68000, 7000, 18, 250, 0.47))),
    (3.0, status("sentinel", "working", "Reviewing PR #17: diff is 2 files, +31 −4. Checking the test actually fails without the fix.", TICKET)),
    (6.0, status("sentinel", "working", "Test is real, scope is tight, no schema or business-rule changes. Checking error handling on the archived path.", TICKET, telemetry=tel(15000, 1200, 4, 40, 0.09))),
    (5.0, event("atlas.sentinel", "review.posted", agent("sentinel"), TICKET, "Sentinel reviewed PR #17: no blocking concerns. Now waiting on a human.",
                pr=PR, verdict="comment", body=REVIEW_BODY, telemetry=tel(19000, 1600, 5, 55, 0.11))),
    (1.0, status("sentinel", "idle", "PR #17 reviewed. It is the human's call now; I cannot approve.", TICKET, telemetry=tel(19000, 1600, 5, 55, 0.11))),
]

THROUGH: list[tuple[float, dict]] = [
    (6.0, event("atlas.mission-control", "human.approved", HUMAN, TICKET, "Maroun approved and merged PR #17 after waiting 96s", pr=PR, waited_seconds=96)),
    (2.0, event("atlas.github", "pr.merged", None, TICKET, "PR #17 merged into main (squash)", pr=PR, sha="9f3c2a1d7e")),
    (2.0, status("conductor", "working", "Waiting for the deploy workflow for 9f3c2a1d7e.", TICKET)),
    (8.0, event("atlas.github", "deploy.completed", None, None, "Deployed atlas-platform 9f3c2a1d7e to production", service="atlas-platform", sha="9f3c2a1d7e", run_id=4412)),
    (3.0, status("conductor", "working", "Smoke-checking /health and POST /api/invoices for an archived customer. Watching for the old signature.", TICKET, telemetry=tel(4000, 500, 2, 15, 0.02))),
    (8.0, event("atlas.conductor", "verify.passed", agent("conductor"), TICKET, "Verified: deploy healthy and `invoices.create:AttributeError` has not recurred since deploy",
                smoke={"ok": True, "checks": ["health", "invoice_archived_customer_409"]}, signature_seen_after_deploy=False, telemetry=tel(6000, 700, 3, 30, 0.03))),
    (2.0, event("atlas.conductor", "ticket.closed", agent("conductor"), TICKET, f"Closed {TICKET}: fix deployed and verified in production", pr=PR, telemetry=tel(6000, 700, 3, 30, 0.03))),
    (1.0, status("conductor", "idle", f"{TICKET} verified and closed.", TICKET, telemetry=tel(6000, 700, 3, 30, 0.03))),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="http://localhost:8767")
    ap.add_argument("--user", default="")
    ap.add_argument("--password", default="")
    ap.add_argument("--speed", type=float, default=1.0, help="divide every pause by this")
    ap.add_argument("--through", action="store_true", help="continue past the gate to closed")
    ap.add_argument("--reset", action="store_true", help="clear events first")
    args = ap.parse_args()

    auth = (args.user, args.password) if args.user else None
    with httpx.Client(base_url=args.url, auth=auth, timeout=20) as c:
        if args.reset:
            c.post("/api/admin/reset").raise_for_status()
            print("reset")
        script = TO_GATE + (THROUGH if args.through else [])
        for pause, raw in script:
            time.sleep(pause / max(args.speed, 0.01))
            raw["detail"]["ts"] = raw["time"] = datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
            r = c.post("/api/admin/inject", json=raw)
            r.raise_for_status()
            print(f"{raw['source']:24} {raw['detail-type']:24} {raw['detail']['summary'][:80]}")
        state = c.get("/api/state").json()
        row = state["pipeline"][0] if state["pipeline"] else None
        print(f"\nstage: {row['stage'] if row else '-'}   gate waiting: {state['gate']['waiting']}   active: {state['active_ticket']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
