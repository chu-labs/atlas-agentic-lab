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


def _endpoints(rng: random.Random, building_ids: list[int], policy_numbers: list[str], due_soon: list[str] | None = None, hot_buildings: list[int] | None = None):
    """Renewal-season shape: a good share of building and quote traffic goes to policies due soon."""
    hot = hot_buildings or building_ids

    def bld():
        return rng.choice(hot) if rng.random() < 0.5 else rng.choice(building_ids)

    while True:
        r = rng.random()
        if r < 0.30:
            yield "GET", f"/api/policies?due_within_days={rng.choice([7, 14, 30, 30, 30, 60])}&limit={rng.choice([20, 50, 100, 200, 500])}"
        elif r < 0.33:
            yield "GET", f"/api/renewals/reconcile?days={rng.choice([14, 30, 30, 60])}"
        elif r < 0.50:
            yield "GET", f"/api/buildings/{bld()}/risk"
        elif r < 0.62:
            yield "POST", f"/api/policies/{rng.choice(policy_numbers)}/quote"
        elif r < 0.66:
            yield "POST", f"/api/policies/{rng.choice(due_soon or policy_numbers)}/quote"
        elif r < 0.75:
            yield "GET", f"/api/buildings/{bld()}/claims"
        elif r < 0.85:
            yield "GET", f"/api/policies/{rng.choice(policy_numbers)}"
        elif r < 0.93:
            yield "GET", f"/api/buildings/{bld()}"
        else:
            yield "GET", "/api/stats"


def loop(base_url: str, user: str, password: str, rps: float) -> None:
    rng = random.Random()
    auth = (user, password) if user else None
    with httpx.Client(base_url=base_url, auth=auth, timeout=10) as c:
        # discover ids once; refresh occasionally
        def discover():
            b = [x["id"] for x in c.get("/api/buildings", params={"limit": 500, "offset": rng.randint(0, 2000)}).json()]
            p = [x["policy_number"] for x in c.get("/api/policies", params={"limit": 500}).json()]
            due = c.get("/api/policies", params={"due_within_days": 30, "limit": 500}).json()
            d = [x["policy_number"] for x in due if x.get("days_until_expiry", 99) <= 2]
            hot = [x["building_id"] for x in due]
            return b or [1], p or ["ATL-100000"], d, hot

        buildings, policies, due_soon, hot = discover()
        gen = _endpoints(rng, buildings, policies, due_soon, hot)
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
                buildings, policies, due_soon, hot = discover()
                gen = _endpoints(rng, buildings, policies, due_soon, hot)
            time.sleep(max(0.0, rng.expovariate(rps)))


def start(base_url: str, user: str, password: str, rps: float) -> int:
    """Launch the traffic loop as a detached process; credentials go via the environment."""
    import subprocess

    if running():
        return int(PID_FILE.read_text())
    LOCAL_CFG.mkdir(parents=True, exist_ok=True)
    out = open(LOCAL_CFG / "traffic.out", "a")  # noqa: SIM115
    env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"} | {"ATLAS_TRAFFIC_USER": user, "ATLAS_TRAFFIC_PASS": password}
    proc = subprocess.Popen(
        [sys.executable, "-m", "labctl.traffic", base_url, str(rps)],
        stdout=out, stderr=out, stdin=subprocess.DEVNULL, start_new_session=True, env=env,
    )
    PID_FILE.write_text(str(proc.pid))
    return proc.pid


if __name__ == "__main__":
    _url, _rps = sys.argv[1], float(sys.argv[2])
    try:
        loop(_url, os.environ.get("ATLAS_TRAFFIC_USER", ""), os.environ.get("ATLAS_TRAFFIC_PASS", ""), _rps)
    finally:
        PID_FILE.unlink(missing_ok=True)


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
