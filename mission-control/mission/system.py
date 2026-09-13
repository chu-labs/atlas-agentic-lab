"""Environment strip: region, cluster and the image tag each service runs. ECS via boto3; degrades locally."""
from __future__ import annotations

import logging
import threading
import time

from . import __version__
from .settings import settings

log = logging.getLogger(__name__)
SERVICES = ["mission-control", "atlas-board", "atlas-platform"]
_cache: dict = {"at": 0.0, "data": None}
_lock = threading.Lock()


def fetch(force: bool = False) -> dict:
    with _lock:
        if not force and _cache["data"] is not None and time.time() - _cache["at"] < 60:
            return _cache["data"]
        s = settings()
        cluster = s.ecs_cluster or s.lab_name
        out: dict = {"region": s.aws_region, "cluster": cluster, "version": __version__, "image_tag": s.image_tag or None,
                     "services": [], "source": "ecs", "error": None}
        try:
            import boto3

            ecs = boto3.client("ecs", region_name=s.aws_region)
            resp = ecs.describe_services(cluster=cluster, services=SERVICES)
            defs = {}
            for svc in resp.get("services", []):
                td = svc.get("taskDefinition")
                image = None
                if td:
                    if td not in defs:
                        defs[td] = ecs.describe_task_definition(taskDefinition=td)["taskDefinition"]
                    image = (defs[td].get("containerDefinitions") or [{}])[0].get("image")
                out["services"].append(
                    {"name": svc["serviceName"], "status": svc.get("status"), "running": svc.get("runningCount"),
                     "desired": svc.get("desiredCount"), "image": image, "tag": (image or "").rsplit(":", 1)[-1] if image else None}
                )
        except Exception as e:  # noqa: BLE001 - anything from missing creds to no network
            out["source"] = "local"
            out["error"] = type(e).__name__
            out["services"] = [{"name": n, "status": "local" if n == "mission-control" else "unknown", "running": None, "desired": None,
                                "image": None, "tag": s.image_tag or "dev"} for n in SERVICES]
        _cache.update(at=time.time(), data=out)
        return out
