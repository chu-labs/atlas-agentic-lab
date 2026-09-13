"""Client for atlas-board. Every write carries the agent's handle so it shows up as that agent."""
from __future__ import annotations

import logging

import httpx

from .config import config

log = logging.getLogger(__name__)


class Board:
    def __init__(self, actor: str, base_url: str | None = None):
        c = config()
        self.actor = actor
        self.http = httpx.Client(
            base_url=base_url or c.board_url, auth=c.basic_auth, timeout=20, headers={"X-Actor": actor}
        )

    def _j(self, r: httpx.Response):
        r.raise_for_status()
        return r.json() if r.content else None

    def register(self, agent_def) -> dict:
        return self._j(
            self.http.post(
                "/api/users",
                json={
                    "handle": agent_def.name,
                    "display_name": agent_def.display_name,
                    "kind": "agent",
                    "avatar": agent_def.avatar,
                    "color": agent_def.color,
                    "remit": agent_def.remit,
                    "authority": agent_def.authority,
                    "mode": agent_def.mode,
                },
            )
        )

    def list_issues(self, **params) -> list[dict]:
        return self._j(self.http.get("/api/issues", params={k: v for k, v in params.items() if v is not None}))

    def get(self, key: str) -> dict:
        return self._j(self.http.get(f"/api/issues/{key}"))

    def create(self, **fields) -> dict:
        return self._j(self.http.post("/api/issues", json=fields))

    def update(self, key: str, **fields) -> dict:
        return self._j(self.http.patch(f"/api/issues/{key}", json=fields))

    def transition(self, key: str, status: str) -> dict:
        return self._j(self.http.post(f"/api/issues/{key}/transition", json={"status": status}))

    def comment(self, key: str, body: str) -> dict:
        return self._j(self.http.post(f"/api/issues/{key}/comments", json={"body": body}))

    def reasoning(self, key: str, body: str) -> dict:
        """Plain-English thinking, visible in the activity feed."""
        log.info("reasoning", extra={"ticket": key, "body": body})
        return self._j(self.http.post(f"/api/issues/{key}/reasoning", json={"body": body}))

    def escalate(self, key: str, to: str, body: str) -> dict:
        return self._j(self.http.post(f"/api/issues/{key}/escalate", json={"to": to, "body": body}))
