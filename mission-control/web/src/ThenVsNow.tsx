import { STAGES, STAGE_LABEL, type Baselines, type MissionState, type PipelineRow, type Stage } from "./types";
import { fmtInt, fmtUSD, mmss } from "./time";
import { useTween } from "./useMission";

/** A lane column: one of our eleven stages, or the traditional "backlog wait" that has no agentic counterpart. */
export type LaneKey = Stage | "backlog_wait";
export const LANE_KEYS: LaneKey[] = ["error", "triage", "ticket", "backlog_wait", "code", "test", "pr", "human_gate", "merge", "deploy", "verify", "closed"];
const LANE_LABEL: Record<LaneKey, string> = { ...STAGE_LABEL, error: "Detect", human_gate: "Review", deploy: "Change approval", backlog_wait: "Backlog wait" };

/** Traditional-SDLC calendar days per lane column, from the baselines' stage_days. */
export function baselineDays(b: Baselines): Record<LaneKey, number> {
  const d = b.stage_days || {};
  const g = (k: string) => Number(d[k] ?? 0);
  return {
    error: g("detect"),
    triage: g("triage"),
    ticket: g("ticket"),
    backlog_wait: g("backlog_wait"),
    code: g("code"),
    test: g("test"),
    pr: g("pr"),
    human_gate: g("review") + g("gate"),
    merge: 0,
    deploy: g("deploy"),
    verify: g("verify"),
    closed: 0,
  };
}

/** Live seconds per stage: entry to the next entered stage; the current stage runs to `now`. */
export function liveStageSeconds(row: PipelineRow, nowMs: number): Partial<Record<Stage, number>> {
  const entries = STAGES.filter((s) => row.stages[s]).map((s) => ({ s, t: Date.parse(row.stages[s]!) }));
  entries.sort((a, b) => a.t - b.t);
  const end = row.closed_ts ? Date.parse(row.closed_ts) : row.escalated ? Date.parse(row.updated_ts) : nowMs;
  const out: Partial<Record<Stage, number>> = {};
  entries.forEach((e, i) => {
    const next = i + 1 < entries.length ? entries[i + 1].t : end;
    out[e.s] = Math.max(0, (next - e.t) / 1000);
  });
  return out;
}

export function fmtDaysShort(days: number): string {
  if (days <= 0) return "";
  if (days < 1) return `${Math.round(days * 24)}h`;
  return Number.isInteger(days) ? `${days}d` : `${days.toFixed(1)}d`;
}

function fmtDaysLong(days: number): string {
  if (days < 1) return `${Math.round(days * 24)} hours`;
  const r = Math.round(days * 2) / 2;
  return `${Number.isInteger(r) ? r : r.toFixed(1)} days`;
}

export function ThenVsNow({
  state,
  stateAt,
  now,
  row,
  size = "panel",
}: {
  state: MissionState;
  stateAt: number;
  now: number;
  row: PipelineRow | null;
  size?: "panel" | "large";
}) {
  const b = state.baselines;
  const t = state.telemetry;
  const days = baselineDays(b);
  const thenTotalDays = LANE_KEYS.reduce((a, s) => a + days[s], 0);
  const live = row ? liveStageSeconds(row, now) : {};
  const drift = row && !row.closed && !row.escalated ? (now - stateAt) / 1000 : 0;
  const nowTotal = row ? row.durations.total + drift : 0;
  const humanSecs = row ? row.durations.human + (row.durations.open_segment === "gate" ? drift : 0) : 0;
  const rate = b.human_hourly_rate_aud || 185;
  const humanCost = (b.human_engineering_hours || 0) * rate;
  const cost = useTween(t.usd);
  const tokensIn = useTween(t.tokens_in);
  const tokensOut = useTween(t.tokens_out);
  const calls = useTween(t.model_calls);
  const ratio = nowTotal > 0 ? (thenTotalDays * 86400) / nowTotal : 0;

  return (
    <section className={`tvn tvn-${size}`}>
      <h2 className="panel-title">
        Then vs now <span className="panel-sub">{row ? row.ticket : "no active ticket"}</span>
      </h2>
      <div className="tvn-big">
        <span className="tvn-then">~{fmtDaysLong(thenTotalDays)}</span>
        <span className="tvn-arrow">→</span>
        <span className="tvn-now">{row ? mmss(nowTotal) : "–:––"}</span>
        {ratio > 1 && nowTotal >= 60 && <span className="tvn-ratio">{ratio >= 100 ? `${fmtInt(ratio)}×` : `${ratio.toFixed(0)}×`} faster</span>}
      </div>
      <Lane
        title="Now · agentic"
        kind="now"
        parts={STAGES.map((s) => ({ s, v: live[s] ?? 0, label: live[s] ? mmss(live[s]) : "" }))}
        active={row && !row.closed && !row.escalated ? row.stage : null}
      />
      <Lane
        title={`Then · ${b.lane_label ?? "traditional SDLC"}`}
        kind="then"
        parts={LANE_KEYS.map((s) => ({ s, v: days[s] * 86400, label: fmtDaysShort(days[s]) }))}
        active={null}
      />
      <div className="tvn-cost">
        <span>
          <b className="tvn-cost-now">{fmtUSD(cost)}</b> of model time
        </span>
        <span className="tvn-vs">vs</span>
        <span>
          <b className="tvn-cost-then">~${fmtInt(humanCost)}</b> of engineering time at ${rate}/h
        </span>
      </div>
      <div className="tvn-small">
        <span>
          <b>{fmtInt(tokensIn)}</b> tokens in
        </span>
        <span>
          <b>{fmtInt(tokensOut)}</b> out
        </span>
        <span>
          <b>{fmtInt(calls)}</b> model calls
        </span>
        {row && (
          <span>
            human <b className="amber">{mmss(humanSecs)}</b> · machine <b>{mmss(Math.max(0, nowTotal - humanSecs))}</b>
          </span>
        )}
      </div>
      {b.footnote && <div className="tvn-foot">{b.footnote}</div>}
    </section>
  );
}

function Lane({
  title,
  kind,
  parts,
  active,
}: {
  title: string;
  kind: "now" | "then";
  parts: { s: LaneKey; v: number; label: string }[];
  active: Stage | null;
}) {
  const shown = parts.filter((p) => p.v > 0);
  const total = shown.reduce((a, p) => a + p.v, 0) || 1;
  const MIN = 3; // a sliver is still visible; labels only appear when there is room
  const grows = shown.map((p) => Math.max((p.v / total) * 100, MIN));
  const growTotal = grows.reduce((a, g) => a + g, 0) || 1;
  return (
    <div className={`lane lane-${kind}`}>
      <div className="lane-title">{title}</div>
      <div className="lane-bar">
        {shown.map((p, i) => {
          const share = (grows[i] / growTotal) * 100;
          return (
            <div
              key={p.s}
              className={`lane-seg seg-${p.s} ${active === p.s ? "seg-active" : ""}`}
              style={{ flexGrow: grows[i] }}
              title={`${kind === "then" ? LANE_LABEL[p.s] : STAGE_LABEL[p.s as Stage]} ${p.label}`}
            >
              {share >= 11 && <span className="lane-seg-label">{kind === "then" ? LANE_LABEL[p.s] : STAGE_LABEL[p.s as Stage]}</span>}
              {share >= 7 && <span className="lane-seg-val">{p.label}</span>}
            </div>
          );
        })}
      </div>
    </div>
  );
}
