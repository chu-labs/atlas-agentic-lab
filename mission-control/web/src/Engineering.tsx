import { useMemo } from "react";
import type { BoardIssue } from "./Board";
import { Avatar } from "./Avatar";
import { Fleet } from "./Fleet";
import { Pipeline } from "./Pipeline";
import { Queues } from "./Queues";
import { ThenVsNow } from "./ThenVsNow";
import { Timeline } from "./Timeline";
import type { MissionEvent, MissionState, Selection } from "./types";
import { hms } from "./time";
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

export function Engineering({
  state,
  stateAt,
  events,
  now,
  onSelect,
  selected,
  toast,
}: {
  state: MissionState;
  stateAt: number;
  events: MissionEvent[];
  now: number;
  onSelect: (s: Selection) => void;
  selected: Selection | null;
  toast: (m: string) => void;
}) {
  const issues = useFetch<BoardIssue[]>("/api/board/issues?limit=300", 10000);
  const cicd = useFetch<{ pulls: Pull[]; url: string }>("/api/cicd", 15000);
  const devAgents = state.fleet.filter((c) => c.kind === "teammate" || ["forge", "sentinel", "conductor"].includes(c.handle));
  const engEvents = useMemo(() => events.filter((e) => ENG_SOURCES.has(e.source) || e.actor?.kind === "human" || e.detail_type === "issue.assigned"), [events]);
  const active = state.pipeline.find((r) => r.ticket === state.active_ticket) ?? state.pipeline.find((r) => !r.observing) ?? null;
  const work = useMemo(() => {
    const all = issues.data ?? [];
    const agentWork = all.filter((i) => i.assignee?.kind === "agent" && i.status !== "Done");
    const humanQueue = all.filter((i) => i.assignee?.kind !== "agent" && (i.status === "Triage" || i.status === "Backlog"));
    return { agentWork, humanQueue };
  }, [issues.data]);
  const handToForge = async (i: BoardIssue) => {
    try {
      await postJSON(`/api/board/issues/${i.key}/assign`, { handle: "forge" });
      toast(`${i.key} → Forge. Forge will pick this up within ~20 s.`);
      void issues.reload();
    } catch (e) {
      toast(`Could not assign: ${(e as Error).message}`);
    }
  };
  return (
    <>
      <Pipeline state={state} stateAt={stateAt} now={now} onSelect={onSelect} selected={selected} />
      <div className="eng-lower">
        <div className="eng-left">
          <Fleet fleet={devAgents} onSelect={onSelect} selected={selected} title="Dev agents" />
          <section className="work">
            <div className="section-head">
              Assigned work <span className="count">{work.agentWork.length}</span>
              <span className="muted small"> · {work.humanQueue.length} waiting on humans</span>
            </div>
            <div className="work-list">
              {work.agentWork.map((i) => (
                <button key={i.key} className="work-item" onClick={() => onSelect({ kind: "issue", key: i.key })}>
                  <Avatar handle={i.assignee?.handle} size={28} color={i.assignee?.color} emoji={i.assignee?.avatar} />
                  <span className="issue-key">{i.key}</span>
                  <span className="work-title">{i.title}</span>
                  <span className={`pill pill-status-${i.status.toLowerCase().replace(/\s+/g, "-")}`}>{i.status}</span>
                </button>
              ))}
              {work.humanQueue.slice(0, 6).map((i) => (
                <div key={i.key} className="work-item work-human">
                  <Avatar handle={i.assignee?.handle} size={28} color={i.assignee?.color} emoji={i.assignee?.avatar ?? "?"} />
                  <button className="linkish issue-key" onClick={() => onSelect({ kind: "issue", key: i.key })}>
                    {i.key}
                  </button>
                  <span className="work-title">{i.title}</span>
                  <span className="muted small">{i.assignee?.display_name ?? "unassigned"} · {i.status}</span>
                  <button className="btn-mini" onClick={() => void handToForge(i)} title="hand this to Forge">
                    Assign to Forge
                  </button>
                </div>
              ))}
              {work.agentWork.length + work.humanQueue.length === 0 && <div className="muted small empty">{issues.error ?? "Nothing assigned."}</div>}
            <div className="prs">
            <div className="section-head">
              Open PRs <span className="count">{cicd.data?.pulls.length ?? 0}</span>
              <span className="muted small"> · atlas-platform</span>
            </div>
            {(cicd.data?.pulls ?? []).map((p) => (
              <a key={p.number} className="pr-row" href={p.url} target="_blank" rel="noreferrer">
                <span className="pull-num">#{p.number}</span>
                <span className="work-title">{p.title}</span>
                <span className={`checks ${p.checks.failure ? "bad" : p.checks.pending ? "run" : p.checks.total ? "ok" : "dim"}`}>
                  {p.checks.success}/{p.checks.total} checks
                </span>
                <span className="muted small">{p.reviews.length ? `${p.reviews.length} review${p.reviews.length === 1 ? "" : "s"}` : "no reviews"}</span>
              </a>
            ))}
            {cicd.data && cicd.data.pulls.length === 0 && <div className="muted small empty">No open PRs · {hms(new Date(now).toISOString())}</div>}
            </div>
            </div>
          </section>
        </div>
        <Timeline events={engEvents} activeRow={active} rows={state.pipeline} onSelect={onSelect} title="Delivery timeline" />
        <aside className="side">
          <Queues state={state} />
          <ThenVsNow state={state} stateAt={stateAt} now={now} row={active} />
        </aside>
      </div>
    </>
  );
}
