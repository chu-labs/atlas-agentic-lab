"""Emit contract events (docs/EVENTS.md) and poll an SQS queue."""
from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from functools import lru_cache

from .authority import AgentDef
from .config import config

log = logging.getLogger(__name__)


@lru_cache
def _events():
    import boto3

    return boto3.client("events", region_name=config().aws_region)


@lru_cache
def _sqs():
    import boto3

    return boto3.client("sqs", region_name=config().aws_region)


class Emitter:
    """Builds the envelope for one agent and puts events on the bus (or logs them locally)."""

    def __init__(self, agent: AgentDef):
        self.agent = agent
        self.source = f"atlas.{agent.name}"
        self.telemetry: dict[str, dict] = {}  # ticket -> cumulative telemetry

    def envelope(self, ticket: str | None, summary: str, **extra) -> dict:
        d = {
            "ts": datetime.now(UTC).isoformat(),
            "actor": {
                "handle": self.agent.name,
                "kind": "agent",
                "display_name": self.agent.display_name,
                "mode": self.agent.mode,
            },
            "summary": summary,
            "authority": self.agent.authority,
        }
        if ticket:
            d["ticket"] = ticket
            if ticket in self.telemetry:
                d["telemetry"] = self.telemetry[ticket]
        d.update(extra)
        return d

    def emit(self, detail_type: str, ticket: str | None, summary: str, **extra) -> dict:
        detail = self.envelope(ticket, summary, **extra)
        log.info("event", extra={"detail_type": detail_type, "detail": detail})
        bus = config().event_bus
        if bus:
            try:
                _events().put_events(
                    Entries=[
                        {
                            "Source": self.source,
                            "DetailType": detail_type,
                            "EventBusName": bus,
                            "Detail": json.dumps(detail, default=str),
                        }
                    ]
                )
            except Exception:
                log.exception("put_events failed")
        return detail

    def status(self, status: str, thinking: str, ticket: str | None = None, **extra) -> None:
        self.emit("agent.status", ticket, thinking, status=status, thinking=thinking, **extra)

    def add_telemetry(self, ticket: str, **delta) -> dict:
        t = self.telemetry.setdefault(ticket, {"tokens_in": 0, "tokens_out": 0, "model_calls": 0, "seconds": 0.0, "usd": 0.0})
        for k, v in delta.items():
            t[k] = t.get(k, 0) + v
        return t


def poll(queue_url: str, handler, *, max_messages: int = 10, wait: int = 20, idle=None) -> Iterator[None]:
    """Long-poll a queue forever. `handler(body: dict)` returning normally deletes the message.

    Raising leaves the message for redelivery (and the DLQ after maxReceiveCount).
    `idle()` is called when a poll returns nothing, so agents can report idle status.
    """
    sqs = _sqs()
    while True:
        try:
            resp = sqs.receive_message(
                QueueUrl=queue_url, MaxNumberOfMessages=max_messages, WaitTimeSeconds=wait, AttributeNames=["ApproximateReceiveCount"]
            )
        except Exception:
            log.exception("receive_message failed")
            time.sleep(5)
            continue
        msgs = resp.get("Messages", [])
        if not msgs:
            if idle:
                idle()
            yield
            continue
        for m in msgs:
            try:
                body = json.loads(m["Body"])
            except json.JSONDecodeError:
                body = {"raw": m["Body"]}
            try:
                handler(body)
            except Exception:
                log.exception("handler failed; message will be retried")
                continue
            sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=m["ReceiptHandle"])
        yield


def unwrap(body: dict) -> tuple[str, str, dict]:
    """EventBridge -> SQS delivery wraps our detail; raw producers (prod-errors) do not."""
    if "detail-type" in body and "detail" in body:
        return body.get("source", ""), body["detail-type"], body["detail"]
    return "raw", body.get("type", "unknown"), body
