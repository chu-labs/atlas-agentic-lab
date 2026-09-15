"""Scenario runner: kick off a defect and watch the agents pick it up, live, in the terminal."""
from __future__ import annotations

import json
import sys
import time

import httpx
from rich.console import Console
from rich.live import Live
from rich.table import Table

from . import defects, record, state, traffic
from .config import outputs

console = Console()
INTERESTING = {
    "defect.injected", "error.raised", "incident.opened", "issue.assigned", "branch.created", "pr.opened", "pr.updated",
    "review.posted", "review.changes_requested", "human.gate_waiting", "human.approved", "human.rejected", "pr.merged",
    "deploy.completed", "verify.passed", "verify.failed", "ticket.closed", "escalation.raised", "authority.blocked",
    "teammate.spawned", "teammate.finished", "converge.done", "incident.threshold_crossed", "incident.resolved",
}
TERMINAL = {"ticket.closed", "escalation.raised", "verify.failed"}


def _client() -> httpx.Client:
    return httpx.Client(base_url=outputs().urls["mission-control"], auth=defects._basic_auth(), timeout=30)


def _last_event_id(c: httpx.Client) -> int:
    ev = c.get("/api/events", params={"limit": 1}).json()
    return ev[-1]["id"] if ev else 0


def watch(after: int, *, approve_on_key: bool = True, until_terminal: bool = True, timeout: int = 2400) -> str | None:
    """Stream events after `after` to the terminal. Returns the terminal event type, or None on timeout."""
    t0 = time.time()
    seen_errors = 0
    last_error_line = 0
    gate_pr: int | None = None
    with _client() as c:
        console.print(f"[dim]watching Mission Control from event {after} … Ctrl-C stops[/]")
        while time.time() - t0 < timeout:
            try:
                events = c.get("/api/events", params={"after": after, "limit": 500}).json()
            except Exception as e:  # noqa: BLE001
                console.print(f"[red]{type(e).__name__}[/]"); time.sleep(3); continue
            for e in events:
                after = max(after, e["id"])
                dt = e["detail_type"]
                if dt == "error.raised":
                    seen_errors += 1
                    if seen_errors - last_error_line >= 10 or seen_errors == 1:
                        last_error_line = seen_errors
                        console.print(f"[red]{_ts(e)}  +{_el(t0)}  platform  error.raised ×{seen_errors}  {(e.get('detail') or {}).get('message', '')[:100]}[/]")
                    continue
                if dt not in INTERESTING and not (dt == "agent.status" and (e.get("detail") or {}).get("status") in ("working", "escalated", "blocked") and not (e.get("detail") or {}).get("heartbeat")):
                    continue
                actor = (e.get("actor") or {}).get("display_name") or e.get("source", "")
                kind = (e.get("actor") or {}).get("kind")
                colour = "yellow" if kind == "human" else "cyan" if dt.startswith("agent.") else "green"
                console.print(f"[{colour}]{_ts(e)}  +{_el(t0)}  {actor:<15} {dt:<24}[/] {(e.get('summary') or '')[:120]}")
                if dt == "human.gate_waiting":
                    gate_pr = ((e.get("detail") or {}).get("pr") or {}).get("number")
                    console.print(f"[bold yellow]▶ WAITING ON YOU: approve PR #{gate_pr} on the dashboard" + (" (or type A + Enter here)" if approve_on_key else "") + "[/]")
                if dt in TERMINAL and until_terminal:
                    console.print(f"[bold]■ {dt} after {_el(t0)}[/]")
                    return dt
            if gate_pr and approve_on_key and _key_pressed():
                r = c.post("/api/gate/approve", json={"pr": gate_pr})
                console.print(f"[yellow]approve → {r.status_code} {r.text[:120]}[/]")
                gate_pr = None
            time.sleep(2)
    return None


def _ts(e: dict) -> str:
    return (e.get("ts") or "")[11:19]


def _el(t0: float) -> str:
    s = int(time.time() - t0)
    return f"{s // 60}:{s % 60:02d}"


def _key_pressed() -> bool:
    """Non-blocking check for 'a' + Enter on stdin (POSIX)."""
    import select

    if not sys.stdin.isatty():
        return False
    r, _, _ = select.select([sys.stdin], [], [], 0)
    if r:
        line = sys.stdin.readline().strip().lower()
        return line == "a"
    return False


def run(defect_ids: list[str], *, name: str | None, workbench: bool = False, rps: float = 3.0) -> None:
    st = state.load()
    if st.get("injected") or st.get("workbench_injected"):
        raise SystemExit("something is already injected; run `labctl reset` first")
    if not traffic.running():
        u, p = defects._basic_auth()
        traffic.start(outputs().urls["atlas-platform"], u, p, rps)
        console.print("traffic started")
    with _client() as c:
        after = _last_event_id(c)
    record.mark()
    console.print(f"[bold]injecting {', '.join(defect_ids)}[/] (build + rollout ≈ 70 s; the agents are already watching)")
    if workbench:
        for d in defect_ids:
            defects.inject(d, workbench=True)
    else:
        defects.inject("+".join(defect_ids))
    if not traffic.running():
        u, p = defects._basic_auth()
        traffic.start(outputs().urls["atlas-platform"], u, p, rps)
        console.print("[yellow]traffic had stopped during the rollout; restarted[/]")
    console.print("[bold]injected.[/] Watch the dashboard; here is the same story in text:")
    end = watch(after)
    if name:
        console.print(record.save(name))
    if end is None:
        console.print("[yellow]stopped watching (timeout); the run may still be going[/]")
