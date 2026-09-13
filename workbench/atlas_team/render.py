"""Run one headless Claude Code teammate inside a tmux pane and render its stream legibly.

Usage: atlas-team-render <role> <ticket> <worktree> <result.json> <prompt-file>
Prints big, plain lines (thoughts and tool use) to the pane, writes the JSON result on exit, and
mirrors thinking to the lab event bus as a supervised agent when AWS credentials are available.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from .roles import ROLES

BOLD, DIM, RESET = "\033[1m", "\033[2m", "\033[0m"
COLOURS = {"analyst": "\033[38;5;214m", "builder": "\033[38;5;39m", "tester": "\033[38;5;84m", "reviewer": "\033[38;5;177m"}


def _emit(detail_type: str, role: str, ticket: str, summary: str, **extra) -> None:
    bus = os.environ.get("EVENT_BUS")
    if not bus:
        return
    try:
        import boto3

        detail = {
            "ts": datetime.now(UTC).isoformat(),
            "actor": {"handle": f"wb-{role}", "kind": "agent", "display_name": role.title(), "mode": "supervised"},
            "ticket": ticket,
            "summary": summary,
            "role": role,
            **extra,
        }
        boto3.client("events", region_name=os.environ.get("AWS_REGION", "ap-southeast-2")).put_events(
            Entries=[{"Source": "atlas.workbench", "DetailType": detail_type, "EventBusName": bus, "Detail": json.dumps(detail)}]
        )
    except Exception:  # noqa: BLE001
        pass


def main() -> None:
    role, ticket, worktree, result_path, prompt_file = sys.argv[1:6]
    prompt = Path(prompt_file).read_text()
    c = COLOURS.get(role, "")
    print(f"{c}{BOLD}{ROLES[role]['avatar']}  {role.upper()}{RESET}  {DIM}{ticket} · {worktree}{RESET}\n")
    _emit("teammate.spawned", role, ticket, f"{role.title()} started on {ticket} in its own worktree", worktree=worktree, branch=f"workbench/{ticket}/{role}")
    _emit("agent.status", role, ticket, "Starting", status="working", thinking="Reading CLAUDE.md")
    t0 = time.time()
    cmd = [
        "claude", "-p", prompt, "--output-format", "stream-json", "--verbose", "--dangerously-skip-permissions",
        "--model", os.environ.get("WORKBENCH_MODEL", "claude-sonnet-5"), "--max-turns", "60", "--max-budget-usd", "3",
    ]
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    proc = subprocess.Popen(cmd, cwd=worktree, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
    result = {"role": role, "ticket": ticket, "worktree": worktree, "ok": False, "result": "", "cost_usd": 0, "turns": 0, "tools": 0}
    last_status = 0.0
    assert proc.stdout is not None
    for line in proc.stdout:
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "assistant":
            for b in ev.get("message", {}).get("content", []):
                if b.get("type") == "text" and b.get("text", "").strip():
                    text = b["text"].strip()
                    print(f"\n{c}▌{RESET} {text}\n", flush=True)
                    if time.time() - last_status > 3:
                        last_status = time.time()
                        _emit("agent.status", role, ticket, text[:160], status="working", thinking=text[:200])
                elif b.get("type") == "tool_use":
                    result["tools"] += 1
                    inp = b.get("input", {}) or {}
                    what = inp.get("file_path") or inp.get("command") or inp.get("pattern") or ""
                    print(f"  {DIM}› {b.get('name')}  {str(what)[:90]}{RESET}", flush=True)
        elif ev.get("type") == "result":
            result.update(
                ok=not ev.get("is_error", False), result=ev.get("result", ""), cost_usd=ev.get("total_cost_usd", 0), turns=ev.get("num_turns", 0),
                session_id=ev.get("session_id"),
            )
    proc.wait()
    result["seconds"] = round(time.time() - t0, 1)
    try:
        result["commits"] = subprocess.run(["git", "log", "--oneline", "main..HEAD"], cwd=worktree, capture_output=True, text=True).stdout.strip().splitlines()
        result["diffstat"] = subprocess.run(["git", "diff", "--stat", "main...HEAD"], cwd=worktree, capture_output=True, text=True).stdout.strip()
    except Exception:  # noqa: BLE001
        pass
    Path(result_path).write_text(json.dumps(result, indent=2))
    status = "DONE" if result["ok"] else "FAILED"
    print(f"\n{c}{BOLD}■ {role.upper()} {status}{RESET}  {DIM}{result['seconds']}s · {result['turns']} turns · ${result['cost_usd']:.2f} · {len(result.get('commits', []))} commits{RESET}")
    _emit("teammate.finished", role, ticket, f"{role.title()} finished: {status.lower()}, {len(result.get('commits', []))} commits, ${result['cost_usd']:.2f}", ok=result["ok"], commits=result.get("commits", []))
    _emit("agent.status", role, ticket, f"{status.title()}", status="idle" if result["ok"] else "blocked", thinking=f"{status.title()} after {result['seconds']}s")
    print(f"\n{DIM}(pane stays open; the main session collects this work){RESET}")
    # keep the pane readable until the orchestrator closes it
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
