import { useCallback, useEffect, useState } from "react";
import { Drawer } from "./Drawer";
import { Fleet } from "./Fleet";
import { Pipeline } from "./Pipeline";
import { Queues } from "./Queues";
import { SignalStrip } from "./Signal";
import { ThenVsNow } from "./ThenVsNow";
import { Timeline } from "./Timeline";
import { TopBar } from "./TopBar";
import { STAGES, type Selection, type Stage } from "./types";
import { useClock, useMission } from "./useMission";

/** #ATLAS-142/pr opens the drawer on load; #compare opens the comparison. Handy for rehearsal. */
function selectionFromHash(): { sel: Selection | null; compare: boolean } {
  const h = decodeURIComponent(location.hash.replace(/^#/, ""));
  if (!h) return { sel: null, compare: false };
  if (h === "compare") return { sel: null, compare: true };
  if (h.startsWith("agent/")) return { sel: { kind: "agent", handle: h.slice(6) }, compare: false };
  const [ticket, stage] = h.split("/");
  if (ticket && stage && (STAGES as readonly string[]).includes(stage)) return { sel: { kind: "stage", ticket, stage: stage as Stage }, compare: false };
  return { sel: null, compare: false };
}

export default function App() {
  const mission = useMission();
  const now = useClock(1000);
  const { state, stateAt, events } = mission;
  const [selection, setSelection] = useState<Selection | null>(() => selectionFromHash().sel);
  const [compare, setCompare] = useState(() => selectionFromHash().compare);
  const close = useCallback(() => setSelection(null), []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setCompare(false);
      if ((e.key === "c" || e.key === "C") && !(e.target instanceof HTMLInputElement)) setCompare((v) => !v);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (!state) {
    return (
      <div className="app">
        <TopBar mission={mission} now={now} compare={compare} onCompare={() => setCompare((v) => !v)} />
        <div className="boot">Connecting to Mission Control…</div>
      </div>
    );
  }

  const active = state.pipeline.find((r) => r.ticket === state.active_ticket) ?? state.pipeline[0] ?? null;
  return (
    <div className="app">
      <TopBar mission={mission} now={now} compare={compare} onCompare={() => setCompare((v) => !v)} />
      <SignalStrip signal={state.signal} />
      <Pipeline state={state} stateAt={stateAt} now={now} onSelect={setSelection} selected={selection} />
      <div className="lower">
        <Fleet fleet={state.fleet} onSelect={setSelection} selected={selection} />
        <Timeline events={events} activeRow={active} rows={state.pipeline} onSelect={setSelection} />
        <aside className="side">
          <Queues state={state} />
          <ThenVsNow state={state} stateAt={stateAt} now={now} row={active} />
        </aside>
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
      </div>
      <Drawer selection={selection} state={state} events={events} now={now} onClose={close} onSelect={setSelection} />
    </div>
  );
}
