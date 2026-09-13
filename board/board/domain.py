"""Vocabulary of the board and the one piece of business logic it has: the status flow."""
from __future__ import annotations

STATUSES = ["Backlog", "Triage", "In Progress", "In Review", "Done"]
PRIORITIES = ["Highest", "High", "Medium", "Low", "Lowest"]
TYPES = ["Bug", "Story", "Task", "Incident"]
ACTIVITY_KINDS = ["created", "transitioned", "commented", "assigned", "field_changed", "reasoning", "escalated"]

# Forward flow plus the two sanctioned backward moves. Any status may return to Backlog.
_FORWARD = {
    "Backlog": {"Triage"},
    "Triage": {"In Progress"},
    "In Progress": {"In Review"},
    "In Review": {"Done", "In Progress"},
    "Done": {"In Progress"},
}


def allowed_transitions(status: str) -> set[str]:
    nxt = set(_FORWARD.get(status, set()))
    if status != "Backlog":
        nxt.add("Backlog")
    return nxt


def can_transition(from_status: str, to_status: str) -> bool:
    return to_status in allowed_transitions(from_status)
