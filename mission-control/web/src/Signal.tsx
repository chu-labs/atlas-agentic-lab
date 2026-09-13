import type { Signal } from "./types";
import { hms } from "./time";
import { useTween } from "./useMission";

/** The production signal strip: error rate over the last 10 minutes, untracked errors, and the latest one. */
export function SignalStrip({ signal }: { signal: Signal }) {
  const perMin = useTween(signal.per_minute);
  const untracked = useTween(signal.untracked_count);
  const total = useTween(signal.total_10m);
  const latest = signal.latest;
  const hot = signal.per_minute > 0;
  return (
    <section className={`signal ${hot ? "signal-hot" : ""}`}>
      <span className="signal-label">Production signal</span>
      <Sparkline values={signal.rate} />
      <span className="signal-stat">
        <b>{Math.round(perMin)}</b> <span>/ min</span>
      </span>
      <span className="signal-stat">
        <b>{Math.round(total)}</b> <span>in 10 min</span>
      </span>
      <span className={`signal-stat ${signal.untracked_count > 0 ? "signal-untracked" : ""}`}>
        <b>{Math.round(untracked)}</b> <span>untracked</span>
      </span>
      <span className="signal-latest">
        {latest ? (
          <>
            <span className="signal-sig">{latest.signature ?? latest.error_type ?? "error"}</span>
            <span className="signal-msg">{latest.message ?? ""}</span>
            <span className="signal-when">{hms(latest.last_ts)}</span>
          </>
        ) : (
          <span className="muted">{signal.total_10m > 0 ? "every recent error is on a ticket" : "no errors in the last 10 minutes"}</span>
        )}
      </span>
      {signal.triage_since && <span className="signal-triage">Scout triaging</span>}
    </section>
  );
}

function Sparkline({ values }: { values: number[] }) {
  const w = 220;
  const h = 34;
  const max = Math.max(1, ...values);
  const n = Math.max(1, values.length);
  const step = w / n;
  const bars = values.map((v, i) => {
    const bh = v === 0 ? 1.5 : Math.max(3, (v / max) * (h - 4));
    return <rect key={i} x={i * step + 1} y={h - bh} width={Math.max(2, step - 2)} height={bh} rx={1.5} className={v > 0 ? "spark-on" : "spark-off"} />;
  });
  return (
    <svg className="spark" viewBox={`0 0 ${w} ${h}`} width={w} height={h} aria-label="errors per 30 seconds, last 10 minutes">
      {bars}
    </svg>
  );
}
