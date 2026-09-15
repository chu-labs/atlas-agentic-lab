export interface FilterDef {
  key: string;
  label: string;
  options: { value: string; label: string }[];
}

export function FilterBar({
  filters,
  values,
  onChange,
  text,
  onText,
  placeholder = "filter…",
  right,
}: {
  filters: FilterDef[];
  values: Record<string, string>;
  onChange: (key: string, value: string) => void;
  text?: string;
  onText?: (v: string) => void;
  placeholder?: string;
  right?: React.ReactNode;
}) {
  return (
    <div className="filterbar">
      {filters.map((f) => (
        <label key={f.key} className="fb-select">
          <span>{f.label}</span>
          <select value={values[f.key] ?? ""} onChange={(e) => onChange(f.key, e.target.value)}>
            <option value="">all</option>
            {f.options.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
      ))}
      {onText && <input className="fb-text" placeholder={placeholder} value={text ?? ""} onChange={(e) => onText(e.target.value)} />}
      {right && <span className="fb-right">{right}</span>}
    </div>
  );
}
