import { Avatar } from "./Avatar";
import { VIEWS, type View } from "./Nav";
import type { FleetCard, Selection } from "./types";

const DOT: Record<string, string> = { idle: "muted", working: "accent", waiting_on_human: "amber", waiting_on_review: "info", blocked: "bad", escalated: "violet" };

export function Rail({
  view,
  onView,
  counts,
  fleet,
  onSelect,
  selected,
  foot,
}: {
  view: View;
  onView: (v: View) => void;
  counts: Partial<Record<View, string | number>>;
  fleet: FleetCard[];
  onSelect: (s: Selection) => void;
  selected: Selection | null;
  foot: React.ReactNode;
}) {
  const active = fleet.filter((c) => c.status !== "idle").length;
  return (
    <aside className="rail">
      <div className="rail-sec">views</div>
      {VIEWS.map((v) => (
        <button key={v.id} className={`rail-item ${view === v.id ? "on" : ""}`} onClick={() => onView(v.id)}>
          <span className="rail-key">{v.key}</span>
          <span className="rail-label">{v.label}</span>
          {counts[v.id] != null && counts[v.id] !== "" && <span className="rail-count">{counts[v.id]}</span>}
        </button>
      ))}
      <div className="rail-sec">
        fleet <span className="rail-sec-n">{active}/{fleet.length} active</span>
      </div>
      {fleet.map((c) => (
        <button key={c.handle} className={`rail-agent ${selected?.kind === "agent" && selected.handle === c.handle ? "on" : ""}`} onClick={() => onSelect({ kind: "agent", handle: c.handle })} title={c.thinking || c.remit}>
          <Avatar handle={c.handle} size={24} color={c.color} emoji={c.avatar} />
          <span className="rail-agent-name">{c.display_name}</span>
          <span className="rail-agent-ticket mono">{c.ticket ?? ""}</span>
          <span className={`dot dot-${DOT[c.status] ?? "muted"}`} title={c.status.replace(/_/g, " ")} />
        </button>
      ))}
      <div className="rail-foot">{foot}</div>
    </aside>
  );
}
