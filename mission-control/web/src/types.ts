export const STAGES = [
  "error",
  "triage",
  "ticket",
  "code",
  "test",
  "pr",
  "human_gate",
  "merge",
  "deploy",
  "verify",
  "closed",
] as const;
export type Stage = (typeof STAGES)[number];

export const STAGE_LABEL: Record<Stage, string> = {
  error: "Error",
  triage: "Triage",
  ticket: "Ticket",
  code: "Code",
  test: "Test",
  pr: "PR",
  human_gate: "Human gate",
  merge: "Merge",
  deploy: "Deploy",
  verify: "Verify",
  closed: "Closed",
};

export type AgentStatus = "idle" | "working" | "waiting_on_human" | "waiting_on_review" | "blocked" | "escalated";

export interface Actor {
  handle: string;
  kind: "agent" | "human" | "system";
  display_name: string;
  mode: "autonomous" | "supervised" | null;
}

export interface FleetCard {
  handle: string;
  kind: "fleet" | "teammate";
  display_name: string;
  avatar: string;
  color: string;
  remit: string;
  mode: "autonomous" | "supervised";
  authority: Record<string, boolean | string[]>;
  status: AgentStatus;
  thinking: string;
  ticket: string | null;
  last_seen: string | null;
}

export interface PR {
  number: number;
  url?: string;
  title?: string;
  branch?: string;
}

export interface PipelineRow {
  ticket: string | null;
  title: string;
  stage: Stage;
  stages: Partial<Record<Stage, string>>;
  escalated: boolean;
  escalation: { summary?: string; category?: string; to?: string } | null;
  verify_failed: boolean;
  pr: PR | null;
  error: {
    signature?: string | null;
    endpoint?: string | null;
    error_type?: string | null;
    message?: string | null;
    count: number;
    first_seen?: string | null;
    last_seen?: string | null;
  } | null;
  signature: string | null;
  first_ts: string;
  updated_ts: string;
  closed_ts: string | null;
  closed: boolean;
  durations: Durations;
}

export type Segment = "triage" | "code" | "review" | "gate" | "deploy" | "verify";
export const SEGMENTS: Segment[] = ["triage", "code", "review", "gate", "deploy", "verify"];
export const SEGMENT_LABEL: Record<Segment, string> = {
  triage: "Triage",
  code: "Code",
  review: "Review",
  gate: "Gate",
  deploy: "Deploy",
  verify: "Verify",
};

export interface Durations {
  segments: Partial<Record<Segment, number>>;
  open_segment: Segment | null;
  total: number;
  human: number;
  machine: number;
  frozen: boolean;
}

export interface Signal {
  rate: number[];
  bucket_seconds: number;
  total_10m: number;
  per_minute: number;
  untracked_count: number;
  untracked_signatures: number;
  latest: {
    signature: string | null;
    count: number;
    first_ts: string;
    last_ts: string;
    message?: string | null;
    endpoint?: string | null;
    error_type?: string | null;
    status_code?: number | null;
    method?: string | null;
  } | null;
  triage_since: string | null;
}

export interface Gate {
  waiting: boolean;
  pr: PR | null;
  ticket: string | null;
  since: string | null;
  waited_seconds: number;
}

export interface Telemetry {
  ticket: string | null;
  tokens_in: number;
  tokens_out: number;
  model_calls: number;
  seconds: number;
  usd: number;
  first_ts?: string | null;
  pr_ts?: string | null;
  closed_ts?: string | null;
  error_to_pr_seconds?: number | null;
  error_to_closed_seconds?: number | null;
  closed?: boolean;
}

export interface Baselines {
  human_days_error_to_pr: number;
  human_days_error_to_closed: number;
  human_hourly_rate_aud: number;
  human_engineering_hours: number;
  stage_days: Record<string, number>;
  notes?: string;
}

export interface MissionState {
  now: string;
  active_ticket: string | null;
  fleet: FleetCard[];
  pipeline: PipelineRow[];
  gate: Gate;
  telemetry: Telemetry;
  queues: Record<string, number>;
  signal: Signal;
  baselines: Baselines;
  replaying: boolean;
  last_event_id: number;
  human?: { login: string; display_name: string; configured: boolean };
  links?: { board?: string; platform?: string; github?: string };
}

export type Selection = { kind: "stage"; ticket: string; stage: Stage } | { kind: "agent"; handle: string };

export interface MissionEvent {
  id: number;
  received_at: string;
  ts: string;
  source: string;
  detail_type: string;
  ticket: string | null;
  actor: Actor | null;
  summary: string;
  detail: Record<string, unknown>;
  replay: boolean;
}
