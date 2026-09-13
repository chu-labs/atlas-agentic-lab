import { useEffect, useMemo, useRef } from "react";
import type { MissionEvent, PipelineRow, Selection } from "./types";
import { belongsTo, stageOf } from "./attribution";
import { Avatar } from "./Avatar";
import { hms, mmss, secondsBetween } from "./time";

const COLORS: Record<string, string> = {
  scout: "#f59e0b",
  forge: "#3b82f6",
  sentinel: "#a855f7",
  conductor: "#10b981",
  watchtower: "#ef4444",
};
const AVATARS: Record<string, string> = {
  scout: "🔭",
  forge: "⚒️",
  sentinel: "🛡️",
  conductor: "🎼",
  watchtower: "🗼",
  "mission-control": "🛰️",
};
const SOURCE_AVATARS: Record<string, string> = {
  "atlas.platform": "💥",
  "atlas.board": "🗂️",
  "atlas.github": "🐙",
  "atlas.workbench": "🧑‍💻",
  "atlas.mission-control": "🛰️",
};

function who(e: MissionEvent): { avatar: string; name: string; color: string; human: boolean } {
  const a = e.actor;
  if (a?.kind === "human") return { avatar: "👤", name: a.display_name || a.handle, color: "#f5b942", human: true };
  if (a?.handle) {
    return { avatar: AVATARS[a.handle] ?? "🤖", name: a.display_name || a.handle, color: COLORS[a.handle] ?? "#8f9bb8", human: false };
  }
  const src = e.source.replace("atlas.", "");
  return { avatar: SOURCE_AVATARS[e.source] ?? "•", name: src, color: e.source === "atlas.platform" ? "#ef4444" : "#8f9bb8", human: false };
}

/** A rendered timeline row: one event, or a run of consecutive near-identical events. */
interface Group {
  latest: MissionEvent; // newest event in the run: its time and text are what we show
  count: number;
  key: string;
}

function str(v: unknown): string {
  return typeof v === "string" ? v : v == null ? "" : String(v);
}

function errorSignature(e: MissionEvent): string {
  const d = e.detail;
  return str(d.signature) || `${str(d.endpoint)}:${str(d.error_type)}`;
}

/** What makes two consecutive events "the same row". Empty string = never collapse. */
function collapseKey(e: MissionEvent): string {
  if (e.detail_type === "error.raised") return `err|${e.source}|${errorSignature(e)}`;
  if (e.detail_type === "agent.status" || e.detail_type === "agent.thinking") {
    const line = str(e.detail.thinking) || e.summary;
    return `status|${e.actor?.handle ?? e.source}|${line}`;
  }
  return "";
}

function isHeartbeat(e: MissionEvent): boolean {
  return e.detail_type === "agent.status" && e.detail.heartbeat === true;
}

/** Newest-first input. Heartbeats vanish; runs of identical rows fold into one with a count. */
export function groupEvents(events: MissionEvent[]): Group[] {
  const out: Group[] = [];
  for (const e of events) {
    if (isHeartbeat(e)) continue;
    const key = collapseKey(e);
    const last = out[out.length - 1];
    if (key && last && last.key === key && last.latest.replay === e.replay) {
      last.count += 1; // `e` is older; `latest` already holds the newest of the run
    } else {
      out.push({ latest: e, count: 1, key: key || `id:${e.id}` });
    }
  }
  return out;
}

function ErrorText({ e }: { e: MissionEvent }) {
  const d = e.detail;
  const where = [str(d.status_code), str(d.method), str(d.endpoint)].filter(Boolean).join(" ");
  const message = str(d.message);
  return (
    <>
      {where && <span className="row-where">{where}</span>}
      <span className="row-summary">{message || e.summary || str(d.error_type)}</span>
      {message && d.error_type ? <span className="row-sig"> · {str(d.error_type)}</span> : null}
    </>
  );
}

export function Timeline({
  events,
  activeRow,
  rows,
  onSelect,
  title = "Timeline",
}: {
  events: MissionEvent[];
  activeRow: PipelineRow | null;
  rows: PipelineRow[];
  onSelect: (s: Selection) => void;
  title?: string;
}) {
  const open = (e: MissionEvent) => {
    const row = rows.find((r) => belongsTo(e, r));
    if (row?.ticket) onSelect({ kind: "stage", ticket: row.ticket, stage: stageOf(e, row) });
  };
  const listRef = useRef<HTMLDivElement>(null);
  const groups = useMemo(() => groupEvents(events), [events]);
  useEffect(() => {
    listRef.current?.scrollTo({ top: 0, behavior: "smooth" });
  }, [groups[0]?.latest.id, groups[0]?.count]);
  const origin = activeRow?.first_ts ?? null;
  return (
    <section className="timeline">
      <h2 className="panel-title">
        {title} <span className="count">{events.length}</span>
        <span className="panel-sub">{groups.length !== events.length ? `${groups.length} rows · repeats collapsed` : "newest first"}</span>
      </h2>
      <div className="timeline-list" ref={listRef}>
        {groups.length === 0 && <div className="muted empty">No events yet.</div>}
        {groups.map((g) => {
          const e = g.latest;
          const w = who(e);
          const rel = origin ? secondsBetween(origin, e.ts) : null;
          const isError = e.detail_type === "error.raised";
          return (
            <div
              key={e.id}
              className={`row ${w.human ? "row-human" : ""} kind-${e.detail_type.replace(".", "-")} ${rows.some((r) => belongsTo(e, r)) ? "row-click" : ""}`}
              onClick={() => open(e)}
            >
              <span className="row-time">{hms(e.ts)}</span>
              <span className="row-rel">{rel != null && rel >= 0 ? `+${mmss(rel)}` : ""}</span>
              <Avatar handle={e.actor?.handle ?? (e.source === "atlas.mission-control" ? "mission-control" : null)} size={32} color={w.color} emoji={w.avatar} className="row-avatar" />
              <span className="row-body">
                <span className="row-name">{w.name}</span>
                {w.human && <span className="human-tag">HUMAN</span>}
                {e.replay && <span className="replay-tag">replay</span>}
                {isError && <span className="row-kind">error.raised</span>}
                {g.count > 1 && <span className="count-tag">×{g.count}</span>}
                {isError ? <ErrorText e={e} /> : <span className="row-summary">{e.summary || e.detail_type}</span>}
              </span>
            </div>
          );
        })}
      </div>
    </section>
  );
}
