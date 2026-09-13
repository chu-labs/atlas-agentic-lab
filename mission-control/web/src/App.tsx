import { useCallback, useEffect, useRef, useState } from "react";
import { Board } from "./Board";
import { CiCd } from "./CiCd";
import { Dora } from "./Dora";
import { Drawer } from "./Drawer";
import { Fleet } from "./Fleet";
import { Footer } from "./Footer";
import { Nav, VIEWS, type View } from "./Nav";
import { Pipeline } from "./Pipeline";
import { Queues } from "./Queues";
import { SignalStrip } from "./Signal";
import { ThenVsNow } from "./ThenVsNow";
import { Timeline } from "./Timeline";
import { TopBar } from "./TopBar";
import { STAGES, type Selection, type Stage } from "./types";
import { useClock, useMission } from "./useMission";

/** #board / #cicd / #dora pick a tab; #ATLAS-142/pr opens the drawer; #agent/forge, #issue/ATLAS-142; #compare. */
function fromHash(): { view: View; sel: Selection | null; compare: boolean } {
  const h = decodeURIComponent(location.hash.replace(/^#/, ""));
  const base = { view: "mission" as View, sel: null, compare: false };
  if (!h) return base;
  if (h === "compare") return { ...base, compare: true };
  if ((VIEWS.map((v) => v.id) as string[]).includes(h)) return { ...base, view: h as View };
  if (h.startsWith("agent/")) return { ...base, sel: { kind: "agent", handle: h.slice(6) } };
  if (h.startsWith("issue/")) return { ...base, view: "board", sel: { kind: "issue", key: h.slice(6) } };
  const [ticket, stage] = h.split("/");
  if (ticket && stage && (STAGES as readonly string[]).includes(stage)) return { ...base, sel: { kind: "stage", ticket, stage: stage as Stage } };
  return base;
}

export default function App() {
  const mission = useMission();
  const now = useClock(1000);
  const { state, stateAt, events } = mission;
  const initial = useRef(fromHash());
  const [view, setView] = useState<View>(initial.current.view);
  const [selection, setSelection] = useState<Selection | null>(initial.current.sel);
  const [compare, setCompare] = useState(initial.current.compare);
  const [toastMsg, setToastMsg] = useState<string | null>(null);
  const toastTimer = useRef<number | null>(null);
  const close = useCallback(() => setSelection(null), []);
  const toast = useCallback((msg: string) => {
    setToastMsg(msg);
    if (toastTimer.current) window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToastMsg(null), 6000);
  }, []);
  const go = useCallback((v: View) => {
    setView(v);
    history.replaceState(null, "", v === "mission" ? "#" : `#${v}`);
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement || e.target instanceof HTMLSelectElement) return;
      if (e.key === "Escape") setCompare(false);
      if (e.key === "c" || e.key === "C") setCompare((v) => !v);
      const tab = VIEWS.find((v) => v.key === e.key);
      if (tab) go(tab.id);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [go]);

  if (!state) {
    return (
      <div className="app">
        <TopBar mission={mission} now={now} compare={compare} onCompare={() => setCompare((v) => !v)} />
        <div className="boot">Connecting to Mission Control…</div>
      </div>
    );
  }

  const active = state.pipeline.find((r) => r.ticket === state.active_ticket) ?? state.pipeline.find((r) => !r.observing) ?? null;
  const badges: Partial<Record<View, string | number>> = {
    mission: state.gate.awaiting ? `${state.gate.awaiting} waiting` : "",
    board: "",
    cicd: "",
    dora: "",
  };

  return (
    <div className={`app view-${view}`}>
      <TopBar mission={mission} now={now} compare={compare} onCompare={() => setCompare((v) => !v)} />
      <Nav view={view} onView={go} badges={badges} />
      {view === "mission" && (
        <>
          <SignalStrip signal={state.signal} />
          <Pipeline state={state} stateAt={stateAt} now={now} onSelect={setSelection} selected={selection} />
          <div className="lower">
            <Fleet fleet={state.fleet} onSelect={setSelection} selected={selection} />
            <Timeline events={events} activeRow={active} rows={state.pipeline} onSelect={setSelection} />
            <aside className="side">
              <Queues state={state} />
              <ThenVsNow state={state} stateAt={stateAt} now={now} row={active} />
            </aside>
          </div>
        </>
      )}
      {view === "board" && (
        <div className="page">
          <Board fleet={state.fleet} onSelect={setSelection} selected={selection} toast={toast} />
        </div>
      )}
      {view === "cicd" && (
        <div className="page">
          <CiCd toast={toast} humanConfigured={!!state.human?.configured} />
        </div>
      )}
      {view === "dora" && (
        <div className="page">
          <Dora />
        </div>
      )}
      <Footer lastEventId={state.last_event_id} eventCount={events.length} />
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
      {toastMsg && (
        <div className="toast" role="status">
          {toastMsg}
        </div>
      )}
      <Drawer selection={selection} state={state} events={events} now={now} onClose={close} onSelect={setSelection} />
    </div>
  );
}
