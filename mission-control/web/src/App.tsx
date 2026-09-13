import { Fleet } from "./Fleet";
import { Pipeline } from "./Pipeline";
import { Queues } from "./Queues";
import { Telemetry } from "./Telemetry";
import { Timeline } from "./Timeline";
import { TopBar } from "./TopBar";
import { useClock, useMission } from "./useMission";

export default function App() {
  const mission = useMission();
  const now = useClock(1000);
  const { state, stateAt, events } = mission;

  if (!state) {
    return (
      <div className="app">
        <TopBar mission={mission} now={now} />
        <div className="boot">Connecting to Mission Control…</div>
      </div>
    );
  }

  const active = state.pipeline.find((r) => r.ticket === state.active_ticket) ?? null;
  return (
    <div className="app">
      <TopBar mission={mission} now={now} />
      <Pipeline state={state} stateAt={stateAt} now={now} />
      <div className="lower">
        <Fleet fleet={state.fleet} />
        <Timeline events={events} activeRow={active} />
        <aside className="side">
          <Queues state={state} />
          <Telemetry state={state} stateAt={stateAt} now={now} activeRow={active} />
        </aside>
      </div>
    </div>
  );
}
