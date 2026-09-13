"""Fallback: capture a full run from Mission Control and replay it."""
from __future__ import annotations

import json
from pathlib import Path

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
        events = c.get(f"/api/recordings/{name}").json()["events"]
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


def video(name: str, out: Path | None = None, speed: float = 1.0, port: int = 8791) -> Path:
    """Render a recording to MP4 by replaying it into a local Mission Control inside a headless browser.

    Never touches the production dashboard. Needs the local docker-compose Postgres (55433),
    ffmpeg, and `playwright install chromium`.
    """
    import os
    import shutil
    import subprocess
    import tempfile
    import time

    from playwright.sync_api import sync_playwright

    f = RECORDINGS / f"{name}.json"
    if not f.exists():
        raise SystemExit(f"no local recording file {f}; run `labctl record save {name}` first")
    events = json.loads(f.read_text())
    if not events:
        raise SystemExit("recording is empty")
    t0 = _ts(events[0]["time"])
    t1 = _ts(events[-1]["time"])
    duration = max(5.0, (t1 - t0) / speed) + 6.0

    mc_dir = REPO_ROOT / "mission-control"
    env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"} | {
        "DB_HOST": "localhost", "DB_PORT": "55433", "DB_USER": "atlas", "DB_PASSWORD": "atlas", "DB_NAME": f"mission_video_{int(time.time())}",
        "BASIC_AUTH_USER": "", "EVENT_BUS": "", "QUEUE_URL_MISSION_EVENTS": "",
    }
    server = subprocess.Popen(["uv", "run", "uvicorn", "mission.main:app", "--port", str(port)], cwd=mc_dir, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        base = f"http://127.0.0.1:{port}"
        for _ in range(60):
            try:
                if httpx.get(f"{base}/health", timeout=2).status_code == 200:
                    break
            except Exception:  # noqa: BLE001
                pass
            time.sleep(1)
        httpx.post(f"{base}/api/recordings", json={"name": name, "events": events}, timeout=60).raise_for_status()
        tmp = Path(tempfile.mkdtemp(prefix="atlas-video-"))
        with sync_playwright() as p:
            browser = p.chromium.launch()
            ctx = browser.new_context(viewport={"width": 1920, "height": 1080}, record_video_dir=str(tmp), record_video_size={"width": 1920, "height": 1080})
            page = ctx.new_page()
            page.goto(base, wait_until="networkidle")
            time.sleep(3)
            httpx.post(f"{base}/api/replay", json={"name": name, "speed": speed}, timeout=30).raise_for_status()
            time.sleep(duration)
            page.close()
            ctx.close()
            browser.close()
        webm = next(tmp.glob("*.webm"))
        out = out or (RECORDINGS / f"{name}.mp4")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(webm), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30", str(out)], check=True)
        shutil.rmtree(tmp, ignore_errors=True)
        return out
    finally:
        server.terminate()
        try:
            import psycopg

            with psycopg.connect(host="localhost", port=55433, user="atlas", password="atlas", dbname="postgres", autocommit=True) as c:
                c.execute(f'drop database if exists "{env["DB_NAME"]}" with (force)')
        except Exception:  # noqa: BLE001
            pass


def _ts(s: str) -> float:
    from datetime import datetime

    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
