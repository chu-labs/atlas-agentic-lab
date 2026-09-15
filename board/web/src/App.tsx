import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { Link, Outlet, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { ME, usePoll } from "./api";
import { NewIssueDrawer } from "./NewIssueDrawer";
import { daysBetween, shortDate } from "./time";
import { type Board, type Sprint, type User, STATUSES } from "./types";
import { Avatar } from "./ui/Avatar";
import { Popover } from "./ui/Popover";

export type View = "board" | "table" | "timeline";

type Shell = {
  users: User[];
  sprints: Sprint[];
  sprintParam: string; // "active" | id
  setSprint: (v: string) => void;
  view: View;
  setView: (v: View) => void;
  q: string;
  setQ: (q: string) => void;
  board: Board | null;
  stale: boolean;
  openNew: () => void;
};

const ShellCtx = createContext<Shell | null>(null);
export const useShell = () => useContext(ShellCtx)!;

export default function App() {
  const [params, setParams] = useSearchParams();
  const nav = useNavigate();
  const loc = useLocation();
  const sprintParam = params.get("sprint") ?? "active";
  const view = (params.get("view") as View) ?? "board";
  const [q, setQ] = useState(params.get("q") ?? "");
  const [newOpen, setNewOpen] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);

  const { data: users } = usePoll<User[]>("/api/users", 10_000);
  const { data: sprints } = usePoll<Sprint[]>("/api/sprints", 10_000);
  const { data: board, stale } = usePoll<Board>(`/api/board?sprint=${encodeURIComponent(sprintParam)}`, 2000);

  const setParam = useCallback(
    (k: string, v: string | null) => {
      const next = new URLSearchParams(params);
      if (v == null || v === "" || (k === "sprint" && v === "active") || (k === "view" && v === "board")) next.delete(k);
      else next.set(k, v);
      setParams(next, { replace: true });
    },
    [params, setParams],
  );

  // Search is debounced into the URL so the board page can read it.
  useEffect(() => {
    const id = setTimeout(() => setParam("q", q), 150);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);

  // Keyboard: "/" focuses search, "n" new issue, Esc clears search / closes.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement;
      const typing = el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable;
      if (e.key === "/" && !typing) {
        e.preventDefault();
        if (loc.pathname !== "/") nav("/");
        searchRef.current?.focus();
        searchRef.current?.select();
      } else if (e.key === "n" && !typing && !e.metaKey && !e.ctrlKey) {
        e.preventDefault();
        setNewOpen(true);
      } else if (e.key === "Escape" && el === searchRef.current) {
        setQ("");
        searchRef.current?.blur();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [loc.pathname, nav]);

  const shell = useMemo<Shell>(
    () => ({
      users: users ?? [],
      sprints: sprints ?? [],
      sprintParam,
      setSprint: (v) => setParam("sprint", v),
      view,
      setView: (v) => setParam("view", v),
      q,
      setQ,
      board,
      stale,
      openNew: () => setNewOpen(true),
    }),
    [users, sprints, sprintParam, view, q, board, stale, setParam],
  );

  const me = users?.find((u) => u.handle === ME) ?? null;
  const sprint = board?.sprint ?? null;

  return (
    <ShellCtx.Provider value={shell}>
      <header className="topbar">
        <Link to="/" className="brand">
          <span className="brand-mark">A</span>
          <span className="brand-name">ATLAS Board</span>
        </Link>
        <span className="chip project-chip mono">{board?.project.key ?? "ATLAS"}</span>
        <SprintSelector sprints={sprints ?? []} current={sprint} value={sprintParam} onChange={shell.setSprint} board={board} />
        <div className="search">
          <span className="search-icon">⌕</span>
          <input
            ref={searchRef}
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              if (loc.pathname !== "/") nav("/");
            }}
            placeholder="Search issues…"
            aria-label="Search issues"
          />
          <kbd>/</kbd>
        </div>
        <div className="view-toggle" role="tablist">
          {(["board", "table", "timeline"] as View[]).map((v) => (
            <Link key={v} to={`/?${withParam(params, "view", v === "board" ? null : v)}`} role="tab" aria-selected={view === v && loc.pathname === "/"} className={view === v && loc.pathname === "/" ? "on" : ""}>
              {v[0].toUpperCase() + v.slice(1)}
            </Link>
          ))}
        </div>
        <div className="topbar-right">
          <StatusCounts board={board} />
          <span className={`live ${stale ? "live-stale" : ""}`}>
            <i />
            {stale ? "reconnecting" : "live"}
          </span>
          <button type="button" className="btn btn-primary" onClick={() => setNewOpen(true)}>
            + New issue <kbd>n</kbd>
          </button>
          <span className="me" title={me ? `${me.display_name} · ${me.remit}` : ME}>
            <Avatar user={me} size={32} />
          </span>
        </div>
      </header>
      <Outlet />
      <NewIssueDrawer open={newOpen} onClose={() => setNewOpen(false)} />
    </ShellCtx.Provider>
  );
}

function withParam(params: URLSearchParams, k: string, v: string | null): string {
  const next = new URLSearchParams(params);
  if (v == null) next.delete(k);
  else next.set(k, v);
  return next.toString();
}

function StatusCounts({ board }: { board: Board | null }) {
  return (
    <div className="status-counts" aria-label="issues per status">
      {STATUSES.map((s) => (
        <span key={s} className={`count count-${s.toLowerCase().replace(/\s+/g, "-")}`} title={s}>
          <i />
          <b className="mono">{board?.counts[s] ?? "–"}</b>
        </span>
      ))}
    </div>
  );
}

function SprintSelector({ sprints, current, value, onChange, board }: { sprints: Sprint[]; current: Sprint | null; value: string; onChange: (v: string) => void; board: Board | null }) {
  const ref = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);
  const today = new Date().toISOString().slice(0, 10);
  const daysLeft = current ? daysBetween(today, current.ends_on) : null;
  const pts = useMemo(() => {
    if (!board) return null;
    const all = board.columns.flatMap((c) => c.issues);
    const total = all.reduce((a, i) => a + (i.story_points ?? 0), 0);
    const done = all.filter((i) => i.status === "Done").reduce((a, i) => a + (i.story_points ?? 0), 0);
    return { total, done };
  }, [board]);
  const items = [
    ...sprints.map((s) => ({
      key: String(s.id),
      label: s.name,
      group: s.state,
      active: current?.id === s.id,
      meta: <span className="mono">{shortDate(s.starts_on)}–{shortDate(s.ends_on)}</span>,
      onPick: () => onChange(s.state === "active" ? "active" : String(s.id)),
    })),
    { key: "none", label: "No sprint (unplanned)", group: "other", active: value === "none", onPick: () => onChange("none") },
  ];
  return (
    <>
      <button ref={ref} type="button" className={`sprint-btn ${current?.state ?? ""}`} onClick={() => setOpen((o) => !o)} aria-haspopup="menu">
        <span className="sprint-name">{current ? current.name : value === "none" ? "Unplanned" : "Sprint"}</span>
        {current && (
          <span className="sprint-meta mono">
            {shortDate(current.starts_on)}–{shortDate(current.ends_on)}
            {current.state === "active" && daysLeft != null && <span className={`sprint-days ${daysLeft <= 2 ? "warn" : ""}`}> · {daysLeft < 0 ? "ended" : `${daysLeft}d left`}</span>}
            {current.state !== "active" && <span className="sprint-days"> · {current.state}</span>}
          </span>
        )}
        {pts && (
          <span className="sprint-pts mono" title="story points done / total">
            {pts.done}/{pts.total} pts
          </span>
        )}
        <span className="caret">▾</span>
      </button>
      {open && ref.current && <Popover anchor={ref.current} items={items} onClose={() => setOpen(false)} width={300} />}
    </>
  );
}
