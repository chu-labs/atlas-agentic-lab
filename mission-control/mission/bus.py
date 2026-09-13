"""Outbound events, source `atlas.mission-control` (docs/EVENTS.md).

With EVENT_BUS set the event goes to EventBridge and comes back to us through the mission-events
queue like everyone else's. Without a bus (local dev, tests, demo feed) it is folded straight into
the local hub so the timeline still shows it.
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from functools import lru_cache

from .settings import settings

log = logging.getLogger(__name__)
SOURCE = "atlas.mission-control"


@lru_cache
def _events():
    import boto3

    return boto3.client("events", region_name=settings().aws_region)


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def human_actor() -> dict:
    s = settings()
    return {
        "handle": s.github_human_login or "human",
        "kind": "human",
        "display_name": s.github_human_display_name,
        "mode": None,
    }


def system_actor() -> dict:
    return {"handle": "mission-control", "kind": "system", "display_name": "Mission Control", "mode": None}


def envelope(actor: dict, ticket: str | None, summary: str, **extra) -> dict:
    detail = {"ts": now_iso(), "actor": actor, "ticket": ticket, "summary": summary, "lab": settings().lab_name}
    detail.update({k: v for k, v in extra.items() if v is not None})
    return detail


def publish(detail_type: str, detail: dict) -> None:
    """Emit one event. Bus when configured, else straight into the local hub."""
    log.info("mission event", extra={"detail_type": detail_type, "event": detail})
    bus = settings().event_bus
    if not bus:
        from .hub import hub

        hub().ingest({"source": SOURCE, "detail-type": detail_type, "time": detail.get("ts"), "detail": detail})
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
        log.exception("failed to put mission event", extra={"detail_type": detail_type})
