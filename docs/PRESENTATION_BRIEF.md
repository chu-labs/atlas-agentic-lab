# Brief for the presentation builder — "Agentic AI and human oversight" guest lecture

Audience: about 300 university students (business analytics and computing), Thursday 17 September 2026.
Presenter: Maroun. Length: a lecture with a live demo of roughly 8 minutes plus two optional beats.
This document is the single source of truth about the demo so the slides match what will be on screen.
Everything described here was built and rehearsed on 13 September 2026. Nothing is a mock-up.

## 1. The one-sentence thesis

Software engineering is becoming a system where agents do the work and humans make the decisions, and
the interesting design question is no longer "can the agent do it" but "where do we draw the line, and how
do we make that line real rather than decorative".

## 2. The story the demo tells (in the order the audience sees it)

1. A real production service, ATLAS, a small strata insurance platform (policies, buildings, renewals,
   risk scores, premium quotes), is live with synthetic customer traffic. Nobody is at a keyboard.
2. The presenter ships a one-line bug into production (a renewal window that drops policies due exactly
   30 days out). Nobody is told.
3. **Scout** (triage agent) reads the production error stream, recognises a cluster, and writes a bug
   ticket: reproduction steps, stack trace, affected endpoint, customer impact, priority. It assigns it to Forge.
   Measured: about 50 seconds from the first error.
4. **Forge** (engineering agent, Claude Code running headless in a container) clones the repo, reads
   `CLAUDE.md` (its onboarding document, the same one a new engineer gets), reproduces the bug with a
   **failing test first**, fixes it, runs the suite, then verifies its own claim by re-running the test commit
   alone to prove the test fails without the fix, and opens a pull request explaining root cause, fix, test and
   what it deliberately did not change. Measured: about 2 minutes 15 seconds from ticket to PR.
5. **Sentinel** (review agent) reviews the PR independently: scope, forbidden files, business-rule constants,
   test-first history, CI, then a model review of the diff. It can comment or send it back. It cannot approve;
   its GitHub client refuses the approve call outright. Measured: about 1 minute 20 seconds.
6. **The human gate.** The pipeline stops. The dashboard shows an amber box, a live counter of how long it
   has been waiting, and two buttons. GitHub branch protection requires a human approval, and the agents'
   identity cannot approve its own work. The presenter hands the decision to the audience, then clicks
   Approve. One click does three things as the presenter: approves the review, merges, and approves the
   production deployment. All three are recorded against the presenter's name.
7. GitHub Actions tests, builds and deploys. **Conductor** (release agent) waits for the deploy, smoke-checks
   production, confirms the original error signature has stopped, and closes the ticket. Measured: about 4
   minutes from click to closed, most of it the deploy.
8. The timeline shows every action, who or what did it, and what authority it had. One human row among
   dozens of agent rows. That is the governance artefact.

Machine time end to end: about 7 to 8 minutes. The human gate is the only pause and lasts as long as the
presenter talks.

## 3. The two optional beats

**The agent that says no (about 1 minute).** A human files "premiums for buildings over 20 floors look too
high". Forge reads the rating code, finds a deliberate 15% high-rise loading documented as an underwriting
decision, checks git history to confirm it is not a regression, notices the complainant's own numbers match the
loading exactly, refuses to change code, writes three questions an underwriter would have to answer, and
reassigns the ticket to the product owner. Measured: 40 seconds. Message: the most important thing an
autonomous system can do is recognise a decision that is not its to make.

**The Workbench, supervised mode (about 6 minutes).** Same system, different place for the human. The
presenter drives Claude Code in a terminal. Four real agent panes appear on screen, each a separate Claude
Code process on its own git worktree and branch: analyst (writes the approach), tester (writes tests without
seeing the fix), builder (implements without writing tests), then a reviewer on the builder's branch. In
rehearsal the reviewer requested changes for a missing large-lot test; the tester had written exactly that
test on its own branch; merging the branches broke the test suite because the tester imported a constant the
builder had deleted; the presenter's session reconciled it and opened one PR, which landed at the same human
gate. Message: two agents solved the same problem from different ends and their work did not fit; the
interesting part is who reconciles them.

## 4. The cast: agents and their authority (this is data, enforced in code)

| Agent | Role | Can | Cannot | Must escalate on |
|---|---|---|---|---|
| Scout 🔭 | Triage | read production telemetry, create tickets | write code, merge, deploy | security impact, impact over 500 customers |
| Forge ⚒️ | Engineering | write code, open PRs | merge, deploy, change business rules, change schema | ambiguous requirement, business-rule change, security, data migration, cost |
| Sentinel 🛡️ | Review | review, request changes | approve, merge, write code | security impact |
| Conductor 🎼 | Release | verify deploys, close and reopen tickets | merge, write code | verification failed, rollback needed |
| Watchtower 🗼 | Incidents | open incidents, page humans | write code | severity 1 |
| Human (Maroun) | Product owner | approve, merge, deploy, change business rules | | |

Every fleet card on the dashboard shows these as badges; "merge" is struck through on every agent.

## 5. Then versus now (numbers supplied by the presenter for a small production bug)

| Stage | Traditional team | Agentic, measured |
|---|---|---|
| Detect | ~1 day (a customer notices and reports) | seconds (telemetry) |
| Triage and ticket | ~0.5 day (support validates: 10 minutes to hours) | ~50 s |
| Backlog wait | ~7 days (fortnightly sprint) | none |
| Code | ~1 day | ~2 min |
| Test | ~1 day | included (test first) |
| Review | ~1 day | ~1 min 20 s |
| Change approval and deploy | ~2 days | ~3 to 4 min (one human click) |
| Verify and close | ~0.5 day | ~50 s |
| **Total** | **~14 days** | **~8 minutes of machine time** |

Model cost per ticket: roughly USD 0.45 to 0.65. A loaded engineering rate of AUD 185 per hour is used for
comparison. Caveat for the slide: small fix; an XL fix runs to a quarter; review and testing wait the same way.

## 6. Where the line is drawn, and how it is made real (the governance slide)

Three mechanisms make the human gate genuine rather than decorative:
1. GitHub branch protection requires one approving review, and the agents act as a GitHub App whose own
   approval would not count anyway. Sentinel's code refuses to approve.
2. The production environment has a required reviewer, so even a merged change does not deploy until a human
   approves the deployment.
3. Only the dashboard's Approve button, acting with the human's own credential, can emit the "human approved"
   event; nothing else in the system can.

Plus: authority is declared as data per agent and checked before every side effect; a refused action is
recorded on the ticket and the dashboard, not silently skipped. Every agent writes its reasoning in plain
English on the ticket, which the audience reads live.

## 7. What is on screen (assets available to the presentation)

Screenshots are in `docs/assets/` of the `chu-labs/atlas-agentic-lab` repository: `mc-v4-ops.png` (Operations), `mc-v4-eng.png` (Engineering with the gate), `mc-v3-board.png` (Board), `mc-v3-cicd.png`, `mc-v3-dora.png`, `mc-v2-drawer-pr.png` (stage drawer), `mc-v2-compare.png` (then vs now overlay), `mc-v2-agent.png` (an agent's reasoning). Videos are in `recordings/` (not in git: `clean-run.mp4`, `workbench-run.mp4`; ask Maroun).

Screenshots (1920x1080, dark theme) exist for: the human gate waiting, the stage drawer showing a PR's
artefacts and who acted with what authority, the Compare overlay (then vs now), the Operations view (production
signal by kind, live error clusters, service health), the Engineering view (pipeline, dev agents, assigned
work), the Board tab (agents as first-class assignees), CI/CD, and DORA. Two MP4 fallback videos exist: the
clean autonomous run and the Workbench run, replayed into the dashboard at 4x.

Dashboard layout for reference: a pipeline row per ticket with eleven stages (Error, Triage, Ticket, Code,
Test, PR, **Human gate**, Merge, Deploy, Verify, Closed); the human gate is amber, larger, with a person icon.
Fleet cards with robot avatars and authority badges. A timeline where human rows are visibly different. A
then-vs-now panel with a big ratio ("~14 days → 7:39").

## 8. Facts about the build the slides can use safely

- Everything runs in a dedicated, disposable AWS environment; one command destroys it. Total AWS cost for
  the lab's life is under AUD 100.
- The service under test is a fresh, small FastAPI and Postgres application with 40 tests, 2,500 buildings,
  5,500 policies and 19,600 claims, all synthetic. No real customer data anywhere.
- Agents use Claude Sonnet 5 via the Anthropic API; Forge is Claude Code run headless in a container.
- Six injectable defects exist, varying in difficulty: an off-by-one, a timezone mistake, a divide-by-zero on
  bad data, float money drift, an N+1 performance regression, and one that is not a defect at all.
- The "not a defect" ticket exists precisely to show the agent refusing.
- The lab was built in one day on 13 September 2026, largely by agents supervised by a human, which is itself
  a talking point if the presenter wants it.

## 9. Suggested slide spine (for the builder; adjust freely)

1. Title. 2. The old loop: customer notices, support validates, backlog, sprint, code, test, review, CAB, deploy
(~14 days). 3. The new loop: the eleven stages with the human gate highlighted. 4. Meet the fleet (table in §4).
5. **Live demo** (8 min). 6. What just happened: the timeline with one human row. 7. Then vs now (table in §5).
8. The agent that says no (live or the escalation text). 9. The Workbench: same system, human in a different
seat (live or video). 10. How the line is made real (§6). 11. What this means for a business analyst: the
decision, not the typing, is the job; governance artefacts; cost per change; DORA metrics. 12. Risks and
honest limits: agents can be wrong with confidence, escalation quality matters, review still matters, the
gate must be real. 13. Close.

## 10. Do not put on slides

Account numbers, tokens, URLs with credentials, the employer's name in connection with the data, or any
claim that the data is real. The strata plan numbers are fictional ("SP 9xxxxx") on purpose.
