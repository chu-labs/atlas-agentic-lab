# Lab event contract

One EventBridge bus, `atlas-agentic-lab`. Every component emits to it; Mission Control persists and
displays everything; agents receive only what their rule routes to their SQS queue (see
`infra/terraform/events.tf`). When `EVENT_BUS` is empty a component logs the event instead.

## Envelope

EventBridge fields: `Source = "atlas.<component>"`, `DetailType = "<domain>.<verb>"`, `Detail` = JSON below.

Every `Detail` carries:

```json
{
  "ts": "2026-09-17T10:15:03.412Z",
  "actor": {"handle": "forge", "kind": "agent" | "human", "display_name": "Forge", "mode": "autonomous" | "supervised"},
  "ticket": "ATLAS-142",            // when known
  "summary": "Opened PR #17 with a failing-test-first fix",   // one line, plain English, shown on the timeline
  "authority": {"can_merge": false, "...": "..."},               // agents only: their agent.yaml authority block
  "telemetry": {"tokens_in": 0, "tokens_out": 0, "model_calls": 0, "seconds": 0.0, "usd": 0.0}   // optional, cumulative for the ticket
}
```

plus type-specific fields.

## Sources and detail types

| Source | DetailType | Extra fields | Routed to |
|---|---|---|---|
| atlas.platform | error.raised | request_id, endpoint, method, status_code, kind, error_type, message, stack, signature, customer_impact | scout, mission |
| atlas.board | issue.created / issue.transitioned / issue.commented / issue.assigned / issue.updated | issue {key,type,title,status,priority,assignee,labels,pr_url}, from, to, body | forge (issue.assigned to forge), mission |
| atlas.scout | incident.opened / incident.threshold_crossed / incident.resolved / agent.status | incident {signature,count,first_seen,customer_impact}, status | watchtower, mission |
| atlas.forge | agent.status / agent.thinking / pr.opened / pr.updated / escalation.raised | pr {number,url,branch,title}, status, thinking | sentinel (pr.*), mission |
| atlas.sentinel | agent.status / review.posted / review.changes_requested | pr, verdict, body | forge (changes_requested), mission |
| atlas.mission-control | human.approved / human.rejected / human.gate_waiting | pr, waited_seconds | conductor (approved), mission |
| atlas.github | deploy.completed / pr.merged | repo, service, sha, image, run_id, actor | conductor, mission |
| atlas.conductor | agent.status / verify.passed / verify.failed / ticket.closed | pr, smoke {ok, checks}, signature_seen_after_deploy | mission |
| atlas.workbench | workbench.dispatch / teammate.spawned / teammate.finished / converge.started / converge.done | role, worktree, branch, pane | forge (dispatch), mission |

`agent.status` carries `status: idle | working | waiting_on_human | blocked | escalated` and `thinking`,
the live one-liner shown on the fleet card.

## Pipeline stages (Mission Control)

`error → triage → ticket → code → test → pr → human_gate → merge → deploy → verify → closed`.
Mission Control derives the active stage per ticket from the events above; components do not
send stage names.
