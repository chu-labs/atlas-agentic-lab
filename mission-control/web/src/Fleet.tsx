import { Avatar } from "./Avatar";
import type { AgentStatus, FleetCard, Selection } from "./types";

const CHIPS: [string, string][] = [
  ["can_write_code", "code"],
  ["can_review", "review"],
  ["can_merge", "merge"],
  ["can_deploy", "deploy"],
  ["can_change_business_rules", "rules"],
];

const STATUS_LABEL: Record<AgentStatus, string> = {
  idle: "idle",
  working: "working",
  waiting_on_human: "needs human",
  waiting_on_review: "in review",
  blocked: "blocked",
  escalated: "escalated",
};

export function Fleet({ fleet, onSelect, selected, title = "Fleet" }: { fleet: FleetCard[]; onSelect: (s: Selection) => void; selected: Selection | null; title?: string }) {
  return (
    <section className="fleet">
      <h2 className="panel-title">
        {title} <span className="count">{fleet.length}</span>
        <span className="panel-sub">{fleet.filter((c) => c.status !== "idle").length} active · click for reasoning</span>
      </h2>
      <div className="fleet-cards">
        {fleet.map((c) => (
          <button
            key={c.handle}
            className={`card status-${c.status} ${c.kind === "teammate" ? "card-teammate" : ""} ${selected?.kind === "agent" && selected.handle === c.handle ? "selected" : ""}`}
            style={{ ["--agent" as string]: c.color }}
            onClick={() => onSelect({ kind: "agent", handle: c.handle })}
          >
            <div className="card-head">
              <Avatar handle={c.handle} size={56} color={c.color} emoji={c.avatar} className="av-card" />
              <div className="card-id">
                <div className="card-name-row">
                  <span className="card-name">{c.display_name}</span>
                  {c.ticket && <span className="card-ticket">{c.ticket}</span>}
                  <span className={`pill pill-${c.status}`}>{STATUS_LABEL[c.status] ?? c.status}</span>
                </div>
                <div className="chips">
                  {CHIPS.map(([k, label]) => {
                    const on = c.authority?.[k] === true;
                    return (
                      <span key={k} className={`chip ${on ? "chip-on" : "chip-off"}`}>
                        {on ? "✓" : "✕"} {label}
                      </span>
                    );
                  })}
                </div>
                <div className="card-remit" title={c.remit}>
                  <span className={`mode-tag mode-${c.mode}`}>{c.mode}</span>
                  {c.remit}
                </div>
              </div>
            </div>
            <div className="thinking-wrap">
              <p key={c.thinking} className="thinking">
                {c.thinking || <span className="muted">—</span>}
              </p>
            </div>
          </button>
        ))}
      </div>
    </section>
  );
}
