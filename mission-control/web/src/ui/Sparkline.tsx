/** Inline SVG sparkline (bars) — no charting library. Values left→right oldest→newest. */
export function Sparkline({ values, width = 120, height = 26, tone = "accent", className = "" }: { values: number[]; width?: number; height?: number; tone?: "accent" | "danger" | "warning" | "success" | "info" | "muted"; className?: string }) {
  const n = Math.max(1, values.length);
  const max = Math.max(1, ...values);
  const step = width / n;
  return (
    <svg className={`spark spark-${tone} ${className}`} viewBox={`0 0 ${width} ${height}`} width={width} height={height} preserveAspectRatio="none" aria-hidden="true">
      {values.map((v, i) => {
        const h = v <= 0 ? 1 : Math.max(2, (v / max) * (height - 2));
        return <rect key={i} x={i * step + 0.5} y={height - h} width={Math.max(1.5, step - 1)} height={h} rx={1} className={v > 0 ? "on" : "off"} />;
      })}
    </svg>
  );
}

/** Inline SVG line sparkline for continuous series (req/min, p95). */
export function LineSpark({ values, width = 120, height = 26, tone = "accent" }: { values: number[]; width?: number; height?: number; tone?: "accent" | "danger" | "warning" | "success" | "info" | "muted" }) {
  if (values.length < 2) return <svg className={`spark spark-${tone}`} width={width} height={height} aria-hidden="true" />;
  const max = Math.max(1e-9, ...values);
  const min = Math.min(...values);
  const span = Math.max(1e-9, max - min);
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * width},${height - 2 - ((v - min) / span) * (height - 4)}`).join(" ");
  return (
    <svg className={`spark spark-${tone}`} viewBox={`0 0 ${width} ${height}`} width={width} height={height} preserveAspectRatio="none" aria-hidden="true">
      <polyline points={pts} fill="none" strokeWidth={1.6} className="line" />
    </svg>
  );
}

/** Horizontal mini bar chart: label · bar · value. */
export function MiniBar({ rows, max, format = (v: number) => String(v), tone = "danger" }: { rows: { label: string; value: number; hint?: string; onClick?: () => void }[]; max?: number; format?: (v: number) => string; tone?: "accent" | "danger" | "warning" | "success" | "info" }) {
  const m = Math.max(1, max ?? Math.max(0, ...rows.map((r) => r.value)));
  return (
    <div className={`minibar minibar-${tone}`}>
      {rows.map((r, i) => (
        <div key={i} className={`minibar-row ${r.onClick ? "clickable" : ""}`} onClick={r.onClick} title={r.hint ?? r.label}>
          <span className="minibar-label">{r.label}</span>
          <span className="minibar-track">
            <span className="minibar-fill" style={{ width: `${Math.max(1.5, (r.value / m) * 100)}%` }} />
          </span>
          <span className="minibar-value">{format(r.value)}</span>
        </div>
      ))}
      {rows.length === 0 && <div className="empty-line">nothing in the window</div>}
    </div>
  );
}

/** A single inline bar (job durations etc.). */
export function InlineBar({ value, max, tone = "accent", label }: { value: number; max: number; tone?: string; label?: string }) {
  return (
    <span className={`inlinebar tone-${tone}`} title={label}>
      <span className="inlinebar-fill" style={{ width: `${Math.max(2, (value / Math.max(1, max)) * 100)}%` }} />
    </span>
  );
}
