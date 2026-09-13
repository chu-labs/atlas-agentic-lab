"""Entry point: AGENT_NAME selects the agent."""
from __future__ import annotations

import importlib

from .config import config
from .logging_setup import configure


def main() -> None:
    configure()
    name = config().agent_name
    mod = importlib.import_module(f"atlas_agents.{name}")
    mod.Agent().start()


if __name__ == "__main__":
    main()
