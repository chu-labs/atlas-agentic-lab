"""Build the projector-ready tmux layout for the supervised demo, in one command."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from .config import LOCAL_CFG, REPO_ROOT
from .ecs import PLATFORM_REPO

WB_DIR = REPO_ROOT / "workbench"
SESSION = "atlas"
STATE = LOCAL_CFG / "workbench"


def _tmux(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["tmux", *args], capture_output=True, text=True, check=check)


def mcp_config_path() -> Path:
    """A generated MCP config that points at this checkout's atlas-team server."""
    LOCAL_CFG.mkdir(parents=True, exist_ok=True)
    p = LOCAL_CFG / "workbench-mcp.json"
    cfg = json.loads((WB_DIR / "mcp.json").read_text())
    cfg["mcpServers"]["atlas-team"]["args"] = ["run", "--project", str(WB_DIR), "atlas-team"]
    cfg["mcpServers"]["atlas-team"]["env"] = {"ATLAS_PLATFORM_REPO": str(PLATFORM_REPO), "ATLAS_TMUX_SESSION": SESSION}
    p.write_text(json.dumps(cfg, indent=2))
    return p


def reset() -> None:
    """Kill the session, every teammate worktree and the state dir. Target: under thirty seconds."""
    _tmux("kill-session", "-t", SESSION, check=False)
    for meta in STATE.glob("*/*.meta.json"):
        m = json.loads(meta.read_text())
        subprocess.run(["git", "worktree", "remove", "--force", m["worktree"]], cwd=PLATFORM_REPO, capture_output=True)
    subprocess.run(["git", "worktree", "prune"], cwd=PLATFORM_REPO, capture_output=True)
    shutil.rmtree(STATE, ignore_errors=True)
    wt_root = PLATFORM_REPO.parent / ".worktrees"
    shutil.rmtree(wt_root, ignore_errors=True)


def build(ticket: str | None, attach: bool = True, env_extra: dict | None = None) -> None:
    if _tmux("has-session", "-t", SESSION, check=False).returncode == 0:
        reset()
    STATE.mkdir(parents=True, exist_ok=True)
    (STATE / "elapsed").write_text("0:00")
    mcp_cfg = mcp_config_path()
    # make the render entry point resolvable from any pane
    bin_dir = WB_DIR / ".venv" / "bin"
    env = {**os.environ, **(env_extra or {}), "PATH": f"{bin_dir}:{os.environ['PATH']}"}
    env.pop("CLAUDECODE", None)
    started = time.time()
    _tmux("-f", str(WB_DIR / "tmux.conf"), "new-session", "-d", "-s", SESSION, "-x", "240", "-y", "60", "-c", str(PLATFORM_REPO))
    _tmux("set-environment", "-t", SESSION, "PATH", env["PATH"])
    env["ATLAS_PLATFORM_REPO"] = str(PLATFORM_REPO)
    for k in ("EVENT_BUS", "AWS_REGION", "AWS_PROFILE", "WORKBENCH_MODEL", "ATLAS_PLATFORM_REPO"):
        if k in env:
            _tmux("set-environment", "-t", SESSION, k, env[k])
    _tmux("select-pane", "-t", f"{SESSION}:0.0", "-T", " ⌘ MAIN · Claude Code · you type here ")
    _tmux("set", "-g", "@atlas_ticket", ticket or "—")
    # elapsed-time ticker for the status bar
    _tmux("run-shell", "-b", f"while true; do printf '%d:%02d' $(( ($(date +%s) - {int(started)}) / 60 )) $(( ($(date +%s) - {int(started)}) % 60 )) > {STATE / 'elapsed'}; sleep 1; done")
    claude_cmd = f"claude --mcp-config {mcp_cfg} --model claude-sonnet-5"
    _tmux("send-keys", "-t", f"{SESSION}:0.0", claude_cmd, "C-m")
    if attach:
        os.execvp("tmux", ["tmux", "attach", "-t", SESSION])
