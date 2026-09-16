# Run of show — the eight-minute demo

Projector: Mission Control full screen (`http://<alb>/`), the board on a second tab (`:8081`), the
Workbench tmux session on a third window. Laptop terminal: `labctl` ready, `labctl status` green.

Before you walk on: `aws sso login` done, `labctl status` green, fallback recording `clean-run` listed by
`labctl record list`. The whole demo is one command, `labctl show`; it resets, starts traffic, records, files
the "says no" ticket, ships the bug and narrates. You only approve.

| Clock | What happens | What you say |
|---|---|---|
| 0:00 | Dashboard up: fleet idle, queues at zero, pipeline dark. | "This is a real strata insurance service in production, with real synthetic traffic. Nobody on the team is at a keyboard. Watch the top row." |
| 0:15 | `labctl show` (the terminal narrates the same events as the dashboard). In the first minute Forge picks up the "premiums over 20 floors" ticket and refuses it; use that while the bug builds. | "I have just shipped a bug. One line. Renewals due exactly thirty days out fall out of the renewal run. Nobody knows yet." |
| 1:30 | Production errors counter climbs. Scout's card goes *working*; its thinking line reads. | "Scout watches the error queue. It is deciding whether this is noise or a problem. It can open tickets without asking anyone, because a ticket is cheap and reversible." |
| 2:00 | Ticket appears on the board (switch tab for 10 s). Read the reproduction. | "That ticket was written by a machine. Reproduction, stack trace, customer impact. Assigned to Forge." |
| 2:15 | Forge: *Cloning… reading CLAUDE.md*. Pipeline at **code**. | "Forge has an onboarding document, the same one a new engineer gets. Read the rules on screen: failing test first, never change business rules, never touch migrations." |
| 3:00 | Forge thinking: *wrote a failing test… confirmed it fails… fixing…*. Pipeline **test**. | "Test first. Then the fix. Then the whole suite. And then it checks its own claim: it reruns the test commit alone to prove the test really fails without the fix." |
| 4:15 | **PR opened**. Pipeline **pr**. Sentinel goes *working*. | "A second agent, which did not write the code, now reviews it. It cannot approve. Its only powers are to comment or to send it back." |
| 5:00 | Sentinel comments. Pipeline lands on the **HUMAN GATE**, amber, counter ticking. | *Stop talking for five seconds. Let them look.* "Everything so far was autonomous. This is the line. Nothing can pass here without a person. Not because we were nervous, but because this is where accountability lives." |
| 5:20 | **Hand the decision to the audience.** Ask: approve or reject? Read Forge's PR description aloud. | "You are the reviewer. What do you need to know before you say yes?" Take two answers. |
| 5:50 | Click **Approve** on the dashboard. | "That click did three things: approved the review, merged, and approved the production deployment. All three are recorded against my name." |
| 6:30 | Actions deploys. Pipeline **deploy**. Conductor *working*. | "Conductor waits for the deploy, hits production, and checks whether the original error signature has stopped." |
| 7:15 | **verify passed**, ticket **Done**, telemetry: error → PR time, cost. | "About four and a half minutes from the first error to a reviewed pull request, and under a dollar of model time. The rest of the clock was us. The same fix by a human team, measured on real boards, is days." |
| 7:45 | Pause on the timeline: agent rows vs the one human row. | "Read the timeline. Every decision, who or what made it, and what authority it had. That is the governance artefact. That is the lecture." |

## Second beat, if time: the agent that says no (2 min)

`labctl inject ambiguous-high-rise`. A human files "premiums over 20 floors look too high". Forge
picks it up, reads the code, finds a deliberate 15% loading, checks git history to confirm it is not a
regression, notices the broker's own numbers match the loading, and **refuses to change it**. It writes
three questions an underwriter would have to answer and reassigns to the product owner. Measured: 40
seconds from pickup to escalation. Read its escalation comment aloud; it is the best-written thing in
the demo. Say: "The most important thing an
autonomous system can do is recognise a decision that is not its to make."

## Third beat, if time: the Workbench (6 min)

Before the talk: `labctl inject float-premium --workbench` (puts the defect on main with no deploy and
files a human ticket, assigned to you, so the fleet leaves it alone), then `labctl workbench --ticket ATLAS-<n>`.
Switch to the tmux window.

What happened in rehearsal on 13 Sep, and what to say while it happens again:

| Clock | What happens | What you say |
|---|---|---|
| 0:00 | In the main pane: *"Assemble a team for ATLAS-<n>: an analyst, a tester and a builder in parallel, then a reviewer on the builder's branch. Converge, run the suite, open one PR."* | "This is the other mode. I am at the keyboard. Watch the right-hand side." |
| 0:10 | Three panes appear, three branches, three worktrees. | "Three separate processes, three separate copies of the repo. The tester cannot see the builder's code. That is deliberate: tests written against the spec, not against the implementation." |
| 1:30 | All three finish (rehearsal: 53–87 s, about $1 total). Reviewer pane appears on the builder's branch. | "Now a fourth agent reviews the builder's work, and only the builder's work." |
| 3:20 | Reviewer verdict: **request changes**, "no test covers more than 13 lots". | "It is right. The builder wrote no tests. But look at the tester's pane." |
| 3:30 | Main session converges the four branches. **The suite breaks at collection**: the tester's tests import a constant the builder deleted. | *This is the moment.* "Two agents solved the same problem from different ends and their work does not fit together. That is normal engineering. The interesting part is not that they disagree, it is who reconciles them." |
| 4:30 | Main session fixes the import, 48 tests green, opens PR #<n> as the agents' identity. | "The reviewer asked for exactly the tests the tester had already written. Reconciled, green, one PR." |
| 5:00 | Sentinel reviews it; Mission Control shows it at **the same human gate** as the autonomous run. | "Same gate. Same button. The only thing that moved is where the human sat." |

## If anything fails on stage

`labctl record play clean-run --speed 1` replays a captured run into the same dashboard. Keep talking;
the audience cannot tell until you tell them. Then tell them, because that is also part of the lesson.
