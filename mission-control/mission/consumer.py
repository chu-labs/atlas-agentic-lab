"""Background threads: long-poll the mission-events SQS queue and sample queue depths.

Both loops catch everything. A bad message is logged and deleted; an AWS hiccup is logged and
retried after a short pause. The dashboard must never go dark because a poll failed.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from functools import lru_cache

from .hub import hub
from .settings import settings

log = logging.getLogger(__name__)


@lru_cache
def _sqs():
    import boto3

    return boto3.client("sqs", region_name=settings().aws_region)


def start() -> list[threading.Thread]:
    threads: list[threading.Thread] = []
    s = settings()
    if s.queue_url_mission_events:
        t = threading.Thread(target=_poll_events, args=(s.queue_url_mission_events,), name="sqs-events", daemon=True)
        t.start()
        threads.append(t)
    else:
        log.info("QUEUE_URL_MISSION_EVENTS empty; not polling")
    if s.queue_urls():
        t = threading.Thread(target=_sample_depths, name="sqs-depths", daemon=True)
        t.start()
        threads.append(t)
    if s.ops_poll:
        from . import ops

        threads.append(ops.start_poller())
    return threads


def _poll_events(queue_url: str) -> None:
    log.info("polling", extra={"queue_url": queue_url})
    while True:
        try:
            resp = _sqs().receive_message(QueueUrl=queue_url, MaxNumberOfMessages=10, WaitTimeSeconds=20)
            for m in resp.get("Messages", []):
                try:
                    body = json.loads(m["Body"])
                    if isinstance(body, dict) and "detail" in body:
                        hub().ingest(body)
                    else:
                        log.warning("skipping non-event message", extra={"body": m["Body"][:200]})
                except Exception:
                    log.exception("bad message", extra={"body": m.get("Body", "")[:300]})
                finally:
                    try:
                        _sqs().delete_message(QueueUrl=queue_url, ReceiptHandle=m["ReceiptHandle"])
                    except Exception:
                        log.exception("delete_message failed")
        except Exception:
            log.exception("receive_message failed; retrying")
            time.sleep(5)


def _sample_depths(interval: float = 5.0) -> None:
    while True:
        depths: dict[str, int] = {}
        for name, url in settings().queue_urls().items():
            try:
                attrs = _sqs().get_queue_attributes(
                    QueueUrl=url, AttributeNames=["ApproximateNumberOfMessages", "ApproximateNumberOfMessagesNotVisible"]
                )["Attributes"]
                depths[name] = int(attrs.get("ApproximateNumberOfMessages", 0)) + int(
                    attrs.get("ApproximateNumberOfMessagesNotVisible", 0)
                )
            except Exception:
                log.exception("queue depth failed", extra={"queue": name})
        try:
            hub().set_queues(depths)
        except Exception:
            log.exception("set_queues failed")
        time.sleep(interval)
