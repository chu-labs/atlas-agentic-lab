import { LineSpark, Sparkline } from "./Sparkline";

export function KpiTile({
  label,
  value,
  unit,
  delta,
  sub,
  spark,
  sparkKind = "bars",
  tone = "muted",
  onClick,
}: {
  label: string;
  value: React.ReactNode;
  unit?: string;
  delta?: React.ReactNode;
  sub?: React.ReactNode;
  spark?: number[];
  sparkKind?: "bars" | "line";
  tone?: "accent" | "danger" | "warning" | "success" | "info" | "muted";
  onClick?: () => void;
}) {
  return (
    <div className={`kpi2 kpi2-${tone} ${onClick ? "clickable" : ""}`} onClick={onClick}>
      <div className="kpi2-label">{label}</div>
      <div className="kpi2-row">
        <span className="kpi2-value">
          {value}
          {unit && <span className="kpi2-unit">{unit}</span>}
        </span>
        {spark && (sparkKind === "line" ? <LineSpark values={spark} tone={tone} width={110} height={28} /> : <Sparkline values={spark} tone={tone} width={110} height={28} />)}
      </div>
      <div className="kpi2-foot">
        {delta && <span className="kpi2-delta">{delta}</span>}
        {sub && <span className="kpi2-sub">{sub}</span>}
      </div>
    </div>
  );
}
