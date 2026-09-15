export type Tone = "ok" | "warn" | "bad" | "info" | "muted" | "accent" | "amber" | "violet";

const ICON: Record<Tone, string> = { ok: "●", warn: "▲", bad: "✕", info: "◆", muted: "○", accent: "●", amber: "●", violet: "◆" };

export function StatusChip({ tone = "muted", children, icon = true, pulse = false, title }: { tone?: Tone; children: React.ReactNode; icon?: boolean; pulse?: boolean; title?: string }) {
  return (
    <span className={`chip2 chip2-${tone} ${pulse ? "chip2-pulse" : ""}`} title={title}>
      {icon && <span className="chip2-ico">{ICON[tone]}</span>}
      {children}
    </span>
  );
}

export function toneForStatus(s: string): Tone {
  switch (s) {
    case "working":
    case "in_progress":
    case "In Progress":
    case "ticketed":
    case "running":
      return "accent";
    case "idle":
    case "Backlog":
    case "resolved":
    case "closed":
    case "Done":
    case "success":
    case "ok":
      return s === "idle" || s === "Backlog" ? "muted" : "ok";
    case "waiting_on_human":
    case "waiting_on_review":
    case "Triage":
    case "In Review":
    case "waiting":
    case "observing":
      return s === "observing" ? "bad" : "amber";
    case "blocked":
    case "failure":
    case "alerting":
    case "verify failed":
      return "bad";
    case "escalated":
      return "violet";
    default:
      return "muted";
  }
}
