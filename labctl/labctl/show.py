"""`labctl show`: the lecture in one command. You only approve.

Sequence (all timings approximate, measured in rehearsal):
  0:00  preflight: AWS, services, traffic, a reset if anything is injected, recording mark
  0:05  a human files the "premiums over 20 floors look too high" ticket → Forge investigates and refuses (~40 s)
  0:10  the off-by-one bug is shipped to production (build + rollout ≈ 90 s)
  ~2:00 Scout tickets it · ~2:30 Forge starts · ~5:00 PR open · ~6:00 Sentinel done → HUMAN GATE
  you click Approve on Mission Control (or type `a` + Enter here)
  ~+4:00 deploy verified, ticket closed, recording saved
"""
from __future__ import annotations

import time

from rich.console import Console
from rich.panel import Panel

from . import defects, demo, record, state, traffic
from .config import outputs

console = Console()


def _say(msg: str, style: str = "bold") -> None:
    console.print(Panel(msg, style=style, expand=False))


def run(*, with_ambiguous: bool = True, skip_reset: bool = False, rps: float = 3.0) -> None:
    t0 = time.time()
    o = outputs()
    _say("ATLAS demo · preflight", "bold cyan")

    st = state.load()
    if (st.get("injected") or st.get("workbench_injected")) and not skip_reset:
        console.print("something is injected from a previous run; resetting first (about 90 s)…")
        for line in defects.reset():
            console.print(f"  {line}")
    if not traffic.running():
        u, p = defects._basic_auth()
        traffic.start(o.urls["atlas-platform"], u, p, rps)
    console.print("traffic: running")
    with demo._client() as c:
        after = demo._last_event_id(c)
    record.mark()
    name = time.strftime("lecture-%Y%m%d-%H%M")
    console.print(f"recording as [bold]{name}[/]")

    ignore: set[str] = set()
    if with_ambiguous:
        d = defects.get("ambiguous-high-rise")
        key = defects._file_ticket(d["ticket"], {"kind": "human_report", "defect": d["id"]})
        ignore.add(key)
        _say(f"{_el(t0)}  A human just filed {key}: \"{d['ticket']['title']}\"\nWatch Forge read the code and refuse.", "bold magenta")

    _say(f"{_el(t0)}  Shipping the off-by-one bug to production (build + rollout ≈ 90 s).\nTalk: nobody has been told; traffic is live.", "bold yellow")
    defects.inject("off-by-one")
    if not traffic.running():
        u, p = defects._basic_auth()
        traffic.start(o.urls["atlas-platform"], u, p, rps)
    _say(f"{_el(t0)}  The bug is live. From here on it is the agents' turn.\nScout → ticket · Forge → failing test, fix, PR · Sentinel → review · then YOU at the gate.", "bold green")

    end = demo.watch(after, approve_on_key=True, until_terminal=True, timeout=2400, ignore_tickets=ignore, t0=t0)
    if end:
        _say(f"{_el(t0)}  Run finished: {end}", "bold green")
    else:
        _say(f"{_el(t0)}  Watch budget exhausted; the run may still be going on the dashboard.", "bold red")
    try:
        console.print(record.save(name))
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]could not save recording: {e}[/]")
    console.print("\nWhen you are done talking: [bold]uv run labctl reset[/]")


def _el(t0: float) -> str:
    s = int(time.time() - t0)
    return f"{s // 60}:{s % 60:02d}"
