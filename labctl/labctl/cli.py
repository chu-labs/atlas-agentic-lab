"""labctl entry point."""
from __future__ import annotations

import os

import click
from rich.console import Console
from rich.table import Table

console = Console()


@click.group()
def main():
    """Run the ATLAS Agentic SDLC Demo Lab."""


@main.group()
def secrets():
    """Populate and inspect lab secrets in AWS Secrets Manager."""


@secrets.command("push")
@click.option("--anthropic", is_flag=True, help="Push ANTHROPIC_API_KEY from the environment")
@click.option("--github-app", is_flag=True, help="Push the GitHub App from ~/.config/atlas-lab")
@click.option("--basic-auth", nargs=2, metavar="USER PASS", help="Push the ALB basic-auth credential")
@click.option("--github-human", is_flag=True, help="Push GITHUB_HUMAN_TOKEN (fine-grained PAT) and GITHUB_HUMAN_LOGIN from the environment")
def secrets_push(anthropic, github_app, basic_auth, github_human):
    from . import secrets as s

    if anthropic:
        key = os.environ.get("ANTHROPIC_API_KEY") or click.prompt("Anthropic API key", hide_input=True)
        console.print(f"[green]anthropic-api-key[/] -> {s.push_anthropic(key)}")
    if github_app:
        console.print(f"[green]github-app[/] -> {s.push_github_app()}")
    if basic_auth:
        console.print(f"[green]basic-auth[/] -> {s.push_basic_auth(*basic_auth)}")
    if github_human:
        tok = os.environ.get("GITHUB_HUMAN_TOKEN") or click.prompt("GitHub fine-grained PAT", hide_input=True)
        login = os.environ.get("GITHUB_HUMAN_LOGIN") or click.prompt("GitHub login")
        console.print(f"[green]github-human[/] -> {s.push_github_human(tok, login)}")
    if not (anthropic or github_app or basic_auth or github_human):
        raise click.UsageError("nothing to push; pass --anthropic, --github-app, --basic-auth and/or --github-human")


@secrets.command("status")
def secrets_status():
    from . import secrets as s

    t = Table("secret", "populated")
    for k, v in s.status().items():
        t.add_row(k, "[green]yes" if v else "[red]placeholder")
    console.print(t)


@main.command()
@click.argument("image", type=click.Choice(list(__import__("labctl.ecs", fromlist=["IMAGES"]).IMAGES)))
@click.option("--tag", default=None, help="Image tag; default is the git short SHA of the context")
@click.option("--no-wait", is_flag=True)
@click.option("--desired", type=int, default=1)
def deploy(image, tag, no_wait, desired):
    """Build an image for arm64, push it to ECR and roll it out to its services."""
    import subprocess

    from . import ecs

    spec = ecs.IMAGES[image]
    tag = tag or subprocess.run(["git", "rev-parse", "--short=12", "HEAD"], cwd=spec["context"], capture_output=True, text=True).stdout.strip() or "manual"
    console.print(f"building [bold]{image}[/] from {spec['context']} as :{tag}")
    ref = ecs.build_and_push(image, tag)
    for svc in spec["services"]:
        arn = ecs.register_revision(svc, ref)
        console.print(f"  {svc}: {arn.rsplit('/',1)[-1]} -> desired {desired}")
        ecs.rollout(svc, arn, desired=desired, wait=not no_wait)
    console.print("[green]done[/]")


@main.command()
@click.argument("service")
@click.argument("count", type=int)
@click.option("--wait", is_flag=True)
def scale(service, count, wait):
    """Set the desired count of one service (or 'agents' / 'web' / 'all')."""
    from . import ecs

    groups = {"agents": ["scout", "forge", "sentinel", "conductor", "watchtower"], "web": ["mission-control", "atlas-board", "atlas-platform"]}
    groups["all"] = groups["agents"] + groups["web"]
    for svc in groups.get(service, [service]):
        ecs.scale(svc, count, wait=wait)
        console.print(f"{svc} -> {count}")


@main.command()
def status():
    """Health of every component."""
    import httpx

    from . import ecs
    from . import secrets as s
    from .config import outputs as o

    t = Table("service", "desired", "running", "image", "rollout")
    for r in ecs.service_states():
        colour = "green" if r["running"] == r["desired"] else "yellow"
        t.add_row(r["service"], str(r["desired"]), f"[{colour}]{r['running']}[/]", r["image"], r["rollout"])
    console.print(t)
    t = Table("url", "health")
    for name, url in o().urls.items():
        try:
            code = httpx.get(f"{url}/health", timeout=5).status_code
            t.add_row(url, "[green]200" if code == 200 else f"[red]{code}")
        except Exception as e:  # noqa: BLE001
            t.add_row(url, f"[red]{type(e).__name__}")
    console.print(t)
    t = Table("queue", "messages")
    for k, v in ecs.queue_depths().items():
        t.add_row(k, str(v))
    console.print(t)
    t = Table("secret", "populated")
    for k, v in s.status().items():
        t.add_row(k, "[green]yes" if v else "[red]placeholder")
    console.print(t)


@main.group()
def db():
    """Database helpers against the lab RDS instance."""


@db.command("seed")
@click.argument("app", type=click.Choice(["platform", "board", "mission"]))
@click.argument("args", nargs=-1)
def db_seed(app, args):
    """Migrate and seed one app's database (e.g. `labctl db seed platform --buildings 2500`)."""
    from . import db as d

    raise SystemExit(d.run_module(app, "seed", *args))


@db.command("reset")
@click.argument("app", type=click.Choice(["platform", "board", "mission"]))
def db_reset(app):
    """Truncate and reseed one app's database."""
    from . import db as d

    raise SystemExit(d.run_module(app, "reset"))


@db.command("psql")
@click.argument("app", type=click.Choice(["platform", "board", "mission"]))
def db_psql(app):
    """Open psql on one app's database."""
    import os

    from . import db as d

    os.execvp("psql", ["psql", *d.psql_args(app)])


@main.group()
def traffic():
    """Synthetic user traffic against production."""


@traffic.command("start")
@click.option("--rps", default=3.0, show_default=True, help="Mean requests per second")
def traffic_start(rps):
    from . import traffic as t
    from .config import outputs as o

    user, pw = _basic_auth()
    pid = t.start(o().urls["atlas-platform"], user, pw, rps)
    console.print(f"traffic running, pid {pid}, ~{rps} rps")


@traffic.command("stop")
def traffic_stop():
    from . import traffic as t

    console.print("stopped" if t.stop() else "not running")


@traffic.command("status")
def traffic_status():
    from . import traffic as t

    console.print({"running": t.running(), **t.stats()})


def _basic_auth() -> tuple[str, str]:
    import json

    from .aws import client
    from .config import outputs as o

    v = json.loads(client("secretsmanager").get_secret_value(SecretId=o().secrets["basic-auth"])["SecretString"])
    return v["username"], v["password"]


@main.command()
@click.argument("defect_id", required=False)
@click.option("--no-deploy", is_flag=True, help="Push the defective commit but do not deploy it")
@click.option("--list", "list_", is_flag=True, help="List available defects")
@click.option("--workbench", is_flag=True, help="Supervised story: defect on main only, a human files the ticket, no deploy")
def inject(defect_id, no_deploy, list_, workbench):
    """Deploy a defective build to production and start the traffic that triggers it."""
    from . import defects, traffic
    from .config import outputs as o

    if list_ or not defect_id:
        t = Table("id", "difficulty", "title", "agent should")
        for d in defects.list_defects():
            t.add_row(d["id"], d["difficulty"], d["title"], d.get("expected_agent_behaviour", "fix"))
        console.print(t)
        return
    st = defects.inject(defect_id, no_deploy=no_deploy, workbench=workbench)
    console.print(f"[yellow]injected[/] {st['workbench_injected'] if workbench else st['injected']}")
    if workbench:
        return
    if not traffic.running():
        user, pw = _basic_auth()
        traffic.start(o().urls["atlas-platform"], user, pw, 3.0)
        console.print("traffic started")


@main.command()
@click.option("--reseed", is_flag=True, help="Also reseed the platform database")
def reset(reseed):
    """Return everything to the clean pre-demo state (target: under two minutes)."""
    from . import defects

    for line in defects.reset(reseed=reseed or None):
        console.print(line)


@main.group()
def baseline():
    """The clean state that `reset` returns to."""


@baseline.command("set")
@click.option("--image", default=None, help="Clean image reference to record instead of the running one")
@click.option("--force", is_flag=True)
def baseline_set(image, force):
    """Record current origin/main and the production image as the clean baseline."""
    from . import defects

    st = defects.baseline_set(image=image, force=force)
    console.print({k: st[k] for k in ("baseline_sha", "baseline_image")})


@baseline.command("show")
def baseline_show():
    from . import state

    console.print(state.load())


@main.command()
@click.option("--ticket", default=None, help="Ticket key shown in the status bar")
@click.option("--reset", "do_reset", is_flag=True, help="Kill panes and worktrees and rebuild")
@click.option("--no-attach", is_flag=True)
def workbench(ticket, do_reset, no_attach):
    """Build the projector-ready tmux layout (session 'atlas') with Claude Code in the main pane."""
    import os

    from . import workbench as wb
    from .config import outputs as o

    if do_reset:
        wb.reset()
        console.print("workbench reset")
    extra = {}
    try:
        extra = {"EVENT_BUS": o().event_bus, "AWS_REGION": "ap-southeast-2", "AWS_PROFILE": os.environ.get("ATLAS_AWS_PROFILE", "chu-ai")}
    except SystemExit:
        pass
    wb.build(ticket, attach=not no_attach, env_extra=extra)
    if no_attach:
        console.print("session 'atlas' ready: tmux attach -t atlas")


@main.group()
def record():
    """Capture a full run from Mission Control and replay it as the fallback."""


@record.command("mark")
def record_mark():
    """Mark the start of a run (call before `labctl inject`)."""
    from . import record as r

    console.print(f"recording from event {r.mark()}")


@record.command("save")
@click.argument("name")
def record_save(name):
    """Save everything since the mark as a named recording (also written to recordings/<name>.json)."""
    from . import record as r

    console.print(r.save(name))


@record.command("play")
@click.argument("name")
@click.option("--speed", default=1.0, show_default=True, help="1.0 = original timing; 4.0 = four times faster")
def record_play(name, speed):
    """Replay a recording into the live dashboard."""
    from . import record as r

    console.print(r.replay(name, speed))


@record.command("video")
@click.argument("name")
@click.option("--speed", default=2.0, show_default=True, help="Replay speed while filming")
@click.option("--out", default=None, help="Output .mp4 path (default recordings/<name>.mp4)")
def record_video(name, speed, out):
    """Render a saved recording to a standalone MP4 (local dashboard + headless browser)."""
    from pathlib import Path

    from . import record as r

    path = r.video(name, Path(out) if out else None, speed=speed)
    console.print(f"[green]wrote[/] {path}")


@record.command("list")
def record_list():
    from . import record as r

    for rec in r.list_recordings():
        console.print(rec)


@main.command()
@click.option("--yes", is_flag=True, help="Skip the confirmation prompt")
def teardown(yes):
    """terraform destroy everything, then check nothing tagged is left and show month-to-date cost."""
    from . import teardown as t
    from . import traffic

    traffic.stop()
    if not yes:
        click.confirm("This destroys the whole lab (VPC, database, everything). Continue?", abort=True)
    rc = t.destroy()
    if rc != 0:
        console.print(f"[red]destroy exited {rc}[/]")
        raise SystemExit(rc)
    left = t.leftovers()
    if left:
        console.print("[red]leftover resources:[/]")
        for arn in left:
            console.print(f"  {arn}")
    else:
        console.print("[green]no tagged resources left[/]")
    try:
        console.print({"month_to_date_cost": t.month_to_date_cost()})
    except Exception as e:  # noqa: BLE001
        console.print(f"cost explorer unavailable: {e}")


@main.command()
def cost():
    """Month-to-date AWS cost for the lab tag."""
    from . import teardown as t

    console.print(t.month_to_date_cost())


@main.command()
def leftovers():
    """List tagged resources that still exist (use after teardown)."""
    from . import teardown as t

    left = t.leftovers()
    console.print(left or "[green]none[/]")


@main.group()
def demo():
    """Scenario runner: kick off errors and watch the agents react, live, in this terminal."""


@demo.command("run")
@click.argument("defect_ids", nargs=-1, required=True)
@click.option("--record", "record_name", default=None, help="Save the run as a named recording when it ends")
@click.option("--workbench", is_flag=True, help="Supervised story: file a human ticket, no deploy")
def demo_run(defect_ids, record_name, workbench):
    """Inject one or more defects (see `labctl inject --list`) and stream the agents' events here."""
    from . import demo as d

    d.run(list(defect_ids), name=record_name, workbench=workbench)


@demo.command("watch")
@click.option("--since", type=int, default=None, help="Event id to start from (default: now)")
def demo_watch(since):
    """Just watch: stream Mission Control events to the terminal until a ticket closes or escalates."""
    from . import demo as d

    if since is None:
        with d._client() as c:
            since = d._last_event_id(c)
    d.watch(since)


@demo.command("storm")
@click.option("--record", "record_name", default="storm-run")
def demo_storm(record_name):
    """Three defects at once with three Forge tasks: zero-lots, float-premium, n-plus-one."""
    from . import demo as d
    from . import ecs

    ecs.scale("forge", 3)
    console.print("forge scaled to 3")
    d.run(["zero-lots", "float-premium", "n-plus-one"], name=record_name)


@main.group()
def chaos():
    """Infrastructure incidents on demand (kill a task, short outage)."""


@chaos.command("kill-task")
@click.option("--service", default="atlas-platform", show_default=True)
def chaos_kill(service):
    """Stop the running task; ECS replaces it in ~1 min while the ALB serves 503s."""
    from . import chaos as c

    console.print(c.kill_task(service))


@chaos.command("outage")
@click.option("--service", default="atlas-platform", show_default=True)
@click.option("--seconds", default=90, show_default=True)
def chaos_outage(service, seconds):
    """Scale a service to zero for a while, then back."""
    from . import chaos as c

    console.print(c.scale_down(service, seconds))


@main.command()
def outputs():
    """Show Terraform outputs the lab runs on."""
    from .config import outputs as o

    d = o()
    t = Table("key", "value")
    for k, v in d.urls.items():
        t.add_row(f"url.{k}", v)
    t.add_row("db_host", d.db_host)
    t.add_row("cluster", d.cluster)
    t.add_row("event_bus", d.event_bus)
    console.print(t)


if __name__ == "__main__":
    main()
