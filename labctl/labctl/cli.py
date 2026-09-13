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
