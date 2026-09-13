import type { Mission } from "./useMission";

export function TopBar({ mission, now, compare, onCompare }: { mission: Mission; now: number; compare: boolean; onCompare: () => void }) {
  const { connected, transport, replayFlash, state } = mission;
  const replaying = replayFlash || !!state?.replaying;
  const clock = new Date(now).toLocaleTimeString("en-AU", { hour12: false });
  const fleet = state?.fleet ?? [];
  const auto = fleet.filter((c) => c.mode === "autonomous");
  const sup = fleet.filter((c) => c.mode === "supervised");
  const busy = (xs: typeof fleet) => xs.filter((c) => c.status !== "idle").length;
  return (
    <header className="topbar">
      <div className="brand">
        <span className="brand-mark">A</span>
        <span className="brand-text">
          <span className="brand-name">
            ATLAS <span className="brand-sub">Mission Control</span>
          </span>
          <span className="brand-tag">Agentic SDLC · human oversight</span>
        </span>
      </div>
      {state && (
        <span className="mode-chip" title="agents currently working / total">
          <span className="mode-auto">
            <i /> {busy(auto)}/{auto.length} autonomous
          </span>
          <span className="mode-sep">·</span>
          <span className="mode-sup">
            <i /> {busy(sup)}/{sup.length} supervised
          </span>
        </span>
      )}
      {replaying && <span className="replay-badge">REPLAY</span>}
      <div className="topbar-right">
        <button className={`compare-btn ${compare ? "on" : ""}`} onClick={onCompare} title="Then vs now (C)">
          Compare
        </button>
        <span className={`conn ${connected ? "conn-ok" : "conn-bad"}`} title={transport}>
          <i />
          {connected ? (transport === "ws" ? "live" : "polling") : "reconnecting"}
        </span>
        <span className="clock">{clock}</span>
      </div>
    </header>
  );
}
