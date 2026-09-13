"""Fallback: capture a full run from Mission Control and replay it."""
from __future__ import annotations

import json

import httpx

from .config import LOCAL_CFG, REPO_ROOT, outputs

RECORDINGS = REPO_ROOT / "recordings"


def _client() -> httpx.Client:
    from .defects import _basic_auth

    return httpx.Client(base_url=outputs().urls["mission-control"], auth=_basic_auth(), timeout=120)


def mark() -> int:
    """Return the current last event id, to record from."""
    with _client() as c:
        ev = c.get("/api/events", params={"limit": 1}).json()
    LOCAL_CFG.mkdir(parents=True, exist_ok=True)
    last = ev[-1]["id"] if ev else 0
    (LOCAL_CFG / "record-mark").write_text(str(last))
    return last


def save(name: str) -> dict:
    since = int((LOCAL_CFG / "record-mark").read_text()) if (LOCAL_CFG / "record-mark").exists() else 0
    with _client() as c:
        r = c.post("/api/recordings", json={"name": name, "since_event_id": since})
        r.raise_for_status()
        rec = r.json()
        events = c.get("/api/events", params={"after": since, "limit": 5000}).json()
    RECORDINGS.mkdir(exist_ok=True)
    (RECORDINGS / f"{name}.json").write_text(json.dumps(events, indent=1, default=str))
    return {"name": name, "events": len(events), "file": str(RECORDINGS / f"{name}.json")}


def replay(name: str, speed: float = 1.0) -> dict:
    with _client() as c:
        names = [r["name"] for r in c.get("/api/recordings").json()]
        if name not in names:
            f = RECORDINGS / f"{name}.json"
            if not f.exists():
                raise SystemExit(f"no recording {name!r}; have {names} and files {[p.stem for p in RECORDINGS.glob('*.json')]}")
            c.post("/api/recordings", json={"name": name, "events": json.loads(f.read_text())}).raise_for_status()
        r = c.post("/api/replay", json={"name": name, "speed": speed})
        r.raise_for_status()
        return r.json()


def list_recordings() -> list[dict]:
    with _client() as c:
        return c.get("/api/recordings").json()
