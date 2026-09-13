"""Thin proxy to atlas-board so the presenter can file and assign work from Mission Control.

Every call goes out as the human (X-Actor = BOARD_ACTOR, default "maroun") with the lab's basic
auth. Assigning an issue to Forge is what puts it on Forge's queue: the board emits issue.assigned.
"""
from __future__ import annotations

import logging

import httpx
from fastapi import HTTPException

from .settings import settings

log = logging.getLogger(__name__)
transport: httpx.BaseTransport | None = None  # tests inject an httpx.MockTransport


def actor() -> str:
    return settings().board_actor or "maroun"


def client() -> httpx.Client:
    s = settings()
    if not s.board_url:
        raise HTTPException(503, "BOARD_URL is not set: Mission Control cannot reach the board")
    auth = (s.basic_auth_user, s.basic_auth_pass) if s.basic_auth_user else None
    return httpx.Client(
        base_url=s.board_url.rstrip("/"), auth=auth, headers={"X-Actor": actor(), "Accept": "application/json"},
        timeout=15, transport=transport,
    )


def call(method: str, path: str, **kw):
    try:
        with client() as c:
            r = c.request(method, path, **kw)
    except httpx.HTTPError as e:
        raise HTTPException(502, f"board unreachable: {e}") from e
    if r.status_code >= 400:
        detail = r.text[:300]
        try:
            detail = r.json().get("detail", detail)
        except ValueError:
            pass
        raise HTTPException(r.status_code if r.status_code < 500 else 502, f"board said: {detail}")
    return r.json() if r.content else None


def list_issues(limit: int = 200) -> list[dict]:
    return call("GET", "/api/issues", params={"limit": limit})


def get_issue(key: str) -> dict:
    return call("GET", f"/api/issues/{key}")


def list_users() -> list[dict]:
    return call("GET", "/api/users")


def create_issue(body: dict) -> dict:
    return call("POST", "/api/issues", json=body)


def assign(key: str, handle: str | None) -> dict:
    return call("PATCH", f"/api/issues/{key}", json={"assignee": handle})


def transition(key: str, status: str, body: str | None = None) -> dict:
    return call("POST", f"/api/issues/{key}/transition", json={"status": status, "body": body})
