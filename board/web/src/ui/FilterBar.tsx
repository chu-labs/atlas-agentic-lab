import { useRef, useState, type ReactNode } from "react";
import { Popover, type PopoverItem } from "./Popover";

export type FilterOption = { value: string; label: ReactNode; icon?: ReactNode; group?: string };

export type FilterDef = {
  key: string;
  label: string;
  options: FilterOption[];
};

export type Filters = Record<string, string[]>;

/** A row of dropdown filters plus chips for every active value. */
export function FilterBar({ defs, value, onChange, children }: { defs: FilterDef[]; value: Filters; onChange: (f: Filters) => void; children?: ReactNode }) {
  const active = defs.flatMap((d) => (value[d.key] ?? []).map((v) => ({ def: d, v })));
  const toggle = (key: string, v: string) => {
    const cur = value[key] ?? [];
    const next = cur.includes(v) ? cur.filter((x) => x !== v) : [...cur, v];
    onChange({ ...value, [key]: next });
  };
  return (
    <div className="filterbar">
      {defs.map((d) => (
        <FilterButton key={d.key} def={d} selected={value[d.key] ?? []} onToggle={(v) => toggle(d.key, v)} />
      ))}
      {children}
      {active.length > 0 && (
        <div className="filter-chips">
          {active.map(({ def, v }) => {
            const opt = def.options.find((o) => o.value === v);
            return (
              <button key={`${def.key}:${v}`} type="button" className="chip filter-chip" onClick={() => toggle(def.key, v)} title="Remove filter">
                <span className="filter-chip-key">{def.label}</span>
                {opt?.icon}
                <span>{opt?.label ?? v}</span>
                <span className="filter-chip-x">✕</span>
              </button>
            );
          })}
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => onChange({})}>
            Clear
          </button>
        </div>
      )}
    </div>
  );
}

function FilterButton({ def, selected, onToggle }: { def: FilterDef; selected: string[]; onToggle: (v: string) => void }) {
  const ref = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);
  const items: PopoverItem[] = def.options.map((o) => ({
    key: o.value,
    label: o.label,
    icon: o.icon,
    group: o.group,
    active: selected.includes(o.value),
    meta: selected.includes(o.value) ? "✓" : undefined,
    onPick: () => onToggle(o.value),
  }));
  return (
    <>
      <button ref={ref} type="button" className={`btn btn-sm filter-btn ${selected.length ? "on" : ""}`} onClick={() => setOpen((o) => !o)}>
        {def.label}
        {selected.length > 0 && <span className="filter-count">{selected.length}</span>}
        <span className="caret">▾</span>
      </button>
      {open && ref.current && <Popover anchor={ref.current} items={items} onClose={() => setOpen(false)} />}
    </>
  );
}
