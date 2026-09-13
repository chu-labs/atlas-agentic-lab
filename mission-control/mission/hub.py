"""The in-process hub: one State, one event sink, one WebSocket fan-out.

`ingest()` is the single entry point for every event whether it came from SQS, a replay, the demo
feed or our own gate actions. It persists, folds into state, broadcasts, and publishes follow-ups.
Thread-safe: SQS and replay threads call it; the ASGI loop reads from it.
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from datetime import UTC, datetime, timedelta
from functools import lru_cache

from .db import repo
from .db.pool import conn
from .settings import settings
from .state import State, iso, normalise, parse_ts

log = logging.getLogger(__name__)


class Broadcaster:
    """Fan-out to WebSocket clients from any thread. Each client owns an asyncio.Queue."""

    def __init__(self):
        self.loop: asyncio.AbstractEventLoop | None = None
        self.queues: set[asyncio.Queue] = set()
        self._lock = threading.Lock()

    def attach(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        with self._lock:
            self.queues.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        with self._lock:
            self.queues.discard(q)

    def send(self, message: dict) -> None:
        if not self.loop or self.loop.is_closed():
            return
        payload = json.dumps(message, default=str)
        with self._lock:
            targets = list(self.queues)

        def _put():
            for q in targets:
                try:
                    q.put_nowait(payload)
                except asyncio.QueueFull:
                    pass

        try:
            self.loop.call_soon_threadsafe(_put)
        except RuntimeError:
            pass


class Hub:
    def __init__(self):
        self.state = State()
        self.broadcaster = Broadcaster()
        self._ingest_lock = threading.Lock()

    # ------------------------------------------------------------ reads

    def snapshot(self) -> dict:
        return self.state.snapshot(settings().baselines)

    def state_message(self) -> dict:
        return {"type": "state", **self.snapshot()}

    # ------------------------------------------------------------ writes

    def rebuild(self, limit: int = 2000) -> int:
        """Reset derived state and fold the last `limit` stored events back in (no follow-ups)."""
        with self._ingest_lock:
            self.state.reset()
            with conn() as c:
                rows = repo.recent_events(c, limit)
            for r in rows:
                self.state.apply(self._from_row(r), emit=False)
            return len(rows)

    @staticmethod
    def _from_row(r: dict) -> dict:
        return {
            "id": r["id"],
            "received_at": r["received_at"],
            "ts": parse_ts(r["ts"]),
            "source": r["source"],
            "detail_type": r["detail_type"],
            "ticket": r["ticket"],
            "actor": r["actor"],
            "summary": r["summary"],
            "detail": r["detail"],
            "replay": r["replay"],
        }

    def ingest(self, raw: dict, *, replay: bool = False) -> dict:
        """Persist one EventBridge-shaped event, fold it in, broadcast, publish follow-ups."""
        e = normalise(raw, replay=replay)
        with self._ingest_lock:
            with conn() as c:
                row = repo.insert_event(c, e)
            stored = self._from_row(row)
            # Replay is pure playback: the recording already holds our own follow-ups.
            followups = self.state.apply(stored, emit=not replay)
        public = repo.serialise_event(row)
        self.broadcaster.send({"type": "event", "event": public})
        self.broadcaster.send(self.state_message())
        for detail_type, extra in followups:
            self._publish_followup(detail_type, extra)
        return public

    def _publish_followup(self, detail_type: str, extra: dict) -> None:
        from .bus import envelope, publish, system_actor

        try:
            summary = extra.pop("summary", detail_type)
            ticket = extra.pop("ticket", None)
            publish(detail_type, envelope(system_actor(), ticket, summary, **extra))
        except Exception:
            log.exception("follow-up publish failed", extra={"detail_type": detail_type})

    def set_queues(self, depths: dict[str, int]) -> None:
        with self.state.lock:
            self.state.queues = dict(depths)
        self.broadcaster.send({"type": "queues", "queues": dict(depths), "now": iso(datetime.now(UTC))})

    def reset(self) -> None:
        with self._ingest_lock:
            with conn() as c:
                repo.clear_events(c)
            self.state.reset()
        self.broadcaster.send(self.state_message())

    # ------------------------------------------------------------ recordings / replay

    def record(self, name: str, since_event_id: int) -> dict:
        with conn() as c:
            rows = repo.events_after(c, since_event_id, 100_000)
            events = [
                {
                    "source": r["source"],
                    "detail-type": r["detail_type"],
                    "time": iso(parse_ts(r["ts"])),
                    "detail": r["detail"],
                }
                for r in rows
            ]
            return repo.serialise_event(repo.save_recording(c, name, events))

    def replay(self, name: str, speed: float = 1.0) -> int:
        """Start replaying a recording in a background thread. Returns the number of events queued."""
        with conn() as c:
            rec = repo.get_recording(c, name)
        if not rec:
            raise KeyError(name)
        events: list[dict] = rec["events"]
        if not events:
            return 0
        speed = max(0.1, float(speed or 1.0))
        threading.Thread(target=self._replay_worker, args=(events, speed), name=f"replay:{name}", daemon=True).start()
        return len(events)

    def _replay_worker(self, events: list[dict], speed: float) -> None:
        origin = parse_ts(events[0].get("detail", {}).get("ts") or events[0].get("time"))
        started = datetime.now(UTC)
        wall_start = time.monotonic()
        for raw in events:
            orig = parse_ts(raw.get("detail", {}).get("ts") or raw.get("time"))
            offset = max(0.0, (orig - origin).total_seconds()) / speed
            delay = offset - (time.monotonic() - wall_start)
            if delay > 0:
                time.sleep(delay)
            shifted = started + timedelta(seconds=offset)
            detail = dict(raw.get("detail") or {})
            detail["original_ts"] = detail.get("ts")
            detail["ts"] = iso(shifted)
            try:
                self.ingest({**raw, "time": detail["ts"], "detail": detail}, replay=True)
            except Exception:
                log.exception("replay ingest failed")


@lru_cache
def hub() -> Hub:
    return Hub()
