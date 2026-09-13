"""Lab-level events (source atlas.lab) so the dashboard shows what the operator did."""
from __future__ import annotations

import json
from datetime import UTC, datetime

from .aws import client
from .config import outputs


def emit(detail_type: str, summary: str, **extra) -> None:
    detail = {
        "ts": datetime.now(UTC).isoformat(),
        "actor": {"handle": "maroun", "kind": "human", "display_name": "Maroun", "mode": None},
        "summary": summary,
        **extra,
    }
    client("events").put_events(
        Entries=[{"Source": "atlas.lab", "DetailType": detail_type, "EventBusName": outputs().event_bus, "Detail": json.dumps(detail, default=str)}]
    )
