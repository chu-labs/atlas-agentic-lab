# atlas-agentic-lab

Infrastructure, agents, dashboard, seeder, CLI and docs for the ATLAS Agentic SDLC Demo Lab.

The system under test lives in the sibling repository `atlas-platform`.

Everything here is ephemeral and destroyed after the lecture. See `RUNBOOK.md` once it exists.

Layout:

- `infra/terraform` — one root module for the whole lab
- `agents/` — Scout, Forge, Sentinel, Conductor, Watchtower
- `board/` — atlas-board, the purpose-built issue tracker
- `mission-control/` — the projector dashboard
- `workbench/` — tmux layout and the atlas-team MCP server
- `labctl/` — demo control CLI
- `demo/defects/` — injectable defects for atlas-platform
- `tools/` — one-off helpers (GitHub App manifest, etc.)
- `docs/` — design record, architecture, runbook, run of show
