"""Forge: ticket in, pull request out. Claude Code does the engineering; Forge does the process.

Forge never merges. It reproduces with a failing test first, fixes, verifies the suite itself,
verifies the test really fails without the fix, opens a PR, and explains itself on the ticket.
When a ticket is not a defect, it refuses and escalates.
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import time
from pathlib import Path

import yaml

from . import base, claude_code
from .github import GitHub

log = logging.getLogger(__name__)

INVESTIGATE = """You are Forge, the engineering agent for the ATLAS platform. You are in a fresh clone of the
repository on branch `{branch}`. Read `CLAUDE.md` first; it is your onboarding document and its rules bind you.

Ticket {key}: {title}

{description}

Structured evidence attached to the ticket:
{source}

Your authority (this is data, and it is enforced):
{authority}

PHASE 1 — INVESTIGATE ONLY. Do not modify any file in this phase.
Find the code paths involved and form a root-cause hypothesis. Then decide honestly which this is:
- "fix": behaviour contradicts the documented intent, existing tests, or an obviously reasonable expectation
  (a crash, wrong arithmetic, a boundary error, a timezone mistake, a performance regression).
- "escalate": the ticket asks for a different business outcome (rates, loadings, thresholds, windows, risk
  weights), is ambiguous, needs a data migration or schema change, has security impact, or otherwise falls
  under must_escalate_when. Changing a deliberate rule to satisfy a complaint is not a bug fix.

Think out loud in short plain-English paragraphs as you go; a human audience reads them live.
End your reply with exactly one JSON object:
{{"decision": "fix" | "escalate", "category": "<short>", "root_cause_hypothesis": "<1-2 sentences>",
  "plan": ["<step>", ...], "files": ["<path>", ...],
  "escalation": {{"reason": "<why this is not a code fix>", "what_i_need_to_know": ["<question>", ...], "assign_to": "maroun"}} }}
"""

IMPLEMENT = """PHASE 2 — IMPLEMENT. Follow CONTRIBUTING.md and CLAUDE.md exactly.
1. Write a failing test that reproduces the bug in the matching `tests/test_*.py`. Run just that test with
   `uv run pytest <path>::<name>` and confirm it FAILS. Commit only the test: `git add -A && git commit -m "test: {key} reproduce <short>"`.
2. Make the smallest correct fix. Run `uv run pytest` and `uv run ruff check atlas tests`; both must pass.
   Commit: `git commit -am "fix: {key} <short>"`.
Do not push. Do not touch migrations, dependencies, business-rule constants, or anything outside the ticket.
If you notice something else worth fixing, leave it and mention it under not_changed.
Keep narrating briefly in plain English. End with exactly one JSON object:
{{"root_cause": "<2-3 sentences>", "fix": "<what changed and why>", "test": "<what the test proves>",
  "not_changed": "<what you deliberately left alone>", "commits": ["<sha or message>", ...], "confidence": <0-1>}}
"""

REWORK = """Sentinel reviewed your pull request and requested changes:

{review}

Address every point that is valid; if one is not, say why in your summary. Keep the failing-test-first history
intact (add new commits; do not rewrite history). Run `uv run pytest` and `uv run ruff check atlas tests` before
finishing, and commit. Do not push. End with exactly one JSON object:
{{"addressed": ["<point -> what you did>", ...], "pushed_back": ["<point -> why not>", ...], "confidence": <0-1>}}
"""


def _sh(cmd: list[str], cwd: Path, env: dict | None = None, check: bool = True, timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=check, env=env, timeout=timeout)


def slug(text: str, n: int = 40) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:n].rstrip("-") or "fix"


class Agent(base.Agent):
    queue_env = "queue_url"

    def __init__(self):
        super().__init__()
        self.gh = GitHub()
        self.sessions: dict[str, dict] = {}  # ticket -> {session_id, workdir, branch, pr}
        self.cfg.workdir.mkdir(parents=True, exist_ok=True)

    # --- routing ----------------------------------------------------------
    def handle(self, source: str, detail_type: str, detail: dict) -> None:
        if detail_type == "issue.assigned" and (detail.get("issue", {}).get("assignee") == "forge" or detail.get("to") == "forge"):
            key = detail.get("ticket") or detail.get("issue", {}).get("key")
            if key and detail.get("issue", {}).get("status") in (None, "Backlog", "Triage", "In Progress"):
                self.work_ticket(key)
        elif detail_type == "review.changes_requested":
            self.rework(detail.get("ticket"), detail.get("pr", {}), detail.get("body", ""))
        elif detail_type == "workbench.dispatch":
            key = detail.get("ticket")
            if key:
                self.work_ticket(key)

    # --- the main flow ----------------------------------------------------
    def work_ticket(self, key: str) -> None:
        if not self.guard("can_write_code", f"work on {key}", key):
            return
        issue = self.board.get(key)
        if issue.get("pr_url") and issue.get("status") == "In Review":
            log.info("already has a PR; skipping", extra={"ticket": key})
            return
        t0 = time.time()
        self.current_ticket = key
        self.board.move(key, "In Progress")
        self.think(key, f"Picked up {key} from the queue: \"{issue['title']}\". Cloning atlas-platform and reading CLAUDE.md before I touch anything.")

        branch = f"fix/{key}-{slug(issue['title'])}"
        wd = self._fresh_clone(key, branch)
        env = self._test_env()
        self.emitter.emit("branch.created", key, f"Created branch {branch} in a fresh clone", branch=branch)

        # Phase 1: investigate and decide
        run1 = claude_code.run(
            INVESTIGATE.format(
                key=key, title=issue["title"], description=issue.get("description", ""),
                source=json.dumps(issue.get("source") or {}, indent=2, default=str),
                authority=yaml.safe_dump(self.me.authority, sort_keys=False), branch=branch,
            ),
            wd, model=self.me.model or self.cfg.model, env=env,
            on_thought=lambda t: self.think(key, t),
            on_tool=lambda t: self.emitter.status("working", t, ticket=key, tool=True),
            max_turns=40, max_budget_usd=2.0,
        )
        self._account(key, run1)
        decision = run1.final_json() or {}
        if not run1.ok or not decision:
            self._fail(key, f"Investigation did not complete cleanly ({run1.error or 'no decision returned'}).")
            return
        if decision.get("decision") == "escalate":
            self._escalate(key, decision)
            return

        # Phase 2: implement, failing test first
        run2 = claude_code.run(
            IMPLEMENT.format(key=key), wd, model=self.me.model or self.cfg.model, env=env, resume=run1.session_id,
            on_thought=lambda t: self.think(key, t),
            on_tool=lambda t: self.emitter.status("working", t, ticket=key, tool=True),
            max_turns=80, max_budget_usd=4.0,
        )
        self._account(key, run2)
        summary = run2.final_json() or {}
        if not run2.ok:
            self._fail(key, f"Implementation did not complete ({run2.error}).")
            return

        # Independent verification: the suite is green, and the test really fails without the fix.
        ok, report = self._verify(wd, env, key)
        if not ok:
            self.think(key, f"My own verification failed, so I am not opening a PR: {report}")
            self._fail(key, f"Verification failed: {report}")
            return
        self.think(key, report)

        # Push and open the PR
        if not self.guard("can_open_pull_requests", "open a pull request", key):
            return
        self._push(wd, branch)
        body = self._pr_body(key, issue, decision, summary, report)
        pr = self.gh.open_pr(branch, f"{key}: {issue['title']}", body)
        self.sessions[key] = {"session_id": run2.session_id, "workdir": str(wd), "branch": branch, "pr": pr["number"]}
        self.board.update(key, pr_url=pr["html_url"], branch=branch)
        self.board.comment(
            key,
            f"Opened pull request [#{pr['number']}]({pr['html_url']}).\n\n**Root cause:** {summary.get('root_cause', '?')}\n\n"
            f"**Fix:** {summary.get('fix', '?')}\n\n**Test:** {summary.get('test', '?')}\n\n**Not changed:** {summary.get('not_changed', '-')}\n\n"
            f"I cannot merge this; it needs Sentinel's review and a human approval.",
        )
        self.board.move(key, "In Review")
        elapsed = time.time() - t0
        self.emitter.emit(
            "pr.opened", key, f"Opened PR #{pr['number']} after {elapsed / 60:.1f} min: failing test first, then the fix",
            pr={"number": pr["number"], "url": pr["html_url"], "branch": branch, "title": pr["title"], "head_sha": pr["head"]["sha"]},
            summary_json=summary,
        )
        self.emitter.status("waiting_on_review", f"PR #{pr['number']} open. Waiting for Sentinel.", ticket=key)
        self.current_ticket = None

    def rework(self, key: str | None, pr: dict, review: str) -> None:
        if not key or key not in self.sessions:
            log.warning("rework requested for unknown ticket %s", key)
            if key:
                self.board.comment(key, "Sentinel requested changes but I no longer have the working copy for this ticket. A human needs to pick this up.")
                self.emitter.status("blocked", f"Lost working copy for {key}", ticket=key)
            return
        s = self.sessions[key]
        wd, env = Path(s["workdir"]), self._test_env()
        self.board.move(key, "In Progress")
        self.think(key, "Sentinel requested changes. Reading the review and reworking on the same branch.")
        run = claude_code.run(
            REWORK.format(review=review), wd, model=self.me.model or self.cfg.model, env=env, resume=s["session_id"],
            on_thought=lambda t: self.think(key, t),
            on_tool=lambda t: self.emitter.status("working", t, ticket=key, tool=True),
            max_turns=60, max_budget_usd=3.0,
        )
        self._account(key, run)
        out = run.final_json() or {}
        ok, report = self._verify(wd, env, key, require_two_commits=False)
        if not run.ok or not ok:
            self._fail(key, f"Rework failed: {run.error or report}")
            return
        self._push(wd, s["branch"])
        self.gh.comment(s["pr"], "Addressed Sentinel's review:\n\n" + "\n".join(f"- {a}" for a in out.get("addressed", [])) + ("\n\nPushed back on:\n" + "\n".join(f"- {a}" for a in out.get("pushed_back", [])) if out.get("pushed_back") else ""))
        self.board.comment(key, "Addressed the review and pushed. " + report)
        self.board.move(key, "In Review")
        prd = self.gh.pr(s["pr"])
        self.emitter.emit("pr.updated", key, f"Pushed rework to PR #{s['pr']}", pr={"number": s["pr"], "url": prd["html_url"], "branch": s["branch"], "title": prd["title"], "head_sha": prd["head"]["sha"]})
        self.emitter.status("waiting_on_review", "Rework pushed. Waiting for Sentinel again.", ticket=key)

    # --- pieces -----------------------------------------------------------
    def _fresh_clone(self, key: str, branch: str) -> Path:
        wd = self.cfg.workdir / key
        if wd.exists():
            shutil.rmtree(wd)
        _sh(["git", "clone", "--quiet", self.gh.clone_url(), str(wd)], cwd=self.cfg.workdir)
        _sh(["git", "config", "user.name", "Forge (atlas agent)"], cwd=wd)
        _sh(["git", "config", "user.email", "forge@atlas-lab.invalid"], cwd=wd)
        _sh(["git", "checkout", "-q", "-b", branch], cwd=wd)
        _sh(["uv", "sync", "--extra", "dev", "--quiet"], cwd=wd, timeout=600)
        return wd

    def _test_env(self) -> dict:
        import os

        env = {k: v for k, v in os.environ.items() if k not in ("VIRTUAL_ENV", "CLAUDECODE")}
        env.update({"DB_HOST": self.cfg.db_host, "DB_PORT": "5432", "DB_USER": self.cfg.db_user, "DB_PASSWORD": self.cfg.db_password, "DB_NAME": "atlas_forge"})
        return env

    def _verify(self, wd: Path, env: dict, key: str, require_two_commits: bool = True) -> tuple[bool, str]:
        suite = _sh(["uv", "run", "pytest", "-q", "-p", "no:cacheprovider"], cwd=wd, env=env, check=False)
        if suite.returncode != 0:
            return False, "the full suite is not green:\n" + suite.stdout[-1200:]
        lint = _sh(["uv", "run", "ruff", "check", "atlas", "tests"], cwd=wd, env=env, check=False)
        if lint.returncode != 0:
            return False, "ruff is not clean:\n" + lint.stdout[-800:]
        log_out = _sh(["git", "log", "--format=%h %s", "main..HEAD"], cwd=wd).stdout.strip().splitlines()
        if require_two_commits:
            test_commits = [c for c in log_out if " test:" in c or c.split(" ", 1)[1].startswith("test")]
            if len(log_out) < 2 or not test_commits:
                return False, f"expected a test commit followed by a fix commit, found: {log_out}"
            # Check the failing-test-first claim: at the test commit alone, the suite must fail.
            test_sha = test_commits[-1].split()[0]
            probe = wd.parent / f"{key}-probe"
            if probe.exists():
                shutil.rmtree(probe)
            _sh(["git", "worktree", "add", "-q", str(probe), test_sha], cwd=wd)
            try:
                _sh(["uv", "sync", "--extra", "dev", "--quiet"], cwd=probe, env=env, timeout=600)
                at_test = _sh(["uv", "run", "pytest", "-q", "-x", "-p", "no:cacheprovider"], cwd=probe, env={**env, "DB_NAME": "atlas_forge_probe"}, check=False)
            finally:
                _sh(["git", "worktree", "remove", "--force", str(probe)], cwd=wd, check=False)
            if at_test.returncode == 0:
                return False, "the test commit does not fail on its own, so it does not reproduce the bug"
            n = len(log_out)
            return True, f"Verified independently: full suite green, ruff clean, and the suite fails at the test commit alone ({n} commits: test first, then fix)."
        return True, "Verified independently: full suite green and ruff clean."

    def _push(self, wd: Path, branch: str) -> None:
        _sh(["git", "remote", "set-url", "origin", self.gh.clone_url()], cwd=wd)
        _sh(["git", "push", "--quiet", "-u", "origin", branch], cwd=wd)

    def _pr_body(self, key: str, issue: dict, decision: dict, summary: dict, report: str) -> str:
        return (
            f"Fixes {key}: {issue['title']}\n\n"
            f"## Root cause\n{summary.get('root_cause', decision.get('root_cause_hypothesis', '?'))}\n\n"
            f"## Fix\n{summary.get('fix', '?')}\n\n"
            f"## Test\n{summary.get('test', '?')}\n\n"
            f"## Not changed\n{summary.get('not_changed', '-')}\n\n"
            f"## Verification\n{report}\n\n"
            f"---\nOpened by **Forge** (autonomous agent). Authority: can write code and open PRs; cannot merge or deploy. "
            f"Confidence {summary.get('confidence', '?')}. Ticket: {self.cfg.board_url}/issue/{key}\n"
        )

    def _escalate(self, key: str, decision: dict) -> None:
        esc = decision.get("escalation") or {}
        questions = esc.get("what_i_need_to_know") or []
        to = esc.get("assign_to") or "maroun"
        self.think(key, f"I am not going to change code for this. {esc.get('reason', decision.get('root_cause_hypothesis', ''))}")
        body = (
            f"**Escalating to a human instead of fixing.**\n\n{esc.get('reason', '')}\n\n"
            f"Category: `{decision.get('category', 'ambiguous')}`. My authority says I must escalate on "
            f"{', '.join(self.me.authority.get('must_escalate_when', []))}, and this falls under that.\n\n"
            "What I would need to know before changing anything:\n" + "\n".join(f"- {q}" for q in questions)
            + f"\n\nReassigning to @{to}."
        )
        self.board.escalate(key, to, body)
        self.emitter.emit(
            "escalation.raised", key, f"Refused to change code on {key}: {decision.get('category', 'not a defect')}. Escalated to {to}.",
            category=decision.get("category"), questions=questions, assigned_to=to,
        )
        self.emitter.status("escalated", f"{key} is a decision, not a defect. Handed to {to}.", ticket=key)
        self.current_ticket = None

    def _fail(self, key: str, why: str) -> None:
        log.error("ticket failed: %s", why)
        self.board.escalate(key, "maroun", f"I could not complete this safely: {why}\n\nLeaving it for a human.")
        self.emitter.emit("escalation.raised", key, f"Could not complete {key}: {why[:160]}", category="agent_failure")
        self.emitter.status("blocked", f"Stuck on {key}: {why[:120]}", ticket=key)
        self.current_ticket = None

    def _account(self, key: str, run: claude_code.Run) -> None:
        self.emitter.add_telemetry(key, tokens_in=run.tokens_in, tokens_out=run.tokens_out, model_calls=run.turns, seconds=run.seconds, usd=run.cost_usd)
