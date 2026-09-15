/** Inline-SVG bars and sparklines. No chart library. */

export type Segment = { label: string; value: number; color: string };

/** One horizontal stacked bar with a legend. */
export function MiniBar({ segments, total, height = 10, legend = true }: { segments: Segment[]; total?: number; height?: number; legend?: boolean }) {
  const sum = total ?? segments.reduce((a, s) => a + s.value, 0);
  let x = 0;
  return (
    <div className="minibar">
      <svg className="minibar-svg" viewBox="0 0 100 10" preserveAspectRatio="none" style={{ height }} role="img" aria-label={segments.map((s) => `${s.label} ${s.value}`).join(", ")}>
        <rect x={0} y={0} width={100} height={10} fill="var(--surface-2)" />
        {sum > 0 &&
          segments.map((s) => {
            const w = (s.value / sum) * 100;
            const el = <rect key={s.label} x={x} y={0} width={w} height={10} fill={s.color} />;
            x += w;
            return el;
          })}
      </svg>
      {legend && (
        <div className="minibar-legend">
          {segments.map((s) => (
            <span key={s.label} className="legend-item">
              <i style={{ background: s.color }} />
              <span className="legend-label">{s.label}</span>
              <b className="mono">{s.value}</b>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

/** Small horizontal bars, one per row, for category counts. */
export function BarRows({ rows, color = "var(--accent)" }: { rows: { label: React.ReactNode; value: number; color?: string }[]; color?: string }) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  return (
    <div className="barrows">
      {rows.map((r, i) => (
        <div key={i} className="barrow">
          <span className="barrow-label">{r.label}</span>
          <svg className="barrow-svg" viewBox="0 0 100 8" preserveAspectRatio="none">
            <rect x={0} y={0} width={100} height={8} fill="var(--surface-2)" />
            <rect x={0} y={0} width={(r.value / max) * 100} height={8} fill={r.color ?? color} />
          </svg>
          <b className="barrow-value mono">{r.value}</b>
        </div>
      ))}
    </div>
  );
}

/** Tiny line chart. */
export function Sparkline({ values, width = 120, height = 28, color = "var(--accent)" }: { values: number[]; width?: number; height?: number; color?: string }) {
  if (values.length < 2) return <svg width={width} height={height} />;
  const max = Math.max(...values, 1);
  const min = Math.min(...values, 0);
  const span = max - min || 1;
  const pts = values.map((v, i) => [(i / (values.length - 1)) * (width - 2) + 1, height - 1 - ((v - min) / span) * (height - 2)]);
  const d = pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");
  const last = pts[pts.length - 1];
  return (
    <svg className="sparkline" width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
      <path d={`${d} L${last[0]},${height} L1,${height} Z`} fill={color} opacity={0.12} />
      <path d={d} fill="none" stroke={color} strokeWidth={1.5} />
      <circle cx={last[0]} cy={last[1]} r={2} fill={color} />
    </svg>
  );
}
