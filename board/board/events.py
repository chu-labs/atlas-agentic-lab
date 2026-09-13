"""Outbound domain events to EventBridge, source `atlas.board` (see docs/EVENTS.md).

Best effort: a failure to emit is logged and never fails the request. With EVENT_BUS empty the
event is only logged, which is what local dev and tests want.
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from functools import lru_cache

from .settings import settings

log = logging.getLogger(__name__)
SOURCE = "atlas.board"


@lru_cache
def _events():
    import boto3

    return boto3.client("events", region_name=settings().aws_region)


def envelope(actor: dict, issue: dict | None, summary: str, **extra) -> dict:
    """Build the EVENTS.md detail body. `issue` is the compact summary from repo.issue_summary."""
    detail = {
        "ts": datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "actor": {
            "handle": actor["handle"],
            "kind": actor["kind"],
            "display_name": actor["display_name"],
            "mode": actor.get("mode"),
        },
        "ticket": issue["key"] if issue else None,
        "summary": summary,
        "lab": settings().lab_name,
    }
    if actor["kind"] == "agent" and actor.get("authority"):
        detail["authority"] = actor["authority"]
    if issue is not None:
        detail["issue"] = issue
    detail.update({k: v for k, v in extra.items() if v is not None})
    return detail


def emit(detail_type: str, detail: dict) -> None:
    log.info("board event", extra={"detail_type": detail_type, "event": detail})
    bus = settings().event_bus
    if not bus:
        return
    try:
        _events().put_events(
            Entries=[
                {
                    "Source": SOURCE,
                    "DetailType": detail_type,
                    "EventBusName": bus,
                    "Detail": json.dumps(detail, default=str),
                }
            ]
        )
    except Exception:
        log.exception("failed to put board event", extra={"detail_type": detail_type})
