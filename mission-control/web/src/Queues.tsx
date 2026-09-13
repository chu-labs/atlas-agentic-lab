import type { MissionState } from "./types";
import { fmtInt } from "./time";
import { useTween } from "./useMission";

export function Queues({ state }: { state: MissionState }) {
  const prodErrors = state.queues["prod-errors"] ?? 0;
  const work = state.queues["forge"] ?? 0;
  const awaiting = state.gate.awaiting ?? 0; // server-derived: only tickets whose current stage is human_gate
  const a = useTween(prodErrors);
  const b = useTween(work);
  const c = useTween(awaiting);
  return (
    <section className="queues">
      <h2 className="panel-title">Queues</h2>
      <div className="counters">
        <div className={`counter counter-errors ${prodErrors > 0 ? "hot" : ""}`}>
          <span className="counter-num">{fmtInt(a)}</span>
          <span className="counter-label">Production errors</span>
        </div>
        <div className={`counter counter-work ${work > 0 ? "hot" : ""}`}>
          <span className="counter-num">{fmtInt(b)}</span>
          <span className="counter-label">Work queue</span>
        </div>
        <div className={`counter counter-gate ${awaiting > 0 ? "hot" : ""}`}>
          <span className="counter-num">{fmtInt(c)}</span>
          <span className="counter-label">PRs awaiting human</span>
        </div>
      </div>
    </section>
  );
}
