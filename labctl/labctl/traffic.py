"""Synthetic user traffic so the dashboard always has a pulse and defects get triggered.

Runs as a local background process (pid file in ~/.config/atlas-lab). Hits a realistic mix of
endpoints on the production ALB with the shared basic-auth credential.
"""
from __future__ import annotations

import json
import os
import random
import signal
import sys
import time
from pathlib import Path

import httpx

from .config import LOCAL_CFG

PID_FILE = LOCAL_CFG / "traffic.pid"
LOG_FILE = LOCAL_CFG / "traffic.log"


def _endpoints(rng: random.Random, building_ids: list[int], policy_numbers: list[str]):
    while True:
        r = rng.random()
        if r < 0.30:
            yield "GET", f"/api/policies?due_within_days={rng.choice([7, 14, 30, 30, 30, 60])}&limit={rng.choice([20, 50, 100])}"
        elif r < 0.50:
            yield "GET", f"/api/buildings/{rng.choice(building_ids)}/risk"
        elif r < 0.62:
            yield "POST", f"/api/policies/{rng.choice(policy_numbers)}/quote"
        elif r < 0.75:
            yield "GET", f"/api/buildings/{rng.choice(building_ids)}/claims"
        elif r < 0.85:
            yield "GET", f"/api/policies/{rng.choice(policy_numbers)}"
        elif r < 0.93:
            yield "GET", f"/api/buildings/{rng.choice(building_ids)}"
        else:
            yield "GET", "/api/stats"


def loop(base_url: str, user: str, password: str, rps: float) -> None:
    rng = random.Random()
    auth = (user, password) if user else None
    with httpx.Client(base_url=base_url, auth=auth, timeout=10) as c:
        # discover ids once; refresh occasionally
        def discover():
            b = [x["id"] for x in c.get("/api/buildings", params={"limit": 200}).json()]
            p = [x["policy_number"] for x in c.get("/api/policies", params={"limit": 300}).json()]
            return b or [1], p or ["ATL-100000"]

        buildings, policies = discover()
        gen = _endpoints(rng, buildings, policies)
        n = 0
        stats = {"ok": 0, "4xx": 0, "5xx": 0, "err": 0}
        while True:
            method, path = next(gen)
            try:
                r = c.request(method, path)
                key = "ok" if r.status_code < 400 else "4xx" if r.status_code < 500 else "5xx"
                stats[key] += 1
            except Exception:  # noqa: BLE001
                stats["err"] += 1
            n += 1
            if n % 50 == 0:
                LOG_FILE.write_text(json.dumps({"requests": n, **stats, "ts": time.time()}))
            if n % 500 == 0:
                buildings, policies = discover()
                gen = _endpoints(rng, buildings, policies)
            time.sleep(max(0.0, rng.expovariate(rps)))


def start(base_url: str, user: str, password: str, rps: float) -> int:
    if running():
        return int(PID_FILE.read_text())
    LOCAL_CFG.mkdir(parents=True, exist_ok=True)
    pid = os.fork()
    if pid == 0:
        os.setsid()
        sys.stdout = sys.stderr = open(LOCAL_CFG / "traffic.out", "a")  # noqa: SIM115
        try:
            loop(base_url, user, password, rps)
        finally:
            PID_FILE.unlink(missing_ok=True)
        os._exit(0)
    PID_FILE.write_text(str(pid))
    return pid


def stop() -> bool:
    if not running():
        return False
    os.kill(int(PID_FILE.read_text()), signal.SIGTERM)
    PID_FILE.unlink(missing_ok=True)
    return True


def running() -> bool:
    if not PID_FILE.exists():
        return False
    try:
        os.kill(int(PID_FILE.read_text()), 0)
        return True
    except OSError:
        PID_FILE.unlink(missing_ok=True)
        return False


def stats() -> dict:
    return json.loads(LOG_FILE.read_text()) if LOG_FILE.exists() else {}
