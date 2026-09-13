"""The four DORA metrics, computed from the derived ticket rows (which come from the event store).

deployment frequency = deploy.completed per day; lead time = pr.opened -> deploy.completed;
change failure rate = verify.failed / deploy.completed; time to restore = first error -> verify.passed.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from statistics import median

from .state import State, iso

WINDOWS = {"24h": timedelta(hours=24), "7d": timedelta(days=7), "all": None}


def _secs(a: datetime | None, b: datetime | None) -> float | None:
    return None if a is None or b is None else max(0.0, (b - a).total_seconds())


def compute(state: State, window: str = "7d", now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    span = WINDOWS.get(window, WINDOWS["7d"])
    since = now - span if span else None
    with state.lock:
        rows = [r for r in state.rows.values() if since is None or r["updated_ts"] >= since]
        tickets = []
        for r in sorted(rows, key=lambda r: r["first_ts"]):
            st = r["stages"]
            first = st.get("error") or r["first_ts"]
            tel = state.ticket_telemetry(r["ticket"], now)
            tickets.append(
                {
                    "ticket": r["ticket"], "title": r["title"], "closed": r["stage"] == "closed", "escalated": r["escalated"],
                    "first_ts": iso(first), "deployed_at": iso(st.get("deploy")), "verified_at": iso(st.get("verify")),
                    "error_to_pr": _secs(first, r.get("pr_ts") or st.get("pr")),
                    "pr_to_deploy": _secs(r.get("pr_ts") or st.get("pr"), st.get("deploy")),
                    "deploy_to_verified": _secs(st.get("deploy"), st.get("verify")),
                    "total": _secs(first, r.get("closed_ts") or st.get("verify") or st.get("deploy")),
                    "usd": round(float(tel.get("usd") or 0), 4),
                    "verify_failed": r["verify_failed"],
                }
            )
    deploys = [r for r in rows if r["stages"].get("deploy")]
    failures = [r for r in rows if r["verify_failed"]]
    if span:
        days = max(span.total_seconds() / 86400, 1e-9)
    else:
        oldest = min((r["first_ts"] for r in rows), default=now)
        days = max((now - oldest).total_seconds() / 86400, 1.0)
    lead = [t["pr_to_deploy"] for t in tickets if t["pr_to_deploy"] is not None]
    restore = [_secs(r["stages"].get("error") or r["first_ts"], r["stages"].get("verify")) for r in rows if r["stages"].get("verify") and not r["verify_failed"]]
    restore = [x for x in restore if x is not None]

    # trend: deploys per bucket (hourly for 24h, daily otherwise)
    bucket = timedelta(hours=1) if window == "24h" else timedelta(days=1)
    n = 24 if window == "24h" else (7 if window == "7d" else min(14, max(1, int(days) + 1)))
    start = now - bucket * n
    trend = []
    for i in range(n):
        lo, hi = start + bucket * i, start + bucket * (i + 1)
        trend.append({"label": lo.strftime("%H:%M" if window == "24h" else "%a %d"), "deploys": sum(1 for r in deploys if lo <= r["stages"]["deploy"] < hi)})
    return {
        "window": window, "days": round(days, 3), "now": iso(now),
        "deployment_frequency": {"count": len(deploys), "per_day": round(len(deploys) / days, 3) if days else 0.0},
        "lead_time": {"median_seconds": median(lead) if lead else None, "samples": len(lead)},
        "change_failure_rate": {"failures": len(failures), "deploys": len(deploys), "rate": (len(failures) / len(deploys)) if deploys else None},
        "time_to_restore": {"median_seconds": median(restore) if restore else None, "samples": len(restore)},
        "trend": trend,
        "tickets": tickets,
    }
