"""Operations: service health from ECS / ALB / CloudWatch, and the infra alerts derived from it.

`clients()` is the only place boto3 is touched, so tests inject fakes. Everything degrades to a
"local" view when AWS is unreachable. A poller (see consumer.start) refreshes every 15 s and emits
`infra.alert` (source atlas.ops) to the bus when a threshold trips, so Watchtower can act on it.
"""
from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from .settings import settings

log = logging.getLogger(__name__)
SERVICES = ["atlas-platform", "atlas-board", "mission-control"]
CACHE_SECONDS = 15
THRESHOLDS = {"elb_5xx_per_min": 5, "p95_ms": 2000, "under_capacity_seconds": 30}
ALERT_COOLDOWN = 300.0
DEPLOY_QUIET_SECONDS = 120.0  # after a rollout completes, its restarts and 5xx are still ours
CONFIRM_POLLS = 2  # a condition must hold on this many consecutive evaluations
ALB = "alb"  # the load-balancer-wide pseudo-service

_cache: dict = {"at": 0.0, "data": None}
_lock = threading.Lock()
_under_since: dict[str, float] = {}  # service -> when running first dropped below desired
_last_alert: dict[str, float] = {}  # service:rule -> last emitted
_deploying: dict[str, bool] = {}  # service -> rollout in progress at the last evaluation
_quiet_until: dict[str, float] = {}  # service -> end of the post-deploy quiet window
_streak: dict[str, int] = {}  # service:rule -> consecutive evaluations the condition held


def reset_alert_state() -> None:
    for d in (_under_since, _last_alert, _deploying, _quiet_until, _streak):
        d.clear()


def _boto_clients() -> dict:
    import boto3

    r = settings().aws_region
    return {"ecs": boto3.client("ecs", region_name=r), "elbv2": boto3.client("elbv2", region_name=r),
            "cloudwatch": boto3.client("cloudwatch", region_name=r), "sts": boto3.client("sts", region_name=r)}


clients: Callable[[], dict] = _boto_clients  # tests replace this


def _tag(image: str | None) -> str | None:
    return image.rsplit(":", 1)[-1] if image and ":" in image else None


def _q(metric: str, stat: str, dims: list[dict], mid: str) -> dict:
    return {"Id": mid, "MetricStat": {"Metric": {"Namespace": "AWS/ApplicationELB", "MetricName": metric, "Dimensions": dims}, "Period": 60, "Stat": stat}, "ReturnData": True}


def fetch(force: bool = False, now: datetime | None = None) -> dict:
    """Health for the three services. Cached; never raises."""
    with _lock:
        if not force and _cache["data"] is not None and time.time() - _cache["at"] < CACHE_SECONDS:
            return _cache["data"]
        now = now or datetime.now(UTC)
        s = settings()
        cluster = s.ecs_cluster or s.lab_name
        out: dict = {"fetched_at": now.isoformat(timespec="seconds").replace("+00:00", "Z"), "region": s.aws_region, "cluster": cluster,
                     "source": "aws", "error": None, "services": []}
        try:
            c = clients()
            out["services"] = _collect(c, cluster, now)
        except Exception as e:  # noqa: BLE001 - creds, network, permissions: all mean "local view"
            out["source"] = "local"
            out["error"] = f"{type(e).__name__}: {str(e)[:120]}"
            out["services"] = [_blank(n) for n in SERVICES]
        _cache.update(at=time.time(), data=out)
        return out


def _blank(name: str) -> dict:
    return {"name": name, "desired": None, "running": None, "status": "unknown", "image_tag": None,
            "deployment": None, "targets": None, "metrics": None}


def _resolve_alb(c: dict) -> tuple[str | None, dict[str, str], dict[str, str]]:
    """(LoadBalancer dimension, {service: TargetGroup dimension}, {service: full target group ARN}).

    Prefers ALB_ARN_SUFFIX / TARGET_GROUP_SUFFIXES from the task definition; falls back to discovery by name.
    """
    s = settings()
    elbv2 = c["elbv2"]
    lb_dim = s.alb_arn_suffix or None
    tg_dims = s.target_groups()
    tg_arns: dict[str, str] = {}
    if lb_dim and tg_dims:
        account = None
        try:
            account = c["sts"].get_caller_identity()["Account"]
        except Exception:  # noqa: BLE001
            account = None
        if account:
            tg_arns = {n: f"arn:aws:elasticloadbalancing:{s.aws_region}:{account}:{suffix}" for n, suffix in tg_dims.items()}
        else:  # no STS: match the suffixes against the account's target groups
            for tg in elbv2.describe_target_groups().get("TargetGroups", []):
                for n, suffix in tg_dims.items():
                    if tg["TargetGroupArn"].endswith(suffix):
                        tg_arns[n] = tg["TargetGroupArn"]
        return lb_dim, tg_dims, tg_arns
    # discovery: the lab's load balancer and target groups named after the services
    cluster = s.ecs_cluster or s.lab_name
    lbs = elbv2.describe_load_balancers().get("LoadBalancers", [])
    lb = next((x for x in lbs if cluster in x.get("LoadBalancerName", "")), lbs[0] if lbs else None)
    lb_dim = lb["LoadBalancerArn"].split("loadbalancer/", 1)[-1] if lb else None
    for tg in elbv2.describe_target_groups().get("TargetGroups", []):
        for n in SERVICES:
            if n in tg.get("TargetGroupName", ""):
                tg_arns[n] = tg["TargetGroupArn"]
                tg_dims[n] = tg["TargetGroupArn"].split(":", 5)[-1]
    return lb_dim, tg_dims, tg_arns


def _collect(c: dict, cluster: str, now: datetime) -> list[dict]:
    ecs, elbv2, cw = c["ecs"], c["elbv2"], c["cloudwatch"]
    svcs = {sv["serviceName"]: sv for sv in ecs.describe_services(cluster=cluster, services=SERVICES).get("services", [])}
    lb_dim, tg_dims, tg_arns = _resolve_alb(c)
    out = []
    for name in SERVICES:
        sv = svcs.get(name)
        row = _blank(name)
        if sv:
            td = sv.get("taskDefinition")
            image = None
            if td:
                try:
                    image = (ecs.describe_task_definition(taskDefinition=td)["taskDefinition"].get("containerDefinitions") or [{}])[0].get("image")
                except Exception:  # noqa: BLE001
                    image = None
            deps = sv.get("deployments") or []
            primary = next((d for d in deps if d.get("status") == "PRIMARY"), deps[0] if deps else None)
            row.update(
                desired=sv.get("desiredCount"), running=sv.get("runningCount"), pending=sv.get("pendingCount"), status=sv.get("status"),
                image_tag=_tag(image), image=image,
                deployment={"status": primary.get("status"), "rollout_state": primary.get("rolloutState"), "created_at": str(primary.get("createdAt")),
                            "updated_at": str(primary.get("updatedAt")), "in_progress": len(deps) > 1 or primary.get("rolloutState") == "IN_PROGRESS"} if primary else None,
            )
        tg_arn = tg_arns.get(name)
        if tg_arn:
            try:
                th = elbv2.describe_target_health(TargetGroupArn=tg_arn).get("TargetHealthDescriptions", [])
                states = [t.get("TargetHealth", {}).get("State") for t in th]
                row["targets"] = {"healthy": states.count("healthy"), "unhealthy": sum(1 for x in states if x not in {"healthy", None}), "total": len(states), "states": states}
            except Exception:  # noqa: BLE001
                log.warning("describe_target_health failed for %s", name, exc_info=True)
                row["targets"] = None
        tg_dim = tg_dims.get(name)
        if lb_dim and tg_dim:
            dims = [{"Name": "LoadBalancer", "Value": lb_dim}, {"Name": "TargetGroup", "Value": tg_dim}]
            lb_only = [{"Name": "LoadBalancer", "Value": lb_dim}]
            try:
                res = cw.get_metric_data(
                    MetricDataQueries=[
                        _q("RequestCount", "Sum", dims, "req"), _q("HTTPCode_Target_5XX_Count", "Sum", dims, "t5"),
                        _q("HTTPCode_ELB_5XX_Count", "Sum", lb_only, "e5"), _q("TargetResponseTime", "p95", dims, "p95"),
                        _q("UnHealthyHostCount", "Maximum", dims, "unh"),
                    ],
                    StartTime=now - timedelta(minutes=5), EndTime=now, ScanBy="TimestampDescending",
                )
                vals = {r["Id"]: r.get("Values") or [] for r in res.get("MetricDataResults", [])}
                row["metrics"] = {
                    "request_count": sum(vals.get("req", [])), "target_5xx": sum(vals.get("t5", [])), "elb_5xx": sum(vals.get("e5", [])),
                    "elb_5xx_last_min": (vals.get("e5") or [0])[0], "p95_ms": round(max(vals.get("p95") or [0]) * 1000),
                    "unhealthy_hosts": max(vals.get("unh") or [0]), "window_minutes": 5,
                    "dimensions": {"LoadBalancer": lb_dim, "TargetGroup": tg_dim},
                }
            except Exception:  # noqa: BLE001
                log.warning("get_metric_data failed for %s", name, exc_info=True)
                row["metrics"] = None
        out.append(row)
    return out


def conditions(services: list[dict], now_s: float | None = None) -> list[dict]:
    """Raw threshold breaches this instant. ELB 5xx is load-balancer-wide, so it is reported once as `alb`."""
    now_s = now_s if now_s is not None else time.time()
    out: list[dict] = []
    elb_5xx = 0.0
    for sv in services:
        name = sv["name"]
        m = sv.get("metrics") or {}
        t = sv.get("targets") or {}
        elb_5xx = max(elb_5xx, float(m.get("elb_5xx_last_min") or 0))
        unhealthy = max(int(m.get("unhealthy_hosts") or 0), int(t.get("unhealthy") or 0))
        if unhealthy > 0:
            out.append({"service": name, "rule": "unhealthy_hosts", "value": unhealthy, "threshold": 0,
                        "summary": f"{name}: {unhealthy} unhealthy target{'s' if unhealthy != 1 else ''} behind the load balancer"})
        p95 = float(m.get("p95_ms") or 0)
        if p95 > THRESHOLDS["p95_ms"]:
            out.append({"service": name, "rule": "latency_p95", "value": p95, "threshold": THRESHOLDS["p95_ms"],
                        "summary": f"{name}: p95 latency {p95 / 1000:.1f} s over the last 5 min"})
        desired, running = sv.get("desired"), sv.get("running")
        if desired is not None and running is not None and running < desired:
            since = _under_since.setdefault(name, now_s)
            if now_s - since > THRESHOLDS["under_capacity_seconds"]:
                out.append({"service": name, "rule": "under_capacity", "value": running, "threshold": desired,
                            "summary": f"{name}: {running} of {desired} tasks running for {int(now_s - since)} s"})
        else:
            _under_since.pop(name, None)
    if elb_5xx > THRESHOLDS["elb_5xx_per_min"]:
        out.append({"service": ALB, "rule": "elb_5xx", "value": elb_5xx, "threshold": THRESHOLDS["elb_5xx_per_min"],
                    "summary": f"Load balancer: {int(elb_5xx)} ELB 5xx in the last minute"})
    return out


def _update_deploy_windows(services: list[dict], now_s: float) -> set[str]:
    """Services whose alerts are ours to ignore: rolling out now, or within DEPLOY_QUIET_SECONDS of finishing."""
    quiet: set[str] = set()
    for sv in services:
        name = sv["name"]
        rolling = bool((sv.get("deployment") or {}).get("in_progress"))
        if rolling:
            quiet.add(name)
        elif _deploying.get(name):  # just finished
            _quiet_until[name] = now_s + DEPLOY_QUIET_SECONDS
        _deploying[name] = rolling
        if now_s < _quiet_until.get(name, 0.0):
            quiet.add(name)
    return quiet


def evaluate_alerts(services: list[dict], now_s: float | None = None) -> list[dict]:
    """Conditions that survive the deploy windows and have held for CONFIRM_POLLS consecutive evaluations.

    A task killed outside a deployment (labctl chaos kill-task) leaves rollout COMPLETED with running < desired,
    so under_capacity and unhealthy_hosts still fire for it once confirmed.
    """
    now_s = now_s if now_s is not None else time.time()
    quiet = _update_deploy_windows(services, now_s)
    raw = conditions(services, now_s)
    live_keys: set[str] = set()
    out: list[dict] = []
    for a in raw:
        suppressed = (a["service"] in quiet) or (a["service"] == ALB and bool(quiet))
        if suppressed:
            continue
        key = f"{a['service']}:{a['rule']}"
        live_keys.add(key)
        _streak[key] = _streak.get(key, 0) + 1
        if _streak[key] >= CONFIRM_POLLS:
            out.append({**a, "confirmed_polls": _streak[key], "deploy_quiet": sorted(quiet)})
    for key in [k for k in _streak if k not in live_keys]:
        _streak.pop(key, None)
    return out


def alert_event(a: dict) -> dict:
    display = "Load balancer" if a["service"] == ALB else a["service"]
    return {
        "actor": {"handle": "ops", "kind": "system", "display_name": "Ops monitor", "mode": None},
        "summary": a["summary"], "kind": "infra", "service": a["service"], "service_display": display, "rule": a["rule"],
        "value": a["value"], "threshold": a["threshold"], "signature": f"infra:{a['service']}:{a['rule']}",
        "endpoint": display, "error_type": a["rule"], "message": a["summary"],
    }


def poll_once(publish: Callable[[str, dict], None], now_s: float | None = None) -> list[dict]:
    """Refresh health, evaluate the rules, emit new alerts (cooldown per service+rule). Returns what fired."""
    data = fetch(force=True)
    if data["source"] != "aws":
        return []
    now_s = now_s if now_s is not None else time.time()
    fired = []
    for a in evaluate_alerts(data["services"], now_s):
        key = f"{a['service']}:{a['rule']}"
        if now_s - _last_alert.get(key, 0.0) < ALERT_COOLDOWN:
            continue
        _last_alert[key] = now_s
        fired.append(a)
        try:
            publish("infra.alert", alert_event(a))
        except Exception:  # noqa: BLE001
            log.exception("infra.alert publish failed")
    data["alerts"] = fired
    return fired


def start_poller() -> threading.Thread:
    def loop():
        from .bus import envelope, publish

        while True:
            try:
                poll_once(lambda dt, d: publish(dt, {**envelope(d.pop("actor"), None, d.pop("summary"), **d)}))
            except Exception:  # noqa: BLE001
                log.exception("ops poll failed")
            time.sleep(CACHE_SECONDS if (_cache["data"] or {}).get("source") == "aws" else 60)

    t = threading.Thread(target=loop, name="ops-health", daemon=True)
    t.start()
    return t
