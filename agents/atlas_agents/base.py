"""The shape every agent shares: a definition, an emitter, a board identity, a queue loop."""
from __future__ import annotations

import logging
import time

from . import authority, events
from .board import Board
from .config import config

log = logging.getLogger(__name__)


class Agent:
    queue_env = "queue_url"

    def __init__(self):
        c = config()
        self.cfg = c
        self.me = authority.load(c.agent_name)
        self.emitter = events.Emitter(self.me)
        self.board = Board(self.me.name)
        self.current_ticket: str | None = None
        self._last_idle = 0.0

    # --- lifecycle --------------------------------------------------------
    def start(self) -> None:
        try:
            self.board.register(self.me)
        except Exception:
            log.exception("board registration failed; continuing")
        self.emitter.status("idle", f"{self.me.display_name} online. {self.me.remit}")
        queue = getattr(self.cfg, self.queue_env)
        log.info("polling", extra={"queue": queue})
        for _ in events.poll(queue, self._dispatch, idle=self._idle):
            pass

    def _dispatch(self, body: dict) -> None:
        source, detail_type, detail = events.unwrap(body)
        self.handle(source, detail_type, detail)

    def _idle(self) -> None:
        # Heartbeat at most every 60s so the fleet card shows liveness without spamming the timeline.
        if time.time() - self._last_idle > 60:
            self._last_idle = time.time()
            self.emitter.status("idle", "Waiting for work", heartbeat=True)

    # --- helpers for subclasses ------------------------------------------
    def think(self, ticket: str | None, text: str, status: str = "working") -> None:
        """One thought: to the board activity log (if a ticket) and to the fleet card."""
        if ticket:
            try:
                self.board.reasoning(ticket, text)
            except Exception:
                log.exception("could not write reasoning to board")
        self.emitter.status(status, text, ticket=ticket)

    def guard(self, permission: str, action: str, ticket: str | None = None) -> bool:
        """Check authority; on violation, record it visibly and return False."""
        try:
            self.me.require(permission, action)
            return True
        except authority.AuthorityViolation as e:
            self.emitter.emit("authority.blocked", ticket, f"Blocked by policy: {e}", permission=permission, action=action)
            if ticket:
                try:
                    self.board.reasoning(ticket, f"I wanted to {action}, but my authority does not allow it ({permission} is false). Stopping here and leaving this for a human.")
                except Exception:
                    log.exception("could not record the block on the board")
            return False

    def handle(self, source: str, detail_type: str, detail: dict) -> None:  # pragma: no cover - abstract
        raise NotImplementedError
