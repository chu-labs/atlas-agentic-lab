import type { MissionState, PipelineRow } from "./types";
import { fmtDays, fmtInt, fmtUSD, mmss } from "./time";

export function Telemetry({
  state,
  stateAt,
  now,
  activeRow,
}: {
  state: MissionState;
  stateAt: number;
  now: number;
  activeRow: PipelineRow | null;
}) {
  const t = state.telemetry;
  const b = state.baselines;
  const drift = (now - stateAt) / 1000;
  const toPr = t.error_to_pr_seconds ?? null;
  const toClosed =
    t.error_to_closed_seconds == null ? null : t.closed || activeRow?.escalated ? t.error_to_closed_seconds : t.error_to_closed_seconds + drift;
  const humanSeconds = t.usd / (b.human_hourly_rate_aud / 3600);
  return (
    <section className="telemetry">
      <h2 className="panel-title">
        Telemetry <span className="panel-sub">{t.ticket ?? "no active ticket"}</span>
      </h2>
      <div className="stats">
        <Stat label="tokens in" value={fmtInt(t.tokens_in)} />
        <Stat label="tokens out" value={fmtInt(t.tokens_out)} />
        <Stat label="model calls" value={fmtInt(t.model_calls)} />
        <Stat label="cost" value={fmtUSD(t.usd)} accent />
        <Stat label="error → PR" value={mmss(toPr)} big />
        <Stat label={t.closed ? "error → closed" : "error → now"} value={mmss(toClosed)} big />
      </div>
      <div className="compare">
        <div>
          Same fix by a human team: <b>~{fmtDays(b.human_days_error_to_pr)}</b> to a PR, <b>~{fmtDays(b.human_days_error_to_closed)}</b> to closed
        </div>
        <div>
          Agent spend so far buys <b>{mmss(humanSeconds)}</b> of one engineer at ${b.human_hourly_rate_aud}/h
        </div>
      </div>
    </section>
  );
}

function Stat({ label, value, big, accent }: { label: string; value: string; big?: boolean; accent?: boolean }) {
  return (
    <div className={`stat ${big ? "stat-big" : ""} ${accent ? "stat-accent" : ""}`}>
      <span className="stat-value">{value}</span>
      <span className="stat-label">{label}</span>
    </div>
  );
}
