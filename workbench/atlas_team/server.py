"""The atlas-team MCP server. The main Claude Code session calls these tools; real tmux panes appear."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .roles import ROLES

SESSION = os.environ.get("ATLAS_TMUX_SESSION", "atlas")
STATE_DIR = Path(os.environ.get("ATLAS_WB_STATE", str(Path.home() / ".config" / "atlas-lab" / "workbench")))
MAX_TEAMMATES = 4
mcp = FastMCP("atlas-team")


def _repo() -> Path:
    if os.environ.get("ATLAS_PLATFORM_REPO"):
        return Path(os.environ["ATLAS_PLATFORM_REPO"])
    return Path(subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True).stdout.strip())


def _tmux(*args: str, check: bool = True) -> str:
    return subprocess.run(["tmux", *args], capture_output=True, text=True, check=check).stdout.strip()


def _teammates(ticket: str | None = None) -> list[dict]:
    out = []
    for f in sorted(STATE_DIR.glob("*/*.meta.json")):
        m = json.loads(f.read_text())
        if ticket and m["ticket"] != ticket:
            continue
        res = Path(m["result"])
        m["state"] = "done" if res.exists() and json.loads(res.read_text()).get("ok") else ("failed" if res.exists() else "running")
        if res.exists():
            m["summary"] = {k: v for k, v in json.loads(res.read_text()).items() if k in ("ok", "seconds", "turns", "cost_usd", "commits", "diffstat")}
        out.append(m)
    return out


@mcp.tool()
def spawn_teammate(role: str, task: str, ticket: str) -> str:
    """Spawn a real teammate: a headless Claude Code process in its own git worktree and its own tmux pane.

    role: analyst | builder | tester | reviewer. task: what to do, in plain English (include the ticket text).
    ticket: e.g. ATLAS-142. Returns the branch and pane. Maximum four teammates at once.
    """
    if role not in ROLES:
        return f"unknown role {role!r}; choose from {', '.join(ROLES)}"
    running = [t for t in _teammates() if t["state"] == "running"]
    if len(running) >= MAX_TEAMMATES:
        return f"already {MAX_TEAMMATES} teammates running; collect or close some first"
    repo = _repo()
    branch = f"workbench/{ticket}/{role}"
    wt = repo.parent / ".worktrees" / f"{ticket}-{role}"
    if wt.exists():
        subprocess.run(["git", "worktree", "remove", "--force", str(wt)], cwd=repo, capture_output=True)
    subprocess.run(["git", "branch", "-D", branch], cwd=repo, capture_output=True)
    subprocess.run(["git", "worktree", "add", "-q", "-b", branch, str(wt), "HEAD"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["uv", "sync", "--extra", "dev", "--quiet"], cwd=wt, capture_output=True)

    d = STATE_DIR / ticket
    d.mkdir(parents=True, exist_ok=True)
    prompt_file = d / f"{role}.prompt.txt"
    prompt_file.write_text(f"{ROLES[role]['prompt']}\n\nTICKET {ticket}:\n{task}\n\nYou are on branch {branch} in {wt}. Commit your work on this branch. Do not push.")
    result = d / f"{role}.json"
    result.unlink(missing_ok=True)

    import sys

    render = str(Path(sys.executable).parent / "atlas-team-render")
    cmd = f"cd {wt} && {render} {role} {ticket} {wt} {result} {prompt_file}"
    # Split the right-hand side: first teammate splits the main window horizontally, later ones split the last teammate pane vertically.
    panes = _tmux("list-panes", "-t", SESSION, "-F", "#{pane_id} #{pane_title}").splitlines()
    teammate_panes = [p.split()[0] for p in panes if any(r in p for r in ROLES)]
    if not teammate_panes:
        pane = _tmux("split-window", "-h", "-t", f"{SESSION}:0.0", "-P", "-F", "#{pane_id}", "-l", "48%", cmd)
    else:
        pane = _tmux("split-window", "-v", "-t", teammate_panes[-1], "-P", "-F", "#{pane_id}", cmd)
        _tmux("select-layout", "-t", SESSION, "main-vertical", check=False)
    _tmux("select-pane", "-t", pane, "-T", f" {ROLES[role]['avatar']} {role.upper()} · {ticket} ")
    _tmux("select-pane", "-t", pane, "-P", f"fg={ROLES[role]['colour']}", check=False)
    _tmux("set-option", "-p", "-t", pane, "pane-border-style", f"fg={ROLES[role]['colour']}", check=False)
    _tmux("set-option", "-p", "-t", pane, "pane-active-border-style", f"fg={ROLES[role]['colour']},bold", check=False)
    _tmux("select-pane", "-t", f"{SESSION}:0.0")
    (d / f"{role}.meta.json").write_text(json.dumps({"role": role, "ticket": ticket, "branch": branch, "worktree": str(wt), "pane": pane, "result": str(result), "started": time.time()}))
    _tmux("set", "-g", "@atlas_agents", str(len(teammate_panes) + 1), check=False)
    _tmux("set", "-g", "@atlas_ticket", ticket, check=False)
    return f"{role} spawned on branch {branch} (worktree {wt}) in pane {pane}. Watch it work; call teammate_status to poll."


@mcp.tool()
def teammate_status(ticket: str | None = None) -> str:
    """Status of every teammate: running / done / failed, with commits and cost when finished."""
    ts = _teammates(ticket)
    if not ts:
        return "no teammates"
    lines = []
    for t in ts:
        s = t.get("summary", {})
        lines.append(f"{t['role']:9} {t['state']:8} {t['branch']}  " + (f"{len(s.get('commits', []))} commits, {s.get('seconds')}s, ${s.get('cost_usd', 0):.2f}" if s else f"{int(time.time() - t['started'])}s elapsed"))
    return "\n".join(lines)


@mcp.tool()
def collect_teammates(ticket: str, wait_seconds: int = 0) -> str:
    """Collect every teammate's result for a ticket: their final message, commits and diffstat. Optionally wait for stragglers."""
    deadline = time.time() + wait_seconds
    while time.time() < deadline and any(t["state"] == "running" for t in _teammates(ticket)):
        time.sleep(5)
    parts = []
    for t in _teammates(ticket):
        if t["state"] == "running":
            parts.append(f"## {t['role']} — still running")
            continue
        r = json.loads(Path(t["result"]).read_text())
        parts.append(
            f"## {t['role']} — {'ok' if r.get('ok') else 'FAILED'} ({r.get('seconds')}s, {r.get('turns')} turns, ${r.get('cost_usd', 0):.2f})\n"
            f"branch: {t['branch']}\ncommits:\n" + "\n".join(f"  {c}" for c in r.get("commits", [])) + f"\ndiffstat:\n{r.get('diffstat', '')}\n\nfinal message:\n{r.get('result', '')[:3000]}"
        )
    return "\n\n".join(parts)


@mcp.tool()
def converge_branches(ticket: str, into: str | None = None) -> str:
    """Create fix/<ticket>-workbench from main and merge each teammate branch into it in order analyst, tester, builder, reviewer.

    Stops at the first conflict and reports it so the main session can resolve it by hand in the repo. Reports the merged test status.
    """
    repo = _repo()
    target = into or f"fix/{ticket}-workbench"
    subprocess.run(["git", "checkout", "-q", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "branch", "-D", target], cwd=repo, capture_output=True)
    subprocess.run(["git", "checkout", "-q", "-b", target], cwd=repo, check=True, capture_output=True)
    report = [f"created {target} from main"]
    order = {"analyst": 0, "tester": 1, "builder": 2, "reviewer": 3}
    for t in sorted(_teammates(ticket), key=lambda t: order.get(t["role"], 9)):
        if t["state"] == "running":
            report.append(f"skipped {t['role']}: still running")
            continue
        m = subprocess.run(["git", "merge", "--no-ff", "--no-edit", t["branch"]], cwd=repo, capture_output=True, text=True)
        if m.returncode != 0:
            conflicts = subprocess.run(["git", "diff", "--name-only", "--diff-filter=U"], cwd=repo, capture_output=True, text=True).stdout.split()
            report.append(f"CONFLICT merging {t['branch']}: {conflicts}. Resolve in {repo}, then `git add` and `git commit`, then run tests.")
            _emit_converge(ticket, f"Conflict merging {t['role']}'s branch in {', '.join(conflicts)}; main session resolving", conflict=True)
            return "\n".join(report)
        report.append(f"merged {t['branch']}")
    tests = subprocess.run(["uv", "run", "pytest", "-q", "-p", "no:cacheprovider"], cwd=repo, capture_output=True, text=True)
    report.append("tests: " + (tests.stdout.strip().splitlines() or ["?"])[-1])
    _emit_converge(ticket, f"Converged {len(report) - 2} branches into {target}; " + report[-1], conflict=False)
    return "\n".join(report)


@mcp.tool()
def close_teammates(ticket: str | None = None) -> str:
    """Kill teammate panes and remove their worktrees (branches are kept)."""
    n = 0
    for t in _teammates(ticket):
        _tmux("kill-pane", "-t", t["pane"], check=False)
        subprocess.run(["git", "worktree", "remove", "--force", t["worktree"]], cwd=_repo(), capture_output=True)
        Path(t["result"]).parent.joinpath(f"{t['role']}.meta.json").unlink(missing_ok=True)
        n += 1
    _tmux("set", "-g", "@atlas_agents", "0", check=False)
    return f"closed {n} teammates"


def _emit_converge(ticket: str, summary: str, conflict: bool) -> None:
    bus = os.environ.get("EVENT_BUS")
    if not bus:
        return
    try:
        import boto3
        from datetime import UTC, datetime

        boto3.client("events", region_name=os.environ.get("AWS_REGION", "ap-southeast-2")).put_events(
            Entries=[{"Source": "atlas.workbench", "DetailType": "converge.started" if conflict else "converge.done", "EventBusName": bus,
                      "Detail": json.dumps({"ts": datetime.now(UTC).isoformat(), "actor": {"handle": "maroun", "kind": "human", "display_name": "Maroun", "mode": "supervised"}, "ticket": ticket, "summary": summary})}]
        )
    except Exception:  # noqa: BLE001
        pass


def main() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    mcp.run()


if __name__ == "__main__":
    main()
