# Workbench

Supervised mode: you drive Claude Code in the left pane; when it delegates, real teammate panes
appear on the right, each a headless Claude Code process on its own git worktree and branch.

```
labctl workbench --ticket ATLAS-142      # builds the tmux session `atlas`, attaches
labctl workbench --reset                 # kills everything (panes, worktrees) and rebuilds in <30 s
```

Inside the main session, say for example:

> Assemble a team for ATLAS-142: an analyst to write the approach, a tester to write the tests
> without seeing the fix, a builder to implement, then a reviewer on the builder's branch. Use the
> atlas-team tools. When they finish, collect their work, converge the branches, resolve any
> conflict, run the suite and open one PR.

Tools exposed by the `atlas-team` MCP server: `spawn_teammate`, `teammate_status`,
`collect_teammates`, `converge_branches`, `close_teammates`.

Terminal font: set your terminal profile to at least 20 pt before projecting. tmux cannot change
the font; it is a terminal setting.
