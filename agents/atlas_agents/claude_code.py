"""Run Claude Code headless and stream its thinking.

One session per ticket: phase one investigates (read only), phase two implements, and review
rounds resume the same session so the agent keeps its context.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass
class Run:
    result: str = ""
    session_id: str | None = None
    cost_usd: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    turns: int = 0
    seconds: float = 0.0
    ok: bool = False
    error: str | None = None
    tools_used: list[str] = field(default_factory=list)

    def final_json(self) -> dict | None:
        """The trailing JSON object in the result text, if any."""
        text = self.result
        end = text.rfind("}")
        if end == -1:
            return None
        depth = 0
        for i in range(end, -1, -1):
            if text[i] == "}":
                depth += 1
            elif text[i] == "{":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[i : end + 1])
                    except json.JSONDecodeError:
                        return None
        return None


def _tool_summary(name: str, inp: dict) -> str:
    if name in ("Read", "Edit", "Write", "MultiEdit"):
        p = inp.get("file_path", "")
        return f"{'Reading' if name == 'Read' else 'Editing' if name != 'Write' else 'Writing'} {os.path.relpath(p) if p else 'a file'}"
    if name in ("Grep", "Glob"):
        return f"Searching for {inp.get('pattern', '')!r}"
    if name == "Bash":
        cmd = str(inp.get("command", ""))[:120]
        return f"Running: {cmd}"
    return f"Using {name}"


def run(
    prompt: str,
    cwd: Path,
    *,
    model: str,
    on_thought: Callable[[str], None] | None = None,
    on_tool: Callable[[str], None] | None = None,
    resume: str | None = None,
    max_turns: int = 80,
    max_budget_usd: float = 4.0,
    timeout: int = 1200,
    env: dict | None = None,
    system_append: str | None = None,
) -> Run:
    cmd = [
        "claude", "-p", prompt,
        "--output-format", "stream-json", "--verbose",
        "--model", model,
        "--dangerously-skip-permissions",
        "--max-turns", str(max_turns),
        "--max-budget-usd", str(max_budget_usd),
    ]
    if resume:
        cmd += ["--resume", resume]
    if system_append:
        cmd += ["--append-system-prompt", system_append]
    run = Run()
    t0 = time.time()
    proc_env = {**os.environ, **(env or {})}
    proc_env.pop("CLAUDECODE", None)  # allow nesting when developing inside Claude Code
    log.info("claude start", extra={"cwd": str(cwd), "resume": resume, "model": model})
    proc = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=proc_env)
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            if time.time() - t0 > timeout:
                proc.kill()
                run.error = f"timeout after {timeout}s"
                break
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = ev.get("type")
            if t == "system" and ev.get("subtype") == "init":
                run.session_id = ev.get("session_id")
            elif t == "assistant":
                for block in ev.get("message", {}).get("content", []):
                    if block.get("type") == "text" and block.get("text", "").strip():
                        if on_thought:
                            on_thought(block["text"].strip())
                    elif block.get("type") == "tool_use":
                        run.tools_used.append(block.get("name", "?"))
                        if on_tool:
                            on_tool(_tool_summary(block.get("name", "?"), block.get("input", {}) or {}))
            elif t == "result":
                run.result = ev.get("result", "") or ""
                run.session_id = ev.get("session_id", run.session_id)
                run.cost_usd = float(ev.get("total_cost_usd", 0) or 0)
                u = ev.get("usage", {}) or {}
                run.tokens_in = int(u.get("input_tokens", 0) or 0) + int(u.get("cache_read_input_tokens", 0) or 0) + int(u.get("cache_creation_input_tokens", 0) or 0)
                run.tokens_out = int(u.get("output_tokens", 0) or 0)
                run.turns = int(ev.get("num_turns", 0) or 0)
                run.ok = not ev.get("is_error", False) and ev.get("subtype", "success") == "success"
                if not run.ok:
                    run.error = ev.get("subtype") or "error"
        proc.wait(timeout=30)
    finally:
        run.seconds = time.time() - t0
        if proc.poll() is None:
            proc.kill()
    if proc.returncode not in (0, None) and not run.result:
        run.error = (run.error or "") + " " + (proc.stderr.read()[-1500:] if proc.stderr else "")
        run.ok = False
    log.info("claude done", extra={"ok": run.ok, "turns": run.turns, "usd": round(run.cost_usd, 3), "secs": round(run.seconds), "error": run.error})
    return run
