# RUNBOOK — ATLAS Agentic SDLC Demo Lab

Written to be followed under pressure. Every command runs from `atlas-agentic-lab/labctl` as
`uv run labctl …` (or install once with `uv tool install -e .` and call `labctl`). AWS profile
`chu-ai`; run `aws sso login` first if `labctl status` fails with an expired token.

## 0. One-time setup (already done, here for rebuilds)

1. `tools/github_app_manifest.py` → create the GitHub App; install it on `chu-labs`; `tools/github_app_token.py --check`.
2. `cd infra/terraform && terraform init && terraform plan -out=p && terraform apply p` (about 8 minutes, RDS is the long pole). Set `admin_cidr` in `terraform.tfvars` to your laptop's `/32`.
3. `labctl secrets push --anthropic --github-app --basic-auth maroun maroun --github-human` (PAT and login from env or prompt).
4. `gh variable set AWS_DEPLOY_ROLE_ARN --repo chu-labs/atlas-platform --body "$(terraform output -raw gha_deploy_role_arn)"`.
5. `labctl deploy atlas-platform && labctl db seed platform -- --buildings 2500`.
6. `labctl deploy atlas-board && labctl db seed board`; `labctl deploy mission-control`.
7. `labctl deploy agent --desired 1 && labctl deploy forge --desired 1` (Watchtower can stay at 0 unless you want the incident beat).
8. `labctl baseline set` while production is clean. `labctl traffic start`.
9. `labctl status` — every service running, every URL 200, every secret populated.

## 1. The morning of the lecture

```
aws sso login
labctl status                     # all green
labctl traffic status             # running, 5xx = 0
labctl reset                      # clean board, clean main, clean queues, agents restarted (< 2 min)
labctl record list                # clean-run and workbench-run present
labctl workbench --ticket ATLAS-XX --no-attach   # tmux session ready in another window
```
Open three browser tabs on the projector machine: Mission Control (`labctl outputs` shows the URLs,
basic auth maroun/maroun), the board (`:8081`), GitHub `chu-labs/atlas-platform` pull requests.
Terminal font at least 20 pt. Dark theme.

## 2. Rehearse (repeat as often as you like)

```
labctl record mark
labctl inject off-by-one          # pushes the defect commit, builds, deploys (~70 s), traffic keeps running
# watch Mission Control: error → triage → ticket → code → test → pr → HUMAN GATE
# click Approve on the dashboard (or approve + merge on GitHub and approve the production deployment)
# wait for verify → closed
labctl record save clean-run      # keeps the recording for the fallback
labctl reset                      # back to clean in < 2 minutes
```
Other defects: `labctl inject --list`. `ambiguous-high-rise` files a ticket instead of deploying code;
Forge should escalate, not fix. `zero-lots` also flips three buildings to zero lots (reset reseeds).

## 3. On the day: the eight-minute run

See `RUN_OF_SHOW.md`. In short: `labctl inject off-by-one`, talk, approve at the gate, let Conductor
close it.

## 4. Failure modes and what to do

| Symptom | Do this |
|---|---|
| Dashboard shows nothing after inject for 3 min | `labctl status`: is `scout` running? Is `prod-errors` depth rising? If errors rise but no ticket: Scout's LLM call may be failing; `aws logs tail /atlas-agentic-lab/scout --since 5m --profile chu-ai`. Switch to replay if under time pressure. |
| Forge stuck at *cloning* / *working* > 6 min | `aws logs tail /atlas-agentic-lab/forge --since 10m`. Common: GitHub App token, or the RDS test database. Forge gives up and escalates to you after its budget; the ticket goes to Triage assigned to you. Replay. |
| Sentinel never comments | CI may still be running on the PR head (Sentinel waits up to 4 min). Check the PR checks tab. |
| Approve button errors | The human PAT is missing or expired (`labctl secrets status`). Approve on GitHub instead: approve the review, merge, then Actions → the run → **Review deployments** → approve. Conductor reacts to `deploy.completed` either way. |
| Deploy workflow fails at "configure-aws-credentials" | The OIDC trust policy did not match GitHub's `sub` claim (it now carries numeric ids: `repo:chu-labs@123/atlas-platform@456:ref:...`). `infra/terraform/iam.tf` accepts both forms; `terraform apply` and re-run. |
| Deploy workflow fails | Open the run. If build failed, `labctl deploy atlas-platform` from the merged main and Conductor will not fire; close the ticket by hand on the board. |
| Wifi / API down on stage | `labctl record play clean-run --speed 1` — replays into the live dashboard. Tell the audience afterwards. |
| Workbench pane dies silently | `labctl workbench --reset --ticket ATLAS-XX` rebuilds in < 30 s. Teammate branches survive; worktrees are recreated on spawn. |
| A teammate hangs | In the main pane, call `close_teammates` (or `tmux kill-pane`) and respawn that role. Each teammate has a 60-turn, USD 3 budget cap. |
| Worktree conflict on converge | `converge_branches` stops at the conflict and names the files; resolve in the atlas-platform checkout, `git add`, `git commit`, run tests, push, open the PR. This is the interesting part; do it on screen. |
| Everything is wrong | `labctl reset`; if still wrong, `labctl scale all 0 && labctl scale all 1`; last resort `terraform apply` again (state is local, idempotent). |

## 5. Tear down (after the lecture, before 2026-09-30)

```
labctl traffic stop
labctl teardown           # confirms, terraform destroy, then lists anything tagged that is left (should be none)
labctl cost               # month-to-date AWS cost for the Project tag
```
Then on GitHub: delete the `chu-labs` repos or the org, and uninstall/delete the `chu-atlas-agents` App.
Rotate the Anthropic key and revoke the fine-grained PAT. Delete `~/.config/atlas-lab/`.

## 6. Where things are

| Thing | Where |
|---|---|
| Terraform state | `infra/terraform/terraform.tfstate` (local, gitignored) |
| Secrets | AWS Secrets Manager `atlas-agentic-lab/*`; RDS master password managed by RDS |
| GitHub App credentials | `~/.config/atlas-lab/github-app.json` (mode 600) |
| Baseline and injected state | `~/.config/atlas-lab/state.json` |
| Recordings | `recordings/*.json` in this repo and in Mission Control's database |
| Logs | CloudWatch `/atlas-agentic-lab/<service>`, 3-day retention |
| Defects | `demo/defects/<id>/defect.yaml` + `patch.diff` |
| Event contract | `docs/EVENTS.md` |
