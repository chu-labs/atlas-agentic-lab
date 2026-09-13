import type { AgentStatus, FleetCard } from "./types";

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

export function Fleet({ fleet }: { fleet: FleetCard[] }) {
  return (
    <section className="fleet">
      <h2 className="panel-title">Fleet</h2>
      <div className="fleet-cards">
        {fleet.map((c) => (
          <article key={c.handle} className={`card status-${c.status} ${c.kind === "teammate" ? "card-teammate" : ""}`} style={{ ["--agent" as string]: c.color }}>
            <div className="card-head">
              <span className="avatar" style={{ background: c.color }}>
                {c.avatar}
              </span>
              <div className="card-id">
                <div className="card-name-row">
                  <span className="card-name">{c.display_name}</span>
                  {c.ticket && <span className="card-ticket">{c.ticket}</span>}
                  <span className={`pill pill-${c.status}`}>{STATUS_LABEL[c.status] ?? c.status}</span>
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
          </article>
        ))}
      </div>
    </section>
  );
}
