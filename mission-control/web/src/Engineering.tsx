import { useMemo } from "react";
import type { BoardIssue } from "./Board";
import { Avatar } from "./Avatar";
import { Fleet } from "./Fleet";
import { Pipeline } from "./Pipeline";
import { ThenVsNow } from "./ThenVsNow";
import { Timeline } from "./Timeline";
import { SEGMENTS, SEGMENT_LABEL, STAGE_LABEL, type MissionEvent, type MissionState, type PipelineRow, type Selection } from "./types";
import { fmtInt, fmtUSD, hms, mmss } from "./time";
import { DataTable, KpiTile, Panel, StatusChip, toneForStatus, type Column } from "./ui";
import { useFetch } from "./useFetch";
import { postJSON } from "./useMission";

export const ENG_SOURCES = new Set(["atlas.forge", "atlas.sentinel", "atlas.conductor", "atlas.mission-control", "atlas.github", "atlas.workbench"]);

interface Pull {
  number: number;
  title: string;
  url: string;
  author: string;
  branch: string;
  checks: { total: number; success: number; failure: number; pending: number };
  reviews: { user: string; state: string }[];
}
interface DoraTicket {
  ticket: string;
  usd: number;
  total: number | null;
}

interface WorkRow {
  key: string;
  title: string;
  stage: string | null;
  row: PipelineRow | null;
  issue: BoardIssue | null;
  pull: Pull | null;
  usd: number | null;
}

export function Engineering({
  state,
  stateAt,
  events,
  now,
  onSelect,
  selected,
  toast,
  query,
}: {
  state: MissionState;
  stateAt: number;
  events: MissionEvent[];
  now: number;
  onSelect: (s: Selection) => void;
  selected: Selection | null;
  toast: (m: string) => void;
  query: string;
}) {
  const issues = useFetch<BoardIssue[]>("/api/board/issues?limit=300", 10000);
  const cicd = useFetch<{ pulls: Pull[]; url: string }>("/api/cicd", 15000);
  const dora = useFetch<{ tickets: DoraTicket[] }>("/api/dora?window=all", 20000);
  const devAgents = state.fleet.filter((c) => c.kind === "teammate" || ["forge", "sentinel", "conductor"].includes(c.handle));
  const engEvents = useMemo(() => events.filter((e) => ENG_SOURCES.has(e.source) || e.actor?.kind === "human" || e.detail_type === "issue.assigned"), [events]);
  const active = state.pipeline.find((r) => r.ticket === state.active_ticket) ?? state.pipeline.find((r) => !r.observing) ?? null;
  const tel = state.telemetry;

  const work: WorkRow[] = useMemo(() => {
    const all = issues.data ?? [];
    const usd = new Map((dora.data?.tickets ?? []).map((t) => [t.ticket, t.usd]));
    const pulls = cicd.data?.pulls ?? [];
    const rows = new Map<string, WorkRow>();
    for (const r of state.pipeline) {
      if (!r.ticket) continue;
      rows.set(r.ticket, { key: r.ticket, title: r.title, stage: r.stage, row: r, issue: null, pull: pulls.find((p) => p.number === r.pr?.number) ?? null, usd: usd.get(r.ticket) ?? null });
    }
    for (const i of all) {
      const agent = i.assignee?.kind === "agent" && i.status !== "Done";
      const queued = i.assignee?.kind !== "agent" && (i.status === "Triage" || i.status === "Backlog");
      if (!agent && !queued && !rows.has(i.key)) continue;
      const ex = rows.get(i.key);
      if (ex) ex.issue = i;
      else rows.set(i.key, { key: i.key, title: i.title, stage: null, row: null, issue: i, pull: pulls.find((p) => p.branch?.includes(i.key)) ?? null, usd: usd.get(i.key) ?? null });
    }
    const q = query.trim().toLowerCase();
    const rank = (w: WorkRow) => (w.row ? 0 : w.issue?.assignee?.kind === "agent" ? 1 : w.issue?.status === "Triage" ? 2 : 3);
    return [...rows.values()]
      .filter((w) => !q || `${w.key} ${w.title} ${w.issue?.assignee?.display_name ?? ""}`.toLowerCase().includes(q))
      .sort((a, b) => rank(a) - rank(b) || (b.issue?.updated_at ?? "").localeCompare(a.issue?.updated_at ?? ""));
  }, [issues.data, dora.data, cicd.data, state.pipeline, query]);

  const handToForge = async (key: string) => {
    try {
      await postJSON(`/api/board/issues/${key}/assign`, { handle: "forge" });
      toast(`${key} → Forge. Forge will pick this up within ~20 s.`);
      void issues.reload();
    } catch (e) {
      toast(`Could not assign: ${(e as Error).message}`);
    }
  };

  const cols: Column<WorkRow>[] = [
    { key: "key", title: "Ticket", width: "6.5rem", mono: true, render: (w) => <span className="b">{w.key}</span>, sort: (w) => w.key },
    { key: "title", title: "Title", width: "14rem", render: (w) => <span title={w.title}>{w.title}</span>, sort: (w) => w.title },
    {
      key: "stage", title: "Stage", width: "7rem",
      render: (w) => (w.row ? <StatusChip tone={w.row.closed ? "ok" : w.row.escalated ? "violet" : w.row.stage === "human_gate" ? "amber" : "accent"} icon={false}>{w.row.escalated ? "escalated" : STAGE_LABEL[w.row.stage]}</StatusChip> : <StatusChip tone={toneForStatus(w.issue?.status ?? "")} icon={false}>{w.issue?.status ?? "—"}</StatusChip>),
      sort: (w) => w.row?.stage ?? w.issue?.status,
    },
    {
      key: "who", title: "Assignee", width: "7.5rem",
      render: (w) => {
        const a = w.issue?.assignee;
        const handle = a?.handle ?? (w.row ? (w.row.stage === "human_gate" ? "maroun" : w.row.stage === "verify" || w.row.stage === "deploy" ? "conductor" : w.row.stage === "pr" ? "sentinel" : "forge") : null);
        return <span className="avatar-cell"><Avatar handle={handle} size={20} color={a?.color} emoji={a?.avatar} />{a?.display_name ?? (handle ? handle[0].toUpperCase() + handle.slice(1) : "—")}</span>;
      },
      sort: (w) => w.issue?.assignee?.display_name,
    },
    {
      key: "elapsed", title: "Elapsed per stage", width: "18.5rem",
      render: (w) =>
        w.row ? (
          <span className="segchips">
            {SEGMENTS.map((s) => {
              const v = w.row!.durations.segments[s];
              if (v == null) return null;
              const live = w.row!.durations.open_segment === s && !w.row!.durations.frozen;
              return (
                <span key={s} className={`segchip seg-${s} ${live ? "live" : ""}`} title={SEGMENT_LABEL[s]}>
                  {SEGMENT_LABEL[s][0]} {mmss(v + (live ? (now - stateAt) / 1000 : 0))}
                </span>
              );
            })}
          </span>
        ) : (
          <span className="m">{w.issue ? `updated ${hms(w.issue.updated_at)}` : ""}</span>
        ),
      sort: (w) => w.row?.durations.total,
    },
    {
      key: "pr", title: "PR", width: "5rem", mono: true,
      render: (w) => (w.row?.pr ? <a href={w.row.pr.url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>#{w.row.pr.number}</a> : w.issue?.pr_url ? <a href={w.issue.pr_url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>PR</a> : "—"),
      sort: (w) => w.row?.pr?.number,
    },
    {
      key: "checks", title: "Checks", width: "4.5rem", align: "right", mono: true,
      render: (w) => (w.pull ? <span className={w.pull.checks.failure ? "bad" : w.pull.checks.pending ? "m" : "ok"}>{w.pull.checks.success}/{w.pull.checks.total}</span> : "—"),
    },
    { key: "cost", title: "Cost", width: "5rem", align: "right", mono: true, render: (w) => (w.usd != null ? fmtUSD(w.usd) : w.key === tel.ticket ? fmtUSD(tel.usd) : "—"), sort: (w) => w.usd },
    { key: "tokens", title: "Tokens", width: "5.5rem", align: "right", mono: true, render: (w) => (w.key === tel.ticket ? fmtInt(tel.tokens_in + tel.tokens_out) : "—") },
    {
      key: "act", title: "", width: "7rem", align: "right",
      render: (w) =>
        !w.row && w.issue && w.issue.assignee?.kind !== "agent" ? (
          <button className="btn-mini" title="assign to Forge" onClick={(e) => { e.stopPropagation(); void handToForge(w.key); }}>→ Forge</button>
        ) : null,
    },
  ];

  return (
    <>
      <Pipeline state={state} stateAt={stateAt} now={now} onSelect={onSelect} selected={selected} />
      <div className="kpis kpis-5 span-12">
        <KpiTile label="Active ticket" value={active?.ticket ?? "—"} sub={active?.title ?? "waiting for Scout"} tone="accent" onClick={active?.ticket ? () => onSelect({ kind: "stage", ticket: active.ticket!, stage: active.stage }) : undefined} />
        <KpiTile label="Error → PR" value={mmss(tel.error_to_pr_seconds)} tone="success" sub="wall clock" />
        <KpiTile label="Waiting on a human" value={state.gate.waiting ? mmss(state.gate.waited_seconds + (now - stateAt) / 1000) : "—"} tone={state.gate.waiting ? "warning" : "muted"} sub={state.gate.waiting ? `PR #${state.gate.pr?.number}` : "nothing at the gate"} />
        <KpiTile label="Model spend" value={fmtUSD(tel.usd)} sub={`${fmtInt(tel.tokens_in)} in · ${fmtInt(tel.tokens_out)} out · ${fmtInt(tel.model_calls)} calls`} tone="success" />
        <KpiTile label="Agents working" value={`${devAgents.filter((c) => c.status !== "idle").length}/${devAgents.length}`} sub={devAgents.filter((c) => c.status !== "idle").map((c) => c.display_name).join(", ") || "all idle"} tone="accent" />
      </div>
      <Panel title="Work" count={work.length} sub={issues.error ? issues.error : "tickets in the pipeline and assigned work from the board"} className="span-8 fill">
        <DataTable rows={work} columns={cols} rowKey={(w) => w.key} onRowClick={(w) => (w.row ? onSelect({ kind: "stage", ticket: w.key, stage: w.row.stage }) : onSelect({ kind: "issue", key: w.key }))} selectedKey={selected?.kind === "stage" ? selected.ticket : selected?.kind === "issue" ? selected.key : null} dense emptyText="nothing assigned" />
      </Panel>
      <div className="span-4 eng-side">
        <Panel title="Dev agents" count={devAgents.length} sub={`${devAgents.filter((c) => c.status !== "idle").length} active`}>
          <Fleet fleet={devAgents} onSelect={onSelect} selected={selected} compact />
        </Panel>
        <ThenVsNow state={state} stateAt={stateAt} now={now} row={active} />
      </div>
      <Timeline events={engEvents} activeRow={active} rows={state.pipeline} onSelect={onSelect} title="Delivery timeline" dense className="span-12 fill" query={query} />
    </>
  );
}
