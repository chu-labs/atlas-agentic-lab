"""Watchtower: incidents. Opens an Incident ticket when Scout reports the rate threshold crossed,
keeps a running timeline on it, and drafts a blameless postmortem when the rate recovers."""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from . import base, llm

log = logging.getLogger(__name__)

SYSTEM = """You are Watchtower, the incident agent for the ATLAS strata insurance platform. You write
terse, factual incident updates and blameless postmortems in plain Australian English. Blameless
means: describe what the system did and why, never who was at fault."""


class Agent(base.Agent):
    def __init__(self):
        super().__init__()
        self.incident: str | None = None
        self.timeline: list[str] = []

    def handle(self, source: str, detail_type: str, detail: dict) -> None:
        if detail_type == "incident.threshold_crossed":
            self.open(detail)
        elif detail_type == "incident.resolved":
            self.resolve(detail)
        elif detail_type in ("incident.opened", "pr.opened", "ticket.closed", "human.approved") and self.incident:
            self.note(f"{detail.get('actor', {}).get('display_name', source)}: {detail.get('summary', detail_type)}")

    def open(self, detail: dict) -> None:
        if self.incident:
            return
        if not self.guard("can_create_tickets", "open an incident"):
            return
        rate = detail.get("rate_per_min")
        sigs = detail.get("signatures", [])
        now = datetime.now(UTC).strftime("%H:%M:%S UTC")
        issue = self.board.create(
            type="Incident",
            title=f"Elevated production error rate ({rate}/min)",
            description=f"Scout reported the error rate crossing the threshold at {now}.\n\nSignatures involved:\n" + "\n".join(f"- `{s}`" for s in sigs) + "\n\nTimeline follows in comments.",
            priority="Highest",
            labels=["incident", "production"],
            assignee="watchtower",
        )
        self.incident = issue["key"]
        self.timeline = [f"{now} — incident opened at {rate} errors/min across {len(sigs)} signatures"]
        self.think(self.incident, f"Opened {self.incident}. I will keep a timeline here and draft the postmortem when the rate recovers. I do not fix anything myself.")
        self.emitter.emit("incident.opened", self.incident, f"Opened incident {self.incident} at {rate} errors/min", incident={"rate": rate, "signatures": sigs})

    def note(self, line: str) -> None:
        if not self.incident:
            return
        stamp = datetime.now(UTC).strftime("%H:%M:%S UTC")
        self.timeline.append(f"{stamp} — {line}")
        try:
            self.board.comment(self.incident, f"**{stamp}** {line}")
        except Exception:
            log.exception("timeline comment failed")

    def resolve(self, detail: dict) -> None:
        if not self.incident:
            return
        key = self.incident
        self.note("error rate back under threshold; incident resolved")
        self.think(key, "Drafting a blameless postmortem from the timeline.")
        try:
            pm = llm.ask(SYSTEM, "Write a blameless postmortem (markdown: Summary, Impact, Timeline, What happened, What went well, What we will change) from this timeline:\n" + "\n".join(self.timeline), emitter=self.emitter, ticket=key, max_tokens=1500)
        except Exception:
            log.exception("postmortem llm failed")
            pm = "Postmortem draft unavailable.\n\n" + "\n".join(self.timeline)
        self.board.comment(key, "## Draft postmortem\n\n" + pm)
        self.board.move(key, "In Review")
        self.emitter.emit("incident.resolved", key, f"Resolved {key}; postmortem drafted for human review")
        self.emitter.status("idle", f"{key} resolved; postmortem awaiting a human.", ticket=key)
        self.incident = None
        self.timeline = []
