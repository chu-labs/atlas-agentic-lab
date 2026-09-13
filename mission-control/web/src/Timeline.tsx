import { useEffect, useRef } from "react";
import type { MissionEvent, PipelineRow } from "./types";
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

export function Timeline({ events, activeRow }: { events: MissionEvent[]; activeRow: PipelineRow | null }) {
  const listRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    listRef.current?.scrollTo({ top: 0, behavior: "smooth" });
  }, [events[0]?.id]);
  const origin = activeRow?.first_ts ?? null;
  return (
    <section className="timeline">
      <h2 className="panel-title">
        Timeline <span className="panel-sub">{events.length ? `${events.length} events` : ""}</span>
      </h2>
      <div className="timeline-list" ref={listRef}>
        {events.length === 0 && <div className="muted empty">No events yet.</div>}
        {events.map((e) => {
          const w = who(e);
          const rel = origin ? secondsBetween(origin, e.ts) : null;
          return (
            <div key={e.id} className={`row ${w.human ? "row-human" : ""} kind-${e.detail_type.replace(".", "-")}`}>
              <span className="row-time">{hms(e.ts)}</span>
              <span className="row-rel">{rel != null && rel >= 0 ? `+${mmss(rel)}` : ""}</span>
              <span className="row-avatar" style={{ background: w.color }}>
                {w.avatar}
              </span>
              <span className="row-body">
                <span className="row-name">{w.name}</span>
                {w.human && <span className="human-tag">HUMAN</span>}
                {e.replay && <span className="replay-tag">replay</span>}
                <span className="row-summary">{e.summary || e.detail_type}</span>
              </span>
            </div>
          );
        })}
      </div>
    </section>
  );
}
