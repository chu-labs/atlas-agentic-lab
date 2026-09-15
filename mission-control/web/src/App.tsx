import { useCallback, useEffect, useRef, useState } from "react";
import { Board } from "./Board";
import { CiCd } from "./CiCd";
import { Dora } from "./Dora";
import { Drawer } from "./Drawer";
import { Engineering } from "./Engineering";
import { VIEWS, type View } from "./Nav";
import { Operations, type Health } from "./Ops";
import { Rail } from "./Rail";
import { ThenVsNow } from "./ThenVsNow";
import { TopBar } from "./TopBar";
import { STAGES, type Selection, type Stage } from "./types";
import { Toast } from "./ui";
import { useFetch } from "./useFetch";
import { useClock, useMission } from "./useMission";

interface SystemInfo {
  region: string;
  cluster: string;
  version: string;
  source: string;
  services: { name: string; tag: string | null; running: number | null; desired: number | null }[];
}

/** #ops / #eng / #board / #cicd / #dora pick a view; #ATLAS-142/pr, #agent/forge, #issue/ATLAS-142, #cluster/<sig>, #compare. */
function fromHash(): { view: View; sel: Selection | null; compare: boolean } {
  const h = decodeURIComponent(location.hash.replace(/^#/, ""));
  const base = { view: "ops" as View, sel: null, compare: false };
  if (!h) return base;
  if (h === "compare") return { ...base, compare: true, view: "eng" as View };
  if (h === "mission") return { ...base, view: "eng" as View };
  if ((VIEWS.map((v) => v.id) as string[]).includes(h)) return { ...base, view: h as View };
  if (h.startsWith("agent/")) return { ...base, view: "eng" as View, sel: { kind: "agent", handle: h.slice(6) } };
  if (h.startsWith("issue/")) return { ...base, view: "board", sel: { kind: "issue", key: h.slice(6) } };
  if (h.startsWith("cluster/")) return { ...base, sel: { kind: "cluster", signature: h.slice(8) } };
  const [ticket, stage] = h.split("/");
  if (ticket && stage && (STAGES as readonly string[]).includes(stage)) return { ...base, view: "eng" as View, sel: { kind: "stage", ticket, stage: stage as Stage } };
  return base;
}

const TICKET_KEY = /^[A-Z][A-Z0-9]*-\d+$/i;

export default function App() {
  const mission = useMission();
  const now = useClock(1000);
  const { state, stateAt, events } = mission;
  const initial = useRef(fromHash());
  const [view, setView] = useState<View>(initial.current.view);
  const [selection, setSelection] = useState<Selection | null>(initial.current.sel);
  const [compare, setCompare] = useState(initial.current.compare);
  const [query, setQuery] = useState("");
  const [toastMsg, setToastMsg] = useState<string | null>(null);
  const toastTimer = useRef<number | null>(null);
  const health = useFetch<Health>("/api/ops/health", 15000);
  const system = useFetch<SystemInfo>("/api/system", 60000);
  const close = useCallback(() => setSelection(null), []);
  const toast = useCallback((msg: string) => {
    setToastMsg(msg);
    if (toastTimer.current) window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToastMsg(null), 6000);
  }, []);
  const go = useCallback((v: View) => {
    setView(v);
    history.replaceState(null, "", `#${v}`);
  }, []);
  const submitQuery = useCallback(
    (q: string) => {
      const t = q.trim();
      if (TICKET_KEY.test(t)) setSelection({ kind: "issue", key: t.toUpperCase() });
    },
    [],
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement || e.target instanceof HTMLSelectElement;
      if (e.key === "/" && !typing) {
        e.preventDefault();
        document.getElementById("global-search")?.focus();
        return;
      }
      if (typing) return;
      if (e.key === "Escape") setCompare(false);
      if (e.key === "c" || e.key === "C") setCompare((v) => !v);
      const tab = VIEWS.find((v) => v.key === e.key);
      if (tab) go(tab.id);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [go]);

  const env = health.data ? { region: health.data.region, cluster: health.data.cluster, source: health.data.source } : system.data ? { region: system.data.region, cluster: system.data.cluster, source: system.data.source } : null;

  if (!state) {
    return (
      <div className="app">
        <TopBar mission={mission} now={now} compare={compare} onCompare={() => setCompare((v) => !v)} view={view} onView={go} badges={{}} query={query} onQuery={setQuery} onSubmitQuery={submitQuery} env={env} />
        <div className="boot">Connecting to Mission Control…</div>
      </div>
    );
  }

  const active = state.pipeline.find((r) => r.ticket === state.active_ticket) ?? state.pipeline.find((r) => !r.observing) ?? null;
  const openClusters = state.signal.untracked_signatures + (state.signal.by_kind?.infra?.count ? 1 : 0);
  const badges: Partial<Record<View, string | number>> = {
    ops: openClusters ? `${openClusters} live` : "",
    eng: state.gate.awaiting ? `${state.gate.awaiting} waiting` : state.pipeline.filter((r) => !r.closed && !r.observing).length || "",
    board: "",
    cicd: "",
    dora: "",
  };
  const foot = (
    <>
      <div>
        <code>{system.data?.cluster ?? "…"}</code> · {system.data?.region ?? ""}
      </div>
      {(system.data?.services ?? []).map((s) => (
        <div key={s.name}>
          {s.name} <code>{s.tag ?? "—"}</code>
          {s.running != null ? ` ${s.running}/${s.desired}` : ""}
        </div>
      ))}
      <div>
        events {events.length} · id <code>{state.last_event_id}</code> · mc {system.data?.version ?? ""}
      </div>
    </>
  );

  return (
    <div className={`app view-${view}`}>
      <TopBar mission={mission} now={now} compare={compare} onCompare={() => setCompare((v) => !v)} view={view} onView={go} badges={badges} query={query} onQuery={setQuery} onSubmitQuery={submitQuery} env={env} />
      <div className="shell">
        <Rail view={view} onView={go} counts={badges} fleet={state.fleet} onSelect={setSelection} selected={selection} foot={foot} />
        <main className="content">
          {view === "ops" && <Operations state={state} events={events} now={now} onSelect={setSelection} selected={selection} onGoEngineering={() => go("eng")} query={query} health={health.data} />}
          {view === "eng" && <Engineering state={state} stateAt={stateAt} events={events} now={now} onSelect={setSelection} selected={selection} toast={toast} query={query} />}
          {view === "board" && <Board fleet={state.fleet} onSelect={setSelection} selected={selection} toast={toast} query={query} />}
          {view === "cicd" && <CiCd toast={toast} humanConfigured={!!state.human?.configured} />}
          {view === "dora" && <Dora />}
        </main>
      </div>
      {compare && (
        <div className="compare-overlay" onClick={() => setCompare(false)}>
          <div className="compare-card" onClick={(e) => e.stopPropagation()}>
            <ThenVsNow state={state} stateAt={stateAt} now={now} row={active} size="large" />
            <button className="drawer-close compare-close" onClick={() => setCompare(false)} aria-label="close">
              ✕
            </button>
          </div>
        </div>
      )}
      <Toast message={toastMsg} />
      <Drawer selection={selection} state={state} events={events} now={now} onClose={close} onSelect={setSelection} />
    </div>
  );
}
