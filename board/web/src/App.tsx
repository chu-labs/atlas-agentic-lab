import { Link, Outlet } from "react-router-dom";
import { usePoll } from "./api";
import { STATUSES, type Board } from "./types";

export default function App() {
  const { data, stale } = usePoll<Board>("/api/board?sprint=active", 2000);
  return (
    <>
      <header className="topbar">
        <Link to="/" className="brand">
          <span className="brand-mark">A</span>
          <span className="brand-name">ATLAS</span>
          <span className="brand-sub">board</span>
        </Link>
        <nav className="status-counts" aria-label="issues per status">
          {STATUSES.map((s) => (
            <span key={s} className={`count count-${slug(s)}`}>
              <b>{data?.counts[s] ?? "–"}</b>
              <span>{s}</span>
            </span>
          ))}
        </nav>
        <span className={`live ${stale ? "live-stale" : ""}`} title={stale ? "reconnecting" : "live"}>
          <i />
          {stale ? "reconnecting" : "live"}
        </span>
      </header>
      <Outlet />
    </>
  );
}

export function slug(s: string): string {
  return s.toLowerCase().replace(/\s+/g, "-");
}
