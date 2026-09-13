"""Inject a defect into production, and put everything back."""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

import httpx
import yaml

from . import bus, ecs, state
from .aws import client
from .config import GITHUB_ORG, LOCAL_CFG, REPO_ROOT, outputs

DEFECTS_DIR = REPO_ROOT / "demo" / "defects"
CLONE = LOCAL_CFG / "platform-clone"
PLATFORM_REPO_URL = f"https://github.com/{GITHUB_ORG}/atlas-platform.git"


def list_defects() -> list[dict]:
    out = []
    for d in sorted(DEFECTS_DIR.iterdir()):
        f = d / "defect.yaml"
        if f.exists():
            out.append(yaml.safe_load(f.read_text()) | {"dir": d})
    return out


def get(defect_id: str) -> dict:
    for d in list_defects():
        if d["id"] == defect_id:
            return d
    raise SystemExit(f"unknown defect {defect_id!r}; try: " + ", ".join(d["id"] for d in list_defects()))


def _git(*args: str, cwd: Path = CLONE, check: bool = True) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=check).stdout.strip()


def ensure_clone() -> Path:
    """A private clone of atlas-platform for injecting and resetting, never the developer checkout."""
    if not CLONE.exists():
        LOCAL_CFG.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "--quiet", PLATFORM_REPO_URL, str(CLONE)], check=True)
        _git("config", "user.name", "Maroun")
        _git("config", "user.email", "maroun@aboumaroun.com")
    _git("fetch", "--quiet", "origin")
    _git("checkout", "--quiet", "-B", "main", "origin/main")
    _git("reset", "--quiet", "--hard", "origin/main")
    _git("clean", "-fdq")
    return CLONE


def baseline_set(image: str | None = None, force: bool = False) -> dict:
    """Record origin/main as the clean baseline and the image in production as the clean image.

    Refuses while a defect is injected (the running image would be the defective one) unless
    `image` names the clean image explicitly or `force` is given.
    """
    st = state.load()
    if st.get("injected") and not (image or force):
        raise SystemExit(f"{st['injected']['id']} is injected; production is not clean. Run `labctl reset` first, or pass --image.")
    ensure_clone()
    sha = _git("rev-parse", "origin/main")
    image = image or ecs.current_image("atlas-platform")
    if "defect-" in image and not force:
        raise SystemExit(f"running image {image} is a defect build; deploy a clean build first (labctl deploy atlas-platform) or pass --force")
    return state.save(baseline_sha=sha, baseline_image=image, injected=None)


def inject(defect_id: str, no_deploy: bool = False, workbench: bool = False) -> dict:
    d = get(defect_id)
    st = state.load()
    if not st.get("baseline_sha"):
        baseline_set()
        st = state.load()
    if workbench:
        return _inject_for_workbench(d, st)
    if st.get("injected"):
        raise SystemExit(f"{st['injected']['id']} is already injected; run `labctl reset` first")

    if d.get("ticket"):  # the ambiguous one: a human files a ticket, no code changes
        t = d["ticket"]
        board = outputs().urls["atlas-board"]
        auth = _basic_auth()
        r = httpx.post(
            f"{board}/api/issues",
            auth=auth,
            headers={"X-Actor": t.get("reporter", "alex")},
            json={
                "type": t.get("type", "Bug"), "title": t["title"], "description": t["description"], "priority": t.get("priority", "High"),
                "labels": t.get("labels", []), "assignee": t.get("assignee", "forge"), "source": {"kind": "human_report", "defect": d["id"]},
            },
            timeout=20,
        )
        r.raise_for_status()
        key = r.json()["key"]
        bus.emit("defect.injected", f"Filed {key} as {t.get('reporter', 'alex')}: {t['title']}", defect=d["id"], ticket=key)
        return state.save(injected={"id": d["id"], "ticket": key, "at": time.time()})

    ensure_clone()
    subprocess.run(["git", "apply", str(d["dir"] / d["patch"])], cwd=CLONE, check=True)
    _git("add", "-A")
    _git("commit", "--quiet", "-m", f"{d['commit_message']}\n\n[skip ci]")
    sha = _git("rev-parse", "HEAD")
    _git("push", "--quiet", "origin", "main")

    if d.get("data_sql"):
        _run_sql((d["dir"] / d["data_sql"]).read_text())

    image = None
    if not no_deploy:
        tag = f"defect-{d['id']}-{sha[:8]}"
        image = ecs.build_and_push("atlas-platform", tag, context=CLONE)
        arn = ecs.register_revision("atlas-platform", image)
        ecs.rollout("atlas-platform", arn, desired=1, wait=True)
    bus.emit("defect.injected", f"Injected defect '{d['id']}' into production ({d['title']})", defect=d["id"], sha=sha, image=image)
    return state.save(injected={"id": d["id"], "sha": sha, "image": image, "data": bool(d.get("data_sql")), "at": time.time()})


def _file_ticket(t: dict, source: dict) -> str:
    board = outputs().urls["atlas-board"]
    r = httpx.post(
        f"{board}/api/issues",
        auth=_basic_auth(),
        headers={"X-Actor": t.get("reporter", "alex")},
        json={
            "type": t.get("type", "Bug"), "title": t["title"], "description": t["description"], "priority": t.get("priority", "High"),
            "labels": t.get("labels", []), "assignee": t.get("assignee"), "source": source,
        },
        timeout=20,
    )
    r.raise_for_status()
    return r.json()["key"]


def _inject_for_workbench(d: dict, st: dict) -> dict:
    """Supervised story: the defect lands on main (no deploy, no production errors) and a human files a ticket.

    The fleet ignores it (assigned to a human); the presenter assembles a Workbench team for it.
    """
    if st.get("workbench_injected"):
        raise SystemExit(f"{st['workbench_injected']['id']} is already injected for the workbench; run `labctl reset` first")
    t = d.get("workbench_ticket") or d.get("ticket")
    if not t:
        raise SystemExit(f"{d['id']} has no workbench_ticket block")
    ensure_clone()
    if d.get("patch"):
        subprocess.run(["git", "apply", str(d["dir"] / d["patch"])], cwd=CLONE, check=True)
        _git("add", "-A")
        _git("commit", "--quiet", "-m", f"{d['commit_message']}\n\n[skip ci]")
        _git("push", "--quiet", "origin", "main")
    sha = _git("rev-parse", "HEAD")
    key = _file_ticket(t, {"kind": "human_report", "defect": d["id"], "mode": "supervised"})
    bus.emit("defect.injected", f"Workbench: {t.get('reporter')} filed {key} ({t['title']}); defect on main, not deployed", defect=d["id"], ticket=key, sha=sha, mode="supervised")
    return state.save(workbench_injected={"id": d["id"], "ticket": key, "sha": sha, "at": time.time()})


def reset(reseed: bool | None = None) -> list[str]:
    """Back to the clean pre-demo state. Target: under two minutes."""
    from concurrent.futures import ThreadPoolExecutor

    st = state.load()
    if not st.get("baseline_sha"):
        raise SystemExit("no baseline recorded; run `labctl baseline set` while production is clean")
    steps: list[str] = []
    injected = st.get("injected") or {}
    t0 = time.time()

    def step(msg):
        steps.append(f"{time.time() - t0:5.1f}s {msg}")

    # 1. GitHub: close agent PRs, delete fix branches, cancel pending deploys, force main back to baseline
    gh_close_agent_prs()
    step("closed open agent PRs and deleted fix/* branches")
    ensure_clone()
    _git("push", "--quiet", "--force", "origin", f"{st['baseline_sha']}:main")
    step(f"main reset to {st['baseline_sha'][:12]}")

    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = []
        # 2. production image back to baseline
        if injected.get("image") or ecs.current_image("atlas-platform") != st["baseline_image"]:
            arn = ecs.register_revision("atlas-platform", st["baseline_image"])
            futs.append(pool.submit(lambda: (ecs.rollout("atlas-platform", arn, desired=1, wait=True), "atlas-platform rolled back to baseline image")))
        # 3. queues
        futs.append(pool.submit(lambda: (purge_queues(), "purged all lab queues")))
        # 4. board and mission control
        futs.append(pool.submit(lambda: (_reset_app("atlas-board"), "atlas-board reseeded")))
        futs.append(pool.submit(lambda: (_reset_app("mission-control"), "mission-control cleared")))
        # 5. agents restarted so in-memory state is gone
        futs.append(pool.submit(lambda: (restart_agents(), "agents restarted")))
        # 6. data
        if reseed or (reseed is None and injected.get("data")):
            from . import db

            futs.append(pool.submit(lambda: (db.run_module("platform", "reset"), "platform data reseeded")))
        for f in futs:
            try:
                _, msg = f.result()
                step(msg)
            except Exception as e:  # noqa: BLE001
                step(f"FAILED: {type(e).__name__}: {str(e)[:120]}")
    state.save(injected=None, workbench_injected=None)
    bus.emit("lab.reset", "Lab reset to clean state", seconds=round(time.time() - t0, 1))
    step("done")
    return steps


# --- helpers ------------------------------------------------------------------


def _basic_auth() -> tuple[str, str]:
    v = json.loads(client("secretsmanager").get_secret_value(SecretId=outputs().secrets["basic-auth"])["SecretString"])
    return v["username"], v["password"]


def _run_sql(sql: str) -> None:
    import psycopg

    from . import db

    e = db.env_for("platform")
    with psycopg.connect(host=e["DB_HOST"], port=5432, user=e["DB_USER"], password=e["DB_PASSWORD"], dbname=e["DB_NAME"], autocommit=True) as c:
        c.execute(sql)


def _reset_app(name: str) -> None:
    url = outputs().urls[name]
    httpx.post(f"{url}/api/admin/reset", auth=_basic_auth(), timeout=120).raise_for_status()


def purge_queues() -> None:
    sqs = client("sqs")
    for url in outputs().queues.values():
        try:
            sqs.purge_queue(QueueUrl=url)
        except sqs.exceptions.PurgeQueueInProgress:
            pass


def restart_agents(wait: bool = False) -> None:
    e = client("ecs")
    for svc in ("scout", "forge", "sentinel", "conductor", "watchtower"):
        try:
            e.update_service(cluster=outputs().cluster, service=svc, forceNewDeployment=True)
        except Exception:  # noqa: BLE001
            pass


def gh_close_agent_prs() -> None:
    """Close open PRs from fix/* branches, delete those branches, cancel queued deploy runs."""
    import os

    env = {**os.environ}
    repo = f"{GITHUB_ORG}/atlas-platform"
    prs = json.loads(subprocess.run(["gh", "pr", "list", "--repo", repo, "--state", "open", "--json", "number,headRefName"], capture_output=True, text=True, env=env).stdout or "[]")
    for pr in prs:
        subprocess.run(["gh", "pr", "close", str(pr["number"]), "--repo", repo, "--delete-branch", "--comment", "Closed by labctl reset"], capture_output=True, env=env)
    branches = subprocess.run(["gh", "api", f"repos/{repo}/branches", "--jq", ".[].name"], capture_output=True, text=True, env=env).stdout.split()
    for b in branches:
        if b.startswith("fix/") or b.startswith("workbench/"):
            subprocess.run(["gh", "api", "-X", "DELETE", f"repos/{repo}/git/refs/heads/{b}"], capture_output=True, env=env)
    runs = json.loads(subprocess.run(["gh", "run", "list", "--repo", repo, "--workflow", "deploy.yml", "--status", "waiting", "--json", "databaseId", "--limit", "20"], capture_output=True, text=True, env=env).stdout or "[]")
    for r in runs:
        subprocess.run(["gh", "run", "cancel", str(r["databaseId"]), "--repo", repo], capture_output=True, env=env)


def remove_clone() -> None:
    shutil.rmtree(CLONE, ignore_errors=True)
