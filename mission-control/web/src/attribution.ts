import { STAGES, type FleetCard, type MissionEvent, type PipelineRow, type Segment, type Stage } from "./types";

export function str(v: unknown): string {
  return typeof v === "string" ? v : v == null ? "" : String(v);
}

export function errorSignature(e: MissionEvent): string {
  const d = e.detail;
  return str(d.signature) || `${str(d.endpoint)}:${str(d.error_type)}`;
}

export function isHeartbeat(e: MissionEvent): boolean {
  return e.detail_type === "agent.status" && e.detail.heartbeat === true;
}

const TICKET_KEY = /^[A-Z][A-Z0-9]*-\d+$/;

/** Does this event belong to the ticket row? Errors match by signature; Scout's triage-time events match by window. */
export function belongsTo(e: MissionEvent, row: PipelineRow): boolean {
  if (e.ticket === row.ticket) return true;
  if (e.detail_type === "error.raised") return !!row.signature && errorSignature(e) === row.signature;
  if (e.ticket && !TICKET_KEY.test(e.ticket)) {
    // a pseudo-ticket such as "triage": ours if it sits between the first error and the ticket being opened
    const start = row.stages.error ?? row.stages.triage;
    const end = row.stages.ticket;
    const t = Date.parse(e.ts);
    return !!start && t >= Date.parse(start) - 1000 && (!end || t <= Date.parse(end) + 1000);
  }
  return false;
}

/** Ordered (stage, ms) entries for a row. */
export function stageEntries(row: PipelineRow): { s: Stage; t: number }[] {
  return STAGES.filter((s) => row.stages[s])
    .map((s) => ({ s, t: Date.parse(row.stages[s]!) }))
    .sort((a, b) => a.t - b.t);
}

/** Which stage an event happened in: the latest stage entered at or before the event's time. */
export function stageOf(e: MissionEvent, row: PipelineRow): Stage {
  if (e.detail_type === "error.raised") return "error";
  const t = Date.parse(e.ts);
  const entries = stageEntries(row);
  let best: Stage = entries[0]?.s ?? "ticket";
  for (const en of entries) if (en.t <= t + 500) best = en.s;
  // the event that *enters* a stage belongs to that stage
  const enters: Partial<Record<string, Stage>> = {
    "incident.opened": "ticket",
    "issue.created": "ticket",
    "branch.created": "code",
    "pr.opened": "pr",
    "pr.updated": "pr",
    "review.posted": "human_gate",
    "human.gate_waiting": "human_gate",
    "human.approved": "human_gate",
    "human.rejected": "human_gate",
    "pr.merged": "merge",
    "deploy.completed": "deploy",
    "verify.passed": "verify",
    "verify.failed": "verify",
    "ticket.closed": "closed",
  };
  return enters[e.detail_type] ?? best;
}

/** The duration segment a stage rolls up into for the chip strip. */
export function segmentOf(stage: Stage): Segment {
  switch (stage) {
    case "error":
    case "triage":
    case "ticket":
      return "triage";
    case "code":
    case "test":
      return "code";
    case "pr":
      return "review";
    case "human_gate":
      return "gate";
    case "merge":
    case "deploy":
      return "deploy";
    default:
      return "verify";
  }
}

export interface TelemetryDelta {
  tokens_in: number;
  tokens_out: number;
  model_calls: number;
  usd: number;
}

function tel(e: MissionEvent): Record<string, number> | null {
  const t = e.detail.telemetry;
  return t && typeof t === "object" ? (t as Record<string, number>) : null;
}

/** Tokens and cost spent inside a window: per agent, (max cumulative inside) − (max cumulative before), summed. */
export function telemetryBetween(events: MissionEvent[], fromMs: number, toMs: number): TelemetryDelta {
  const before: Record<string, Record<string, number>> = {};
  const inside: Record<string, Record<string, number>> = {};
  for (const e of events) {
    const t = tel(e);
    const h = e.actor?.handle;
    if (!t || !h) continue;
    const ms = Date.parse(e.ts);
    const target = ms < fromMs ? before : ms <= toMs ? inside : null;
    if (!target) continue;
    const cur = (target[h] ||= {});
    for (const k of ["tokens_in", "tokens_out", "model_calls", "usd"]) cur[k] = Math.max(cur[k] ?? 0, Number(t[k] ?? 0));
  }
  const out: TelemetryDelta = { tokens_in: 0, tokens_out: 0, model_calls: 0, usd: 0 };
  for (const h of Object.keys(inside)) {
    for (const k of Object.keys(out) as (keyof TelemetryDelta)[]) {
      out[k] += Math.max(0, (inside[h][k] ?? 0) - (before[h]?.[k] ?? 0));
    }
  }
  return out;
}

export function authorityAt(e: MissionEvent | undefined, card: FleetCard | undefined): Record<string, unknown> {
  const fromEvent = e?.detail.authority;
  if (fromEvent && typeof fromEvent === "object") return fromEvent as Record<string, unknown>;
  return (card?.authority as Record<string, unknown>) ?? {};
}
