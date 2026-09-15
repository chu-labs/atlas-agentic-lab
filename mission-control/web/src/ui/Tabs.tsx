export function Tabs<T extends string>({ items, value, onChange, size = "sm" }: { items: { id: T; label: string; count?: number | string }[]; value: T; onChange: (v: T) => void; size?: "sm" | "md" }) {
  return (
    <div className={`seg seg-${size}`} role="tablist">
      {items.map((it) => (
        <button key={it.id} role="tab" aria-selected={value === it.id} className={`seg-btn ${value === it.id ? "on" : ""}`} onClick={() => onChange(it.id)}>
          {it.label}
          {it.count != null && it.count !== "" && <span className="seg-count">{it.count}</span>}
        </button>
      ))}
    </div>
  );
}
