export type View = "ops" | "eng" | "board" | "cicd" | "dora";
export const VIEWS: { id: View; label: string; key: string; hint: string }[] = [
  { id: "ops", label: "Operations", key: "1", hint: "what production is doing" },
  { id: "eng", label: "Engineering", key: "2", hint: "what the dev agents are doing" },
  { id: "board", label: "Board", key: "3", hint: "assign work" },
  { id: "cicd", label: "CI/CD", key: "4", hint: "runs and deploy gates" },
  { id: "dora", label: "DORA", key: "5", hint: "four keys" },
];

export function Nav({ view, onView, badges }: { view: View; onView: (v: View) => void; badges: Partial<Record<View, string | number>> }) {
  return (
    <nav className="tabs" aria-label="views">
      {VIEWS.map((v) => (
        <button key={v.id} className={`tab ${view === v.id ? "on" : ""}`} onClick={() => onView(v.id)} title={v.hint}>
          <span className="tab-key">{v.key}</span>
          {v.label}
          {badges[v.id] != null && badges[v.id] !== "" && <span className="tab-badge">{badges[v.id]}</span>}
        </button>
      ))}
    </nav>
  );
}
