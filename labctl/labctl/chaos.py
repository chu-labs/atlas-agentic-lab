"""Infrastructure incidents on demand, so Operations has something real to show."""
from __future__ import annotations

import time

from . import bus
from .aws import client
from .config import outputs


def kill_task(service: str = "atlas-platform") -> dict:
    """Stop the running task of a service. ECS replaces it in about a minute; the ALB returns 503s meanwhile."""
    ecs = client("ecs")
    tasks = ecs.list_tasks(cluster=outputs().cluster, serviceName=service, desiredStatus="RUNNING")["taskArns"]
    if not tasks:
        raise SystemExit(f"no running task for {service}")
    ecs.stop_task(cluster=outputs().cluster, task=tasks[0], reason="labctl chaos kill-task")
    bus.emit("chaos.injected", f"Chaos: killed the running {service} task; ECS is replacing it", scenario="kill-task", service=service)
    return {"stopped": tasks[0].rsplit("/", 1)[-1], "service": service, "at": time.time()}


def scale_down(service: str = "atlas-platform", seconds: int = 90) -> dict:
    """Scale a service to zero for `seconds`, then back to one: a short, total outage."""
    ecs = client("ecs")
    ecs.update_service(cluster=outputs().cluster, service=service, desiredCount=0)
    bus.emit("chaos.injected", f"Chaos: scaled {service} to zero for {seconds}s", scenario="outage", service=service)
    time.sleep(seconds)
    ecs.update_service(cluster=outputs().cluster, service=service, desiredCount=1)
    bus.emit("chaos.resolved", f"Chaos: {service} scaled back to one", scenario="outage", service=service)
    return {"service": service, "outage_seconds": seconds}
