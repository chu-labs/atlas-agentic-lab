export type View = "mission" | "board" | "cicd" | "dora";
export const VIEWS: { id: View; label: string; key: string }[] = [
  { id: "mission", label: "Mission Control", key: "1" },
  { id: "board", label: "Board", key: "2" },
  { id: "cicd", label: "CI/CD", key: "3" },
  { id: "dora", label: "DORA", key: "4" },
];

export function Nav({ view, onView, badges }: { view: View; onView: (v: View) => void; badges: Partial<Record<View, string | number>> }) {
  return (
    <nav className="tabs" aria-label="views">
      {VIEWS.map((v) => (
        <button key={v.id} className={`tab ${view === v.id ? "on" : ""}`} onClick={() => onView(v.id)}>
          <span className="tab-key">{v.key}</span>
          {v.label}
          {badges[v.id] != null && badges[v.id] !== "" && <span className="tab-badge">{badges[v.id]}</span>}
        </button>
      ))}
    </nav>
  );
}
