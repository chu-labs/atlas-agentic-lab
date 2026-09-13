import { useEffect, useMemo, useState } from "react";
import { authorityAt, belongsTo, errorSignature, isHeartbeat, segmentOf, stageEntries, stageOf, str, telemetryBetween } from "./attribution";
import { Avatar } from "./Avatar";
import { Markdown } from "./md";
import { useFetch } from "./useFetch";
import { STAGES, STAGE_LABEL, SEGMENT_LABEL, type FleetCard, type MissionEvent, type MissionState, type PipelineRow, type Selection, type Stage } from "./types";
import { fmtInt, fmtUSD, hms, mmss } from "./time";

const CHIPS: [string, string][] = [
  ["can_write_code", "code"],
  ["can_review", "review"],
  ["can_merge", "merge"],
  ["can_deploy", "deploy"],
  ["can_change_business_rules", "rules"],
];

const AGENT_COLORS: Record<string, string> = { scout: "#f59e0b", forge: "#3b82f6", sentinel: "#a855f7", conductor: "#10b981", watchtower: "#ef4444" };

export function Drawer({
  selection,
  state,
  events,
  now,
  onClose,
  onSelect,
}: {
  selection: Selection | null;
  state: MissionState;
  events: MissionEvent[];
  now: number;
  onClose: () => void;
  onSelect: (s: Selection) => void;
}) {
  const [shown, setShown] = useState(false);
  useEffect(() => {
    if (selection) {
      const id = requestAnimationFrame(() => setShown(true));
      return () => cancelAnimationFrame(id);
    }
    setShown(false);
  }, [selection]);
  useEffect(() => {
    if (!selection) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selection, onClose]);

  if (!selection) return null;
  return (
    <>
      <div className={`drawer-backdrop ${shown ? "on" : ""}`} onClick={onClose} />
      <aside className={`drawer ${shown ? "on" : ""}`} role="dialog" aria-modal="true">
        {selection.kind === "stage" ? (
          <StageDrawer selection={selection} state={state} events={events} now={now} onClose={onClose} onSelect={onSelect} />
        ) : selection.kind === "agent" ? (
          <AgentDrawer handle={selection.handle} state={state} events={events} now={now} onClose={onClose} />
        ) : (
          <IssueDrawer issueKey={selection.key} state={state} onClose={onClose} onSelect={onSelect} />
        )}
      </aside>
    </>
  );
}

// ----------------------------------------------------------------------------- stage

function StageDrawer({
  selection,
  state,
  events,
  now,
  onClose,
  onSelect,
}: {
  selection: { kind: "stage"; ticket: string; stage: Stage };
  state: MissionState;
  events: MissionEvent[];
  now: number;
  onClose: () => void;
  onSelect: (s: Selection) => void;
}) {
  const row = state.pipeline.find((r) => r.ticket === selection.ticket) ?? null;
  const ticketEvents = useMemo(() => (row ? events.filter((e) => belongsTo(e, row) && !isHeartbeat(e)).slice().reverse() : []), [events, row]);
  if (!row) {
    return (
      <>
        <DrawerHead title={selection.ticket} sub="ticket not in the current window" onClose={onClose} />
        <p className="muted">No state for this ticket.</p>
      </>
    );
  }
  const stage = selection.stage;
  const inStage = ticketEvents.filter((e) => stageOf(e, row) === stage);
  const entries = stageEntries(row);
  const idx = entries.findIndex((e) => e.s === stage);
  const startMs = idx >= 0 ? entries[idx].t : NaN;
  const endMs = idx >= 0 && idx + 1 < entries.length ? entries[idx + 1].t : row.closed_ts ? Date.parse(row.closed_ts) : now;
  const stageSecs = Number.isFinite(startMs) ? Math.max(0, (endMs - startMs) / 1000) : null;
  const spend = Number.isFinite(startMs) ? telemetryBetween(ticketEvents, startMs, endMs) : null;
  const seg = segmentOf(stage);
  const segSecs = row.durations.segments[seg];
  const actors = uniqueActors(inStage, state.fleet);
  const art = artefacts(ticketEvents, row, state);
  const isGate = stage === "human_gate";
  const entered = row.stages[stage];

  return (
    <>
      <DrawerHead
        title={`${STAGE_LABEL[stage]} · ${row.ticket}`}
        sub={row.title}
        onClose={onClose}
        tone={isGate ? "amber" : row.escalated && stage === row.stage ? "violet" : undefined}
      />
      <nav className="drawer-stages">
        {STAGES.map((s) => (
          <button
            key={s}
            className={`drawer-stage ${s === stage ? "on" : ""} ${row.stages[s] ? "has" : ""}`}
            disabled={!row.stages[s]}
            onClick={() => onSelect({ kind: "stage", ticket: row.ticket!, stage: s })}
          >
            {STAGE_LABEL[s]}
          </button>
        ))}
      </nav>

      <div className="drawer-kpis">
        <Kpi label="entered" value={entered ? hms(entered) : "not yet"} />
        <Kpi label="in this stage" value={stageSecs == null ? "—" : mmss(stageSecs)} live={idx >= 0 && idx === entries.length - 1 && !row.closed && !row.escalated} />
        <Kpi label={`${SEGMENT_LABEL[seg]} segment`} value={segSecs == null ? "—" : mmss(segSecs)} tone={seg === "gate" ? "amber" : undefined} />
        <Kpi label="model spend here" value={spend ? fmtUSD(spend.usd) : "—"} sub={spend ? `${fmtInt(spend.tokens_in + spend.tokens_out)} tokens · ${fmtInt(spend.model_calls)} calls` : ""} />
      </div>

      {isGate && <GateFacts row={row} events={ticketEvents} state={state} now={now} />}
      {row.escalated && stage === row.stage && (
        <section className="drawer-section escalated-box">
          <h3>Escalated to a human</h3>
          <p>{row.escalation?.summary}</p>
          <p className="muted">
            category <b>{row.escalation?.category?.replace(/_/g, " ")}</b>
            {row.escalation?.to ? <> · handed to <b>{row.escalation.to}</b></> : null}
          </p>
        </section>
      )}

      <section className="drawer-section">
        <h3>What happened</h3>
        {inStage.length === 0 && <p className="muted">{entered ? "Nothing recorded in this stage yet." : "This stage has not been reached."}</p>}
        <ol className="prose">
          {collapse(inStage).map((g) => (
            <li key={g.e.id}>
              <span className="prose-time">{hms(g.e.ts)}</span>
              <span className="prose-body">
                <span className="prose-who" style={{ color: colorOf(g.e) }}>
                  {nameOf(g.e)}
                </span>
                {g.n > 1 && <span className="count-tag">×{g.n}</span>}
                <span className="prose-text">{textOf(g.e)}</span>
              </span>
            </li>
          ))}
        </ol>
      </section>

      {actors.length > 0 && (
        <section className="drawer-section">
          <h3>Who acted</h3>
          <div className="actors">
            {actors.map(({ card, last, human }) => (
              <div key={card?.handle ?? last.actor?.handle ?? "x"} className="actor">
                <Avatar handle={last.actor?.handle} size={44} color={human ? "#f5b942" : card?.color} emoji={human ? "👤" : card?.avatar ?? "🤖"} />
                <div className="actor-body">
                  <div className="actor-name">
                    {human ? last.actor?.display_name : card?.display_name ?? last.actor?.display_name}
                    <span className={`mode-tag ${human ? "mode-human" : `mode-${card?.mode ?? last.actor?.mode ?? "autonomous"}`}`}>
                      {human ? "human" : card?.mode ?? last.actor?.mode ?? "autonomous"}
                    </span>
                  </div>
                  {!human && <AuthorityChips authority={authorityAt(last, card)} />}
                  {human && <div className="muted small">Full authority: the only actor who can approve, merge and release.</div>}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="drawer-section">
        <h3>Artefacts</h3>
        <dl className="artefacts">
          <dt>Ticket</dt>
          <dd>
            {art.ticketUrl ? (
              <a href={art.ticketUrl} target="_blank" rel="noreferrer">
                {row.ticket}
              </a>
            ) : (
              row.ticket
            )}{" "}
            <span className="muted">{row.title}</span>
          </dd>
          {row.error && (
            <>
              <dt>Error signature</dt>
              <dd>
                <code>{row.signature}</code> <span className="muted">· {row.error.count}× since {hms(row.error.first_seen ?? row.first_ts)}</span>
                {row.error.message && <div className="muted small">{row.error.message}</div>}
              </dd>
            </>
          )}
          {art.branch && (
            <>
              <dt>Branch</dt>
              <dd>
                <code>{art.branch}</code>
              </dd>
            </>
          )}
          {row.pr && (
            <>
              <dt>Pull request</dt>
              <dd>
                {row.pr.url ? (
                  <a href={row.pr.url} target="_blank" rel="noreferrer">
                    #{row.pr.number}
                  </a>
                ) : (
                  <>#{row.pr.number}</>
                )}{" "}
                {row.pr.title}
                {art.prBody && (
                  <details open={stage === "pr"} className="body">
                    <summary>PR body</summary>
                    <Markdown text={art.prBody} />
                  </details>
                )}
              </dd>
            </>
          )}
          {art.review && (
            <>
              <dt>Sentinel’s review</dt>
              <dd>
                <span className={`verdict ${art.review.changes ? "verdict-changes" : "verdict-ok"}`}>{art.review.changes ? "changes requested" : "no blocking concerns"}</span>
                <details open={stage === "human_gate" || stage === "pr"} className="body">
                  <summary>review body</summary>
                  <Markdown text={art.review.body} />
                </details>
              </dd>
            </>
          )}
          {art.deploy && (
            <>
              <dt>Deploy</dt>
              <dd>
                {art.deploy.url ? (
                  <a href={art.deploy.url} target="_blank" rel="noreferrer">
                    run {art.deploy.runId}
                  </a>
                ) : (
                  <>run {art.deploy.runId ?? "—"}</>
                )}{" "}
                <span className="muted">
                  {art.deploy.service} {art.deploy.sha ? <code>{art.deploy.sha.slice(0, 10)}</code> : null} · {hms(art.deploy.ts)}
                </span>
              </dd>
            </>
          )}
          {art.smoke && (
            <>
              <dt>Conductor’s smoke checks</dt>
              <dd>
                <ul className="checks">
                  {art.smoke.checks.map((c, i) => (
                    <li key={i} className={art.smoke!.ok ? "ok" : "bad"}>
                      {c}
                    </li>
                  ))}
                </ul>
                {art.smoke.signatureSeen != null && (
                  <div className="muted small">original signature after deploy: {art.smoke.signatureSeen ? "seen again" : "not seen"}</div>
                )}
              </dd>
            </>
          )}
        </dl>
      </section>
    </>
  );
}

function GateFacts({ row, events, state, now }: { row: PipelineRow; events: MissionEvent[]; state: MissionState; now: number }) {
  const approved = events.find((e) => e.detail_type === "human.approved");
  const rejected = events.filter((e) => e.detail_type === "human.rejected");
  const merged = events.find((e) => e.detail_type === "pr.merged");
  const deployed = events.find((e) => e.detail_type === "deploy.completed");
  const waiting = state.gate.waiting && state.gate.ticket === row.ticket;
  const since = row.stages.human_gate;
  const waited = approved
    ? Number(approved.detail.waited_seconds ?? (since ? (Date.parse(approved.ts) - Date.parse(since)) / 1000 : 0))
    : waiting && since
      ? (now - Date.parse(since)) / 1000
      : null;
  const login = state.human?.login;
  const who = approved?.actor?.display_name ?? (waiting ? "waiting…" : "—");
  const sha = str((approved?.detail.pr as { merge_sha?: string } | undefined)?.merge_sha || merged?.detail.sha);
  const steps = [
    { label: `POST …/pulls/${row.pr?.number ?? "n"}/reviews  { event: "APPROVE" }`, done: !!approved, note: "a review only a human account can leave" },
    { label: `PUT  …/pulls/${row.pr?.number ?? "n"}/merge  { merge_method: "squash" }`, done: !!approved || !!merged, note: sha ? `→ ${sha.slice(0, 10)}` : "" },
    { label: `POST …/actions/runs/{deploy run}/pending_deployments  { state: "approved" }`, done: !!deployed, note: deployed ? "production deployment released" : "waits for the deploy.yml run" },
  ];
  return (
    <section className="drawer-section gate-facts">
      <h3>The human gate</h3>
      <div className="gate-facts-grid">
        <Kpi label="approved by" value={who} tone="amber" />
        <Kpi label="when" value={approved ? hms(approved.ts) : waiting ? "not yet" : "—"} />
        <Kpi label="waited" value={waited == null ? "—" : mmss(waited)} live={waiting} tone="amber" />
        <Kpi label="rejections" value={String(rejected.length)} />
      </div>
      <p className="muted small">
        Agents cannot do any of this: every step below runs with {login ? `@${login}` : "the human"}'s own GitHub token, from this screen.
      </p>
      <ol className="gh-steps">
        {steps.map((s, i) => (
          <li key={i} className={s.done ? "done" : ""}>
            <span className="gh-tick">{s.done ? "✓" : i + 1}</span>
            <code>{s.label}</code>
            {s.note && <span className="muted small">{s.note}</span>}
          </li>
        ))}
      </ol>
      {rejected.map((r) => (
        <p key={r.id} className="rejected">
          {hms(r.ts)} · {r.actor?.display_name} sent it back: “{str(r.detail.reason)}”
        </p>
      ))}
    </section>
  );
}

// ----------------------------------------------------------------------------- agent

function AgentDrawer({ handle, state, events, now, onClose }: { handle: string; state: MissionState; events: MissionEvent[]; now: number; onClose: () => void }) {
  const card = state.fleet.find((c) => c.handle === handle);
  const active = state.pipeline.find((r) => r.ticket === state.active_ticket) ?? state.pipeline[0] ?? null;
  const mine = useMemo(() => {
    const own = events.filter((e) => e.actor?.handle === handle && !isHeartbeat(e));
    const forTicket = active ? own.filter((e) => belongsTo(e, active)) : own;
    return (forTicket.length ? forTicket : own).slice(0, 80);
  }, [events, handle, active]);
  const spend = active && mine.length ? telemetryBetween(mine.slice().reverse(), 0, now) : null;
  if (!card) {
    return <DrawerHead title={handle} sub="unknown agent" onClose={onClose} />;
  }
  return (
    <>
      <DrawerHead
        title={card.display_name}
        sub={card.remit}
        onClose={onClose}
        avatar={<Avatar handle={card.handle} size={96} color={card.color} emoji={card.avatar} />}
      />
      <div className="drawer-kpis">
        <Kpi label="status" value={card.status.replace(/_/g, " ")} />
        <Kpi label="mode" value={card.mode} tone={card.mode === "supervised" ? "violet" : undefined} />
        <Kpi label="ticket" value={card.ticket ?? "—"} />
        <Kpi label="spend on this ticket" value={spend ? fmtUSD(spend.usd) : "—"} sub={spend ? `${fmtInt(spend.tokens_in + spend.tokens_out)} tokens · ${fmtInt(spend.model_calls)} calls` : ""} />
      </div>
      <section className="drawer-section">
        <h3>Authority</h3>
        <AuthorityChips authority={card.authority as Record<string, unknown>} full />
        {Array.isArray(card.authority.must_escalate_when) && (
          <p className="muted small">must escalate when: {(card.authority.must_escalate_when as string[]).map((x) => x.replace(/_/g, " ")).join(", ")}</p>
        )}
      </section>
      <section className="drawer-section">
        <h3>Reasoning trail {active ? <span className="muted">· {active.ticket}</span> : null}</h3>
        {mine.length === 0 && <p className="muted">Nothing from {card.display_name} yet.</p>}
        <ol className="prose">
          {collapse(mine).map((g) => (
            <li key={g.e.id}>
              <span className="prose-time">{hms(g.e.ts)}</span>
              <span className="prose-body">
                <span className="prose-kind">{g.e.detail_type}</span>
                {g.n > 1 && <span className="count-tag">×{g.n}</span>}
                <span className="prose-text">{textOf(g.e)}</span>
              </span>
            </li>
          ))}
        </ol>
      </section>
    </>
  );
}

// ----------------------------------------------------------------------------- board issue

interface IssueFull {
  key: string;
  type: string;
  title: string;
  status: string;
  priority: string;
  description: string;
  labels: string[];
  pr_url: string | null;
  branch: string | null;
  created_at: string;
  updated_at: string;
  assignee: { handle: string; display_name: string; color: string; avatar: string; kind: string; mode: string | null } | null;
  reporter: { handle: string; display_name: string; color: string; avatar: string; kind: string } | null;
  activity: { id: number; kind: string; from_value: string | null; to_value: string | null; body: string | null; created_at: string; actor: { handle: string; display_name: string; color: string; avatar: string; kind: string } }[];
  comments: { id: number; body: string; created_at: string; author: { handle: string; display_name: string; color: string; avatar: string; kind: string } }[];
}

function IssueDrawer({ issueKey, state, onClose, onSelect }: { issueKey: string; state: MissionState; onClose: () => void; onSelect: (s: Selection) => void }) {
  const { data, error } = useFetch<IssueFull>(`/api/board/issues/${issueKey}`, 5000);
  const row = state.pipeline.find((r) => r.ticket === issueKey);
  const board = state.links?.board;
  if (!data) {
    return (
      <>
        <DrawerHead title={issueKey} sub={error ?? "loading…"} onClose={onClose} />
      </>
    );
  }
  const feed = [
    ...data.activity.map((a) => ({ id: `a${a.id}`, at: a.created_at, who: a.actor, kind: a.kind, text: a.body ?? (a.kind === "transitioned" ? `${a.from_value} → ${a.to_value}` : a.kind === "assigned" ? `assigned to ${a.to_value ?? "nobody"}` : a.to_value ?? "") })),
    ...data.comments.map((c) => ({ id: `c${c.id}`, at: c.created_at, who: c.author, kind: "comment", text: c.body })),
  ].sort((a, b) => a.at.localeCompare(b.at));
  return (
    <>
      <DrawerHead
        title={`${data.key} · ${data.type}`}
        sub={data.title}
        onClose={onClose}
        avatar={data.assignee ? <Avatar handle={data.assignee.handle} size={96} color={data.assignee.color} emoji={data.assignee.avatar} /> : undefined}
      />
      <div className="drawer-kpis">
        <Kpi label="status" value={data.status} />
        <Kpi label="priority" value={data.priority} />
        <Kpi label="assignee" value={data.assignee?.display_name ?? "—"} sub={data.assignee?.mode ?? data.assignee?.kind ?? ""} />
        <Kpi label="updated" value={hms(data.updated_at)} sub={`created ${hms(data.created_at)}`} />
      </div>
      <div className="drawer-links">
        {board && (
          <a href={`${board.replace(/\/$/, "")}/issue/${data.key}`} target="_blank" rel="noreferrer">
            open on the board ↗
          </a>
        )}
        {data.pr_url && (
          <a href={data.pr_url} target="_blank" rel="noreferrer">
            pull request ↗
          </a>
        )}
        {row && (
          <button className="linkish" onClick={() => onSelect({ kind: "stage", ticket: data.key, stage: row.stage })}>
            pipeline: {row.stage.replace("_", " ")} →
          </button>
        )}
        {data.labels.map((l) => (
          <span key={l} className="label">
            {l}
          </span>
        ))}
      </div>
      <section className="drawer-section">
        <h3>Description</h3>
        {data.description ? <Markdown text={data.description} /> : <p className="muted">No description.</p>}
      </section>
      <section className="drawer-section">
        <h3>
          Activity <span className="muted">· {feed.length}</span>
        </h3>
        <ol className="prose">
          {feed.map((f) => (
            <li key={f.id}>
              <span className="prose-time">{hms(f.at)}</span>
              <span className="prose-body">
                <span className="prose-who" style={{ color: f.who.color }}>
                  {f.who.display_name}
                </span>
                <span className="prose-kind">{f.kind}</span>
                <span className="prose-text">{f.kind === "comment" || f.kind === "reasoning" ? <Markdown text={f.text} /> : f.text}</span>
              </span>
            </li>
          ))}
        </ol>
      </section>
    </>
  );
}

// ----------------------------------------------------------------------------- pieces

function DrawerHead({ title, sub, onClose, tone, avatar }: { title: string; sub?: string; onClose: () => void; tone?: "amber" | "violet"; avatar?: JSX.Element }) {
  return (
    <header className={`drawer-head ${tone ? `tone-${tone}` : ""}`}>
      {avatar}
      <div className="drawer-head-text">
        <h2>{title}</h2>
        {sub && <div className="drawer-sub">{sub}</div>}
      </div>
      <button className="drawer-close" onClick={onClose} aria-label="close">
        ✕
      </button>
    </header>
  );
}

function Kpi({ label, value, sub, live, tone }: { label: string; value: string; sub?: string; live?: boolean; tone?: "amber" | "violet" }) {
  return (
    <div className={`kpi ${tone ? `tone-${tone}` : ""} ${live ? "kpi-live" : ""}`}>
      <span className="kpi-value">{value}</span>
      <span className="kpi-label">{label}</span>
      {sub && <span className="kpi-sub">{sub}</span>}
    </div>
  );
}

export function AuthorityChips({ authority, full }: { authority: Record<string, unknown>; full?: boolean }) {
  const keys = full ? Object.keys(authority).filter((k) => typeof authority[k] === "boolean") : CHIPS.map(([k]) => k);
  const label = (k: string) => CHIPS.find(([key]) => key === k)?.[1] ?? k.replace(/^can_/, "").replace(/_/g, " ");
  return (
    <div className="chips">
      {keys.map((k) => {
        const on = authority[k] === true;
        return (
          <span key={k} className={`chip ${on ? "chip-on" : "chip-off"}`}>
            {on ? "✓" : "✕"} {label(k)}
          </span>
        );
      })}
    </div>
  );
}

function uniqueActors(evs: MissionEvent[], fleet: FleetCard[]) {
  const seen = new Map<string, { card: FleetCard | undefined; last: MissionEvent; human: boolean }>();
  for (const e of evs) {
    const h = e.actor?.handle;
    if (!h) continue;
    seen.set(h, { card: fleet.find((c) => c.handle === h), last: e, human: e.actor?.kind === "human" });
  }
  return [...seen.values()];
}

function collapse(evs: MissionEvent[]): { e: MissionEvent; n: number }[] {
  const out: { e: MissionEvent; n: number; key: string }[] = [];
  for (const e of evs) {
    const key = e.detail_type === "error.raised" ? `err|${errorSignature(e)}` : `${e.detail_type}|${e.actor?.handle}|${str(e.detail.thinking) || e.summary}`;
    const last = out[out.length - 1];
    if (last && last.key === key) {
      last.n += 1;
      last.e = e; // keep the latest
    } else out.push({ e, n: 1, key });
  }
  return out;
}

function textOf(e: MissionEvent): string {
  if (e.detail_type === "error.raised") {
    const d = e.detail;
    return `${str(d.status_code)} ${str(d.method)} ${str(d.endpoint)} — ${str(d.message) || str(d.error_type)}`.trim();
  }
  return str(e.detail.thinking) || e.summary || e.detail_type;
}

function nameOf(e: MissionEvent): string {
  return e.actor?.display_name ?? e.source.replace("atlas.", "");
}

function colorOf(e: MissionEvent): string {
  if (e.actor?.kind === "human") return "#f5b942";
  return AGENT_COLORS[e.actor?.handle ?? ""] ?? (e.source === "atlas.platform" ? "#ef4444" : "#94a0bd");
}

function artefacts(evs: MissionEvent[], row: PipelineRow, state: MissionState) {
  const branchEv = evs.find((e) => e.detail_type === "branch.created");
  const prEv = [...evs].reverse().find((e) => e.detail_type === "pr.opened" || e.detail_type === "pr.updated");
  const reviewEv = [...evs].reverse().find((e) => e.detail_type === "review.posted" || e.detail_type === "review.changes_requested");
  const deployEv = evs.find((e) => e.detail_type === "deploy.completed");
  const verifyEv = [...evs].reverse().find((e) => e.detail_type === "verify.passed" || e.detail_type === "verify.failed");
  const gh = state.links?.github;
  const board = state.links?.board;
  const prBody = prEv ? str(prEv.detail.body) || summaryJson(prEv.detail.summary_json) : "";
  const smoke = verifyEv?.detail.smoke as { ok?: boolean; checks?: unknown[] } | undefined;
  const checks = (smoke?.checks ?? []).map((c) => (typeof c === "string" ? c : str((c as { name?: string }).name) || JSON.stringify(c)));
  return {
    ticketUrl: board ? `${board.replace(/\/$/, "")}/issue/${row.ticket}` : null,
    branch: str(branchEv?.detail.branch) || row.pr?.branch || "",
    prBody,
    review: reviewEv ? { body: str(reviewEv.detail.body) || reviewEv.summary, changes: reviewEv.detail_type === "review.changes_requested" } : null,
    deploy: deployEv
      ? {
          runId: deployEv.detail.run_id as number | undefined,
          url: gh && deployEv.detail.run_id ? `${gh}/actions/runs/${deployEv.detail.run_id}` : null,
          service: str(deployEv.detail.service),
          sha: str(deployEv.detail.sha),
          ts: deployEv.ts,
        }
      : null,
    smoke: verifyEv ? { ok: !!smoke?.ok || verifyEv.detail_type === "verify.passed", checks: checks.length ? checks : [verifyEv.summary], signatureSeen: verifyEv.detail.signature_seen_after_deploy as boolean | number | null | undefined } : null,
  };
}

function summaryJson(v: unknown): string {
  if (!v || typeof v !== "object") return "";
  const o = v as Record<string, unknown>;
  return Object.entries(o)
    .map(([k, val]) => `**${k.replace(/_/g, " ")}**: ${Array.isArray(val) ? "\n" + val.map((x) => `- ${str(x)}`).join("\n") : str(val)}`)
    .join("\n\n");
}
