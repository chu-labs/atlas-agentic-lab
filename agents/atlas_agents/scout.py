"""Scout: production errors in, well-written tickets out.

Autonomous by design: creating a ticket is cheap and reversible. Scout never touches code.
"""
from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field

from . import base, llm

log = logging.getLogger(__name__)

# How many occurrences within WINDOW seconds before a kind of error earns a ticket.
THRESHOLDS = {"crash": 1, "business_rule": 3, "performance": 5}
WINDOW = 300
INCIDENT_RATE_PER_MIN = 40  # across all signatures; hands off to Watchtower

SYSTEM = """You are Scout, the triage agent for ATLAS, a strata insurance platform (FastAPI + Postgres).
You turn clusters of production errors into bug tickets an engineer can act on immediately.
Write in plain, direct Australian English. Be specific: quote the endpoint, the error type, the
message, and numbers. Never speculate beyond the evidence; say what you do not know."""


@dataclass
class Cluster:
    signature: str
    events: list[dict] = field(default_factory=list)
    first_seen: float = field(default_factory=time.time)
    ticket: str | None = None
    last_update_count: int = 0

    @property
    def recent(self) -> list[dict]:
        cutoff = time.time() - WINDOW
        return [e for e in self.events if e.get("_received", 0) >= cutoff]

    @property
    def impact(self) -> int:
        return sum(int(e.get("customer_impact", 1)) for e in self.recent) or 1


def sig_label(signature: str) -> str:
    return "sig:" + hashlib.sha1(signature.encode()).hexdigest()[:8]


class Agent(base.Agent):
    queue_env = "queue_url_prod_errors"

    def __init__(self):
        super().__init__()
        self.clusters: dict[str, Cluster] = {}
        self.all_times: list[float] = []
        self.incident_open = False

    # --- intake -----------------------------------------------------------
    def handle(self, source: str, detail_type: str, detail: dict) -> None:
        if "signature" not in detail:
            return
        detail["_received"] = time.time()
        c = self.clusters.setdefault(detail["signature"], Cluster(detail["signature"]))
        c.events.append(detail)
        c.events = c.events[-200:]
        self._track_rate()
        if c.ticket is None:
            c.ticket = self._existing_ticket(c.signature)
        if c.ticket:
            self._update_existing(c)
            return
        kind = detail.get("kind", "crash")
        n = len(c.recent)
        if n >= THRESHOLDS.get(kind, 3) or c.impact >= 25:
            self._open_ticket(c)

    def _track_rate(self) -> None:
        now = time.time()
        self.all_times = [t for t in self.all_times if t > now - 60] + [now]
        if len(self.all_times) >= INCIDENT_RATE_PER_MIN and not self.incident_open:
            self.incident_open = True
            self.emitter.emit(
                "incident.threshold_crossed",
                None,
                f"Error rate crossed {INCIDENT_RATE_PER_MIN}/min across {len(self.clusters)} signatures. Handing off to Watchtower.",
                rate_per_min=len(self.all_times),
                signatures=list(self.clusters),
            )
        elif len(self.all_times) < INCIDENT_RATE_PER_MIN // 4 and self.incident_open:
            self.incident_open = False
            self.emitter.emit("incident.resolved", None, "Error rate back under threshold.", rate_per_min=len(self.all_times))

    # --- dedup ------------------------------------------------------------
    def _existing_ticket(self, signature: str) -> str | None:
        try:
            for issue in self.board.list_issues(label=sig_label(signature)):
                if issue.get("status") != "Done":
                    return issue["key"]
        except Exception:
            log.exception("board lookup failed")
        return None

    def _update_existing(self, c: Cluster) -> None:
        n = len(c.events)
        if n - c.last_update_count >= 25:
            c.last_update_count = n
            try:
                self.board.comment(c.ticket, f"Still occurring: {n} events so far, {len(c.recent)} in the last {WINDOW // 60} minutes, customer impact {c.impact}.")
            except Exception:
                log.exception("board comment failed")

    # --- ticket -----------------------------------------------------------
    def _open_ticket(self, c: Cluster) -> None:
        sample = c.recent[0]
        n = len(c.recent)
        kind = sample.get("kind", "crash")
        self.think(
            None,
            f"Seen {n} {kind.replace('_', ' ')} error{'s' if n != 1 else ''} on {sample.get('method')} {sample.get('endpoint')} "
            f"({sample.get('error_type')}) in the last {WINDOW // 60} minutes. No open ticket matches this signature, so I am assessing it.",
        )
        evidence = {
            "signature": c.signature,
            "kind": kind,
            "occurrences_recent": n,
            "occurrences_total": len(c.events),
            "customer_impact_recent": c.impact,
            "endpoint": sample.get("endpoint"),
            "method": sample.get("method"),
            "error_type": sample.get("error_type"),
            "message": sample.get("message"),
            "status_code": sample.get("status_code"),
            "sample_requests": [
                {k: e.get(k) for k in ("request_id", "path", "query", "path_params", "ts", "elapsed_ms", "customer_impact")}
                for e in c.recent[:5]
            ],
            "stack_excerpt": (sample.get("stack") or "")[-2500:],
            "platform_url": self.cfg.platform_url,
        }
        prompt = (
            "Write a bug ticket for this production error cluster.\n\n"
            "Return JSON with keys: title (<= 80 chars, states the symptom and the endpoint), "
            "priority (Highest|High|Medium|Low), reasoning (a list of 3-5 short plain-English sentences, "
            "first person, explaining what you saw, how you judged severity and customer impact, and why this "
            "deserves a ticket), description (markdown with sections: Summary, Reproduction (exact curl commands "
            "against platform_url using basic auth placeholder -u $USER:$PASS), Evidence (counts, request ids, "
            "timing), Affected endpoint, Customer impact, Where to look (which module the stack points at), "
            "and a fenced code block with the stack excerpt).\n\nEVIDENCE:\n" + __import__("json").dumps(evidence, default=str)
        )
        try:
            out = llm.ask_json(SYSTEM, prompt, emitter=self.emitter, ticket="triage", max_tokens=2500)
        except Exception:
            log.exception("llm failed; falling back to a template ticket")
            out = {
                "title": f"{sample.get('error_type')} on {sample.get('method')} {sample.get('endpoint')}",
                "priority": "High" if kind == "crash" else "Medium",
                "reasoning": [f"I saw {n} occurrences of {sample.get('error_type')} on {sample.get('endpoint')}."],
                "description": f"```\n{evidence['stack_excerpt']}\n```",
            }
        issue = self.board.create(
            type="Bug",
            title=out["title"],
            description=out["description"],
            priority=out.get("priority", "High"),
            labels=["production", kind, sig_label(c.signature)],
            assignee="forge",
            source={
                "signature": c.signature,
                "first_seen": sample.get("ts"),
                "occurrences": len(c.events),
                "customer_impact": c.impact,
                "request_ids": [e.get("request_id") for e in c.recent[:5]],
                "endpoint": sample.get("endpoint"),
                "error_type": sample.get("error_type"),
                "kind": kind,
            },
        )
        key = issue["key"]
        c.ticket = key
        c.last_update_count = len(c.events)
        # move the telemetry accrued under "triage" onto the real ticket
        if "triage" in self.emitter.telemetry:
            self.emitter.telemetry[key] = self.emitter.telemetry.pop("triage")
        for line in out.get("reasoning", []):
            self.think(key, line)
        self.think(key, f"Created {key} at priority {out.get('priority')} and assigned it to Forge. Creating a ticket is cheap and reversible, so I do this without asking.")
        self.emitter.emit(
            "incident.opened",
            key,
            f"Opened {key}: {out['title']}",
            incident={"signature": c.signature, "count": len(c.events), "first_seen": sample.get("ts"), "customer_impact": c.impact},
            issue={"key": key, "title": out["title"], "priority": out.get("priority"), "type": "Bug"},
        )
        self.emitter.status("idle", f"Ticketed {key}. Back to watching the queue.", ticket=key)
