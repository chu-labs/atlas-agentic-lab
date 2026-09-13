"""Build, push and roll out images; scale services; read health."""
from __future__ import annotations

import base64
import subprocess
import time
from pathlib import Path

from .aws import client
from .config import LAB_NAME, REPO_ROOT, outputs

PLATFORM_REPO = REPO_ROOT.parent / "atlas-platform"

# image name -> build context and which ECS services run it
IMAGES: dict[str, dict] = {
    "atlas-platform": {"context": PLATFORM_REPO, "services": ["atlas-platform"]},
    "atlas-board": {"context": REPO_ROOT / "board", "services": ["atlas-board"]},
    "mission-control": {"context": REPO_ROOT / "mission-control", "services": ["mission-control"]},
    "agent": {"context": REPO_ROOT / "agents", "dockerfile": "Dockerfile", "services": ["scout", "sentinel", "conductor", "watchtower"]},
    "forge": {"context": REPO_ROOT / "agents", "dockerfile": "Dockerfile.forge", "services": ["forge"]},
}


def ecr_login() -> str:
    auth = client("ecr").get_authorization_token()["authorizationData"][0]
    user, pw = base64.b64decode(auth["authorizationToken"]).decode().split(":", 1)
    registry = auth["proxyEndpoint"].removeprefix("https://")
    subprocess.run(["docker", "login", "--username", user, "--password-stdin", registry], input=pw, text=True, check=True, capture_output=True)
    return registry


def build_and_push(image: str, tag: str, context: Path | None = None, dockerfile: str | None = None) -> str:
    spec = IMAGES[image]
    ctx = context or spec["context"]
    df = dockerfile or spec.get("dockerfile", "Dockerfile")
    ecr_login()
    ref = f"{outputs().ecr[image]}:{tag}"
    subprocess.run(
        ["docker", "buildx", "build", "--platform", "linux/arm64", "-f", str(ctx / df), "-t", ref, "--push", str(ctx)],
        check=True,
    )
    return ref


def register_revision(service: str, image_ref: str, env_overrides: dict[str, str] | None = None) -> str:
    ecs = client("ecs")
    td = ecs.describe_task_definition(taskDefinition=f"{LAB_NAME}-{service}")["taskDefinition"]
    for k in ("taskDefinitionArn", "revision", "status", "requiresAttributes", "compatibilities", "registeredAt", "registeredBy"):
        td.pop(k, None)
    td["containerDefinitions"][0]["image"] = image_ref
    if env_overrides:
        env = {e["name"]: e["value"] for e in td["containerDefinitions"][0].get("environment", [])}
        env.update(env_overrides)
        td["containerDefinitions"][0]["environment"] = [{"name": k, "value": v} for k, v in env.items()]
    return ecs.register_task_definition(**td)["taskDefinition"]["taskDefinitionArn"]


def rollout(service: str, task_def_arn: str, desired: int | None = None, wait: bool = True) -> None:
    ecs = client("ecs")
    kwargs = {"cluster": outputs().cluster, "service": service, "taskDefinition": task_def_arn, "forceNewDeployment": True}
    if desired is not None:
        kwargs["desiredCount"] = desired
    ecs.update_service(**kwargs)
    if wait:
        ecs.get_waiter("services_stable").wait(cluster=outputs().cluster, services=[service], WaiterConfig={"Delay": 10, "MaxAttempts": 60})


def scale(service: str, desired: int, wait: bool = False) -> None:
    ecs = client("ecs")
    ecs.update_service(cluster=outputs().cluster, service=service, desiredCount=desired)
    if wait:
        ecs.get_waiter("services_stable").wait(cluster=outputs().cluster, services=[service], WaiterConfig={"Delay": 10, "MaxAttempts": 60})


def current_image(service: str) -> str:
    ecs = client("ecs")
    svc = ecs.describe_services(cluster=outputs().cluster, services=[service])["services"][0]
    td = ecs.describe_task_definition(taskDefinition=svc["taskDefinition"])["taskDefinition"]
    return td["containerDefinitions"][0]["image"]


def service_states() -> list[dict]:
    ecs = client("ecs")
    names = outputs().services
    out = []
    for i in range(0, len(names), 10):
        for s in ecs.describe_services(cluster=outputs().cluster, services=names[i : i + 10])["services"]:
            out.append(
                {
                    "service": s["serviceName"],
                    "desired": s["desiredCount"],
                    "running": s["runningCount"],
                    "pending": s["pendingCount"],
                    "image": current_image(s["serviceName"]).rsplit("/", 1)[-1],
                    "rollout": s["deployments"][0].get("rolloutState", "?") if s["deployments"] else "-",
                }
            )
    return sorted(out, key=lambda r: r["service"])


def queue_depths() -> dict[str, int]:
    sqs = client("sqs")
    out = {}
    for name, url in outputs().queues.items():
        a = sqs.get_queue_attributes(QueueUrl=url, AttributeNames=["ApproximateNumberOfMessages", "ApproximateNumberOfMessagesNotVisible"])["Attributes"]
        out[name] = int(a["ApproximateNumberOfMessages"]) + int(a["ApproximateNumberOfMessagesNotVisible"])
    return out


def wait_healthy(url: str, auth: tuple[str, str] | None, timeout: int = 180) -> bool:
    import httpx

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = httpx.get(f"{url}/health", timeout=5)
            if r.status_code == 200:
                return True
        except Exception:  # noqa: BLE001
            pass
        time.sleep(5)
    return False
