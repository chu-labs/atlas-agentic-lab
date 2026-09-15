import { useState } from "react";
import { VIEWS, type View } from "./Nav";
import type { Mission } from "./useMission";

export function TopBar({
  mission,
  now,
  compare,
  onCompare,
  view,
  onView,
  badges,
  query,
  onQuery,
  onSubmitQuery,
  env,
}: {
  mission: Mission;
  now: number;
  compare: boolean;
  onCompare: () => void;
  view: View;
  onView: (v: View) => void;
  badges: Partial<Record<View, string | number>>;
  query: string;
  onQuery: (q: string) => void;
  onSubmitQuery: (q: string) => void;
  env: { region?: string; cluster?: string; source?: string } | null;
}) {
  const { connected, transport, replayFlash, state } = mission;
  const replaying = replayFlash || !!state?.replaying;
  const clock = new Date(now).toLocaleTimeString("en-AU", { hour12: false });
  const [focus, setFocus] = useState(false);
  return (
    <header className="tb">
      <div className="tb-brand">
        <span className="tb-mark">A</span>
        <span className="tb-name">ATLAS</span>
        <span className="tb-prod">Mission Control</span>
      </div>
      <span className={`tb-env ${env?.source === "aws" ? "tb-env-aws" : ""}`} title="environment">
        {env ? `${env.cluster ?? "lab"} · ${env.region ?? ""}${env.source === "local" ? " · local" : ""}` : "…"}
      </span>
      <nav className="tb-tabs" aria-label="views">
        {VIEWS.map((v) => (
          <button key={v.id} className={`tb-tab ${view === v.id ? "on" : ""}`} onClick={() => onView(v.id)} title={`${v.hint} (${v.key})`}>
            <span className="tb-key">{v.key}</span>
            {v.label}
            {badges[v.id] != null && badges[v.id] !== "" && <span className="tb-badge">{badges[v.id]}</span>}
          </button>
        ))}
      </nav>
      <div className={`tb-search ${focus ? "on" : ""}`}>
        <span className="tb-search-ico">⌕</span>
        <input
          value={query}
          placeholder="Search tickets, endpoints, agents…  ( / )"
          onChange={(e) => onQuery(e.target.value)}
          onFocus={() => setFocus(true)}
          onBlur={() => setFocus(false)}
          onKeyDown={(e) => {
            if (e.key === "Enter") onSubmitQuery(query);
            if (e.key === "Escape") {
              onQuery("");
              (e.target as HTMLInputElement).blur();
            }
          }}
          id="global-search"
        />
        {query && (
          <button className="tb-clear" onClick={() => onQuery("")} aria-label="clear">
            ✕
          </button>
        )}
      </div>
      {replaying && <span className="replay-badge">REPLAY</span>}
      <button className={`tb-btn ${compare ? "on" : ""}`} onClick={onCompare} title="Then vs now (C)">
        Compare
      </button>
      <span className={`conn ${connected ? "conn-ok" : "conn-bad"}`} title={transport}>
        <i />
        {connected ? (transport === "ws" ? "live" : "polling") : "reconnecting"}
      </span>
      <span className="tb-clock">{clock}</span>
    </header>
  );
}
