import type { Mission } from "./useMission";

export function TopBar({ mission, now }: { mission: Mission; now: number }) {
  const { connected, transport, replayFlash, state } = mission;
  const replaying = replayFlash || !!state?.replaying;
  const clock = new Date(now).toLocaleTimeString("en-AU", { hour12: false });
  return (
    <header className="topbar">
      <div className="brand">
        <span className="brand-mark">A</span>
        <span className="brand-name">ATLAS</span>
        <span className="brand-sub">Mission Control</span>
      </div>
      {replaying && <span className="replay-badge">REPLAY</span>}
      <div className="topbar-right">
        <span className={`conn ${connected ? "conn-ok" : "conn-bad"}`} title={transport}>
          <i />
          {connected ? (transport === "ws" ? "live" : "polling") : "reconnecting"}
        </span>
        <span className="clock">{clock}</span>
      </div>
    </header>
  );
}
