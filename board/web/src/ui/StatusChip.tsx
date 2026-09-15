import { slug, TYPE_COLOR, TYPE_GLYPH, type IssueType, type Priority, type Status } from "../types";

export function StatusChip({ status, size = "md" }: { status: Status | string; size?: "sm" | "md" }) {
  return <span className={`chip status-chip status-${slug(status)} chip-${size}`}>{status}</span>;
}

const PRIO_GLYPH: Record<Priority, string> = { Highest: "⇈", High: "↑", Medium: "=", Low: "↓", Lowest: "⇊" };

export function PriorityChip({ priority, compact = false }: { priority: Priority; compact?: boolean }) {
  return (
    <span className={`chip prio-chip prio-${priority.toLowerCase()}`} title={priority}>
      <span className="prio-glyph">{PRIO_GLYPH[priority]}</span>
      {!compact && priority}
    </span>
  );
}

export function TypeGlyph({ type, label = false }: { type: IssueType; label?: boolean }) {
  return (
    <span className="type-glyph" style={{ color: TYPE_COLOR[type] }} title={type}>
      <span className="type-mark">{TYPE_GLYPH[type]}</span>
      {label && <span className="type-label">{type}</span>}
    </span>
  );
}

export function LabelChip({ label }: { label: string }) {
  return <span className="chip label-chip">{label}</span>;
}

export function Points({ value }: { value: number | null }) {
  if (value == null) return <span className="pts pts-empty">–</span>;
  return <span className="pts">{value}</span>;
}
