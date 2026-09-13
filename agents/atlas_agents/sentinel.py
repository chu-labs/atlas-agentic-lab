"""Sentinel: an independent second pair of eyes on every Forge pull request.

Deterministic checks first (scope, forbidden paths, business-rule constants, test-first history,
CI status), then a model review for correctness and test quality. Sentinel may comment or request
changes. It cannot approve, and the GitHub client refuses APPROVE outright.
"""
from __future__ import annotations

import logging
import re
import time

from . import base, llm
from .github import GitHub

log = logging.getLogger(__name__)

FORBIDDEN_PATHS = ("migrations/", "pyproject.toml", "uv.lock", ".github/", "Dockerfile")
BUSINESS_RULE_PATTERNS = (
    r"^\+.*\bBASE_RATE\b.*=", r"^\+.*\bHIGH_RISE_LOADING\b.*=", r"^\+.*\bHIGH_RISE_FLOORS\b.*=",
    r"^\+.*\bMINIMUM_PREMIUM\b.*=", r"^\+.*\bWEIGHTS\b.*=", r"^\+.*Decimal\(\"1\.\d+\"\).*loading",
)
MAX_CHANGED_LINES = 400

SYSTEM = """You are Sentinel, the independent review agent for the ATLAS strata insurance platform.
You review pull requests opened by Forge, another agent. You are sceptical by default: your job is to
catch what Forge missed. Judge correctness of the fix against the root cause, whether the test would
actually catch a regression (not just pass), edge cases (boundaries, timezones, Decimal money, zero
values), scope creep, and security. Be concrete: cite file paths and lines. Plain Australian English.
Never approve; your options are COMMENT (looks good, notes only) or REQUEST_CHANGES (with specific asks)."""


class Agent(base.Agent):
    def __init__(self):
        super().__init__()
        self.gh = GitHub()
        self.rounds: dict[int, int] = {}

    def handle(self, source: str, detail_type: str, detail: dict) -> None:
        if detail_type not in ("pr.opened", "pr.updated"):
            return
        pr = detail.get("pr", {})
        key = detail.get("ticket")
        if not pr.get("number"):
            return
        self.review(key, int(pr["number"]))

    def review(self, key: str | None, number: int) -> None:
        if not self.guard("can_review", f"review PR #{number}", key):
            return
        self.rounds[number] = self.rounds.get(number, 0) + 1
        rnd = self.rounds[number]
        self.think(key, f"Reviewing PR #{number} (round {rnd}). I did not write this code and I have not read Forge's reasoning; I am starting from the diff.")
        pr = self.gh.pr(number)
        files = self.gh.pr_files(number)
        diff = self.gh.pr_diff(number)
        issue = self.board.get(key) if key else {}
        strict = "review:strict" in (issue.get("labels") or [])

        findings: list[str] = []
        blocking: list[str] = []

        # 1. Scope and forbidden paths
        touched = [f["filename"] for f in files]
        for f in touched:
            if any(f.startswith(p) or f == p for p in FORBIDDEN_PATHS):
                blocking.append(f"`{f}` is outside a bug fix's remit (schema, dependencies, pipeline). Revert it or split it out.")
        changed = sum(f.get("additions", 0) + f.get("deletions", 0) for f in files)
        if changed > MAX_CHANGED_LINES:
            blocking.append(f"{changed} changed lines is too large for one ticket. Narrow the change.")
        # 2. Business rule constants
        for pat in BUSINESS_RULE_PATTERNS:
            if re.search(pat, diff, flags=re.MULTILINE):
                blocking.append("The diff changes a business-rule constant. That is an underwriting decision, not a bug fix; escalate instead.")
                break
        # 3. Tests present
        test_files = [f for f in touched if f.startswith("tests/")]
        if not test_files:
            blocking.append("No test was added or changed. CONTRIBUTING.md requires a failing test first.")
        # 4. Test-first history
        commits = self.gh.api("GET", f"/repos/{self.gh.org}/{self.gh.repo}/pulls/{number}/commits")
        msgs = [c["commit"]["message"].splitlines()[0] for c in commits]
        if msgs and not msgs[0].lower().startswith("test"):
            findings.append(f"First commit is `{msgs[0]}`; I expected the reproducing test to come first.")
        # 5. CI
        ci = self._wait_for_ci(pr["head"]["sha"])
        if ci == "failure":
            blocking.append("CI is red on this head. Fix the suite before review.")
        elif ci == "unknown":
            findings.append("CI had not reported within my wait; reviewing the diff anyway.")

        self.think(key, f"Mechanical checks done: {len(touched)} files, {changed} changed lines, tests touched: {', '.join(test_files) or 'none'}, CI: {ci}. Now reading the change itself.")

        # 6. Model review
        prompt = (
            f"Pull request #{number}: {pr['title']}\n\nPR description:\n{pr.get('body') or ''}\n\n"
            f"Ticket: {issue.get('title', '')}\n{(issue.get('description') or '')[:2500]}\n\n"
            f"Commits: {msgs}\n\nDIFF:\n{diff[:24000]}\n\n"
            "Return JSON: {\"verdict\": \"comment\" | \"request_changes\", \"summary\": \"<2-3 sentences>\", "
            "\"strengths\": [\"...\"], \"concerns\": [{\"severity\": \"blocking\"|\"minor\", \"where\": \"file:line\", \"what\": \"...\", \"ask\": \"...\"}], "
            "\"test_quality\": \"<would the test catch a regression? what edge case is missing?>\", "
            "\"reasoning\": [\"<3-5 short first-person sentences on how you judged it>\"]}"
            + ("\n\nThis ticket is labelled review:strict: the team wants a second edge-case test before merge. If the change is otherwise sound, "
               "request changes asking for one specific additional test that would strengthen it." if strict and rnd == 1 else "")
        )
        try:
            out = llm.ask_json(SYSTEM, prompt, emitter=self.emitter, ticket=key or f"pr-{number}", max_tokens=4000)
        except Exception:
            log.exception("llm review failed")
            out = {"verdict": "comment", "summary": "Model review unavailable; mechanical checks only.", "concerns": [], "reasoning": [], "strengths": []}
        for line in out.get("reasoning", []):
            self.think(key, line)
        model_blocking = [c for c in out.get("concerns", []) if c.get("severity") == "blocking"]
        request_changes = bool(blocking or model_blocking or out.get("verdict") == "request_changes")
        if rnd >= 3 and not blocking:
            request_changes = False  # do not loop forever; hand the residual to the human
            findings.append("Third round: leaving remaining concerns for the human reviewer rather than looping again.")

        body = self._body(out, blocking, findings, request_changes, ci)
        event = "REQUEST_CHANGES" if request_changes else "COMMENT"
        try:
            self.gh.review(number, event, body)
        except Exception:
            # GitHub occasionally 500s on the reviews endpoint; the review must still land.
            log.exception("review endpoint failed; posting as a PR comment instead")
            self.gh.comment(number, body)
        verdict = "requested changes" if request_changes else "commented; no blocking concerns"
        self.board.comment(key, f"Reviewed [PR #{number}]({pr['html_url']}) and **{verdict}**.\n\n{out.get('summary', '')}" + (
            "\n\nBlocking:\n" + "\n".join(f"- {b}" for b in blocking + [c.get("ask") or c.get("what") for c in model_blocking]) if request_changes else ""
        )) if key else None
        if request_changes:
            self.emitter.emit(
                "review.changes_requested", key, f"Sentinel requested changes on PR #{number}: {out.get('summary', '')[:120]}",
                pr={"number": number, "url": pr["html_url"], "title": pr["title"], "head_sha": pr["head"]["sha"]}, body=body, round=rnd,
            )
            self.emitter.status("idle", f"Sent PR #{number} back to Forge.", ticket=key)
        else:
            self.emitter.emit(
                "review.posted", key, f"Sentinel reviewed PR #{number}: no blocking concerns. Now waiting on a human.",
                pr={"number": number, "url": pr["html_url"], "title": pr["title"], "head_sha": pr["head"]["sha"]}, body=body, round=rnd, verdict="comment",
            )
            self.emitter.status("idle", f"PR #{number} reviewed. It is the human's call now; I cannot approve.", ticket=key)

    def _wait_for_ci(self, sha: str, timeout: int = 240) -> str:
        deadline = time.time() + timeout
        while time.time() < deadline:
            runs = self.gh.check_runs(sha)
            tests = [r for r in runs if r.get("name") == "test"]
            if tests:
                r = tests[0]
                if r.get("status") == "completed":
                    return r.get("conclusion") or "unknown"
            time.sleep(15)
        return "unknown"

    def _body(self, out: dict, blocking: list[str], findings: list[str], request_changes: bool, ci: str) -> str:
        parts = [f"## Sentinel review — {'changes requested' if request_changes else 'no blocking concerns'}", "", out.get("summary", ""), ""]
        if blocking:
            parts += ["### Blocking (policy)"] + [f"- {b}" for b in blocking] + [""]
        concerns = out.get("concerns", [])
        if concerns:
            parts += ["### Concerns"] + [f"- **{c.get('severity', 'minor')}** {c.get('where', '')}: {c.get('what', '')} {('→ ' + c['ask']) if c.get('ask') else ''}" for c in concerns] + [""]
        if out.get("test_quality"):
            parts += ["### Test quality", out["test_quality"], ""]
        if out.get("strengths"):
            parts += ["### What is good"] + [f"- {s}" for s in out["strengths"]] + [""]
        if findings:
            parts += ["### Notes"] + [f"- {f}" for f in findings] + [""]
        parts += ["---", f"CI on head: {ci}. Sentinel is an autonomous agent with authority to review and request changes, not to approve or merge."]
        return "\n".join(parts)
