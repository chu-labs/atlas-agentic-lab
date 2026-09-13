import type { MissionState } from "./types";
import { fmtInt } from "./time";

export function Queues({ state }: { state: MissionState }) {
  const prodErrors = state.queues["prod-errors"] ?? 0;
  const work = state.queues["forge"] ?? 0;
  const awaiting = state.pipeline.filter((r) => !r.closed && !r.escalated && r.stage === "human_gate").length + (state.gate.waiting && !state.pipeline.some((r) => r.stage === "human_gate") ? 1 : 0);
  return (
    <section className="queues">
      <h2 className="panel-title">Queues</h2>
      <div className="counters">
        <div className={`counter counter-errors ${prodErrors > 0 ? "hot" : ""}`}>
          <span className="counter-num">{fmtInt(prodErrors)}</span>
          <span className="counter-label">Production errors</span>
        </div>
        <div className={`counter counter-work ${work > 0 ? "hot" : ""}`}>
          <span className="counter-num">{fmtInt(work)}</span>
          <span className="counter-label">Work queue</span>
        </div>
        <div className={`counter counter-gate ${awaiting > 0 ? "hot" : ""}`}>
          <span className="counter-num">{fmtInt(awaiting)}</span>
          <span className="counter-label">PRs awaiting human</span>
        </div>
      </div>
    </section>
  );
}
