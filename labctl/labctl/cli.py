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
def secrets_push(anthropic, github_app, basic_auth):
    from . import secrets as s

    if anthropic:
        key = os.environ.get("ANTHROPIC_API_KEY") or click.prompt("Anthropic API key", hide_input=True)
        console.print(f"[green]anthropic-api-key[/] -> {s.push_anthropic(key)}")
    if github_app:
        console.print(f"[green]github-app[/] -> {s.push_github_app()}")
    if basic_auth:
        console.print(f"[green]basic-auth[/] -> {s.push_basic_auth(*basic_auth)}")
    if not (anthropic or github_app or basic_auth):
        raise click.UsageError("nothing to push; pass --anthropic, --github-app and/or --basic-auth")


@secrets.command("status")
def secrets_status():
    from . import secrets as s

    t = Table("secret", "populated")
    for k, v in s.status().items():
        t.add_row(k, "[green]yes" if v else "[red]placeholder")
    console.print(t)


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
