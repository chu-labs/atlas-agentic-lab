import { useState } from "react";
import { fmtInt, fmtUSD, mmss } from "./time";
import { useFetch } from "./useFetch";

interface DoraData {
  window: "24h" | "7d" | "all";
  days: number;
  deployment_frequency: { count: number; per_day: number };
  lead_time: { median_seconds: number | null; samples: number };
  change_failure_rate: { failures: number; deploys: number; rate: number | null };
  time_to_restore: { median_seconds: number | null; samples: number };
  trend: { label: string; deploys: number }[];
  tickets: {
    ticket: string;
    title: string;
    closed: boolean;
    escalated: boolean;
    error_to_pr: number | null;
    pr_to_deploy: number | null;
    deploy_to_verified: number | null;
    total: number | null;
    usd: number;
    verify_failed: boolean;
  }[];
  baselines: {
    deployment_frequency?: string;
    deployment_frequency_per_day?: number;
    lead_time_days?: number;
    change_failure_rate?: number;
    time_to_restore_days?: number;
    notes?: string;
  };
}

const ELITE = { df: "on demand (many per day)", lt: "< 1 day", cfr: "0–15%", ttr: "< 1 hour" };

function human(secs: number | null | undefined): string {
  if (secs == null) return "—";
  if (secs < 3600) return mmss(secs);
  if (secs < 86400) return `${(secs / 3600).toFixed(1)} h`;
  return `${(secs / 86400).toFixed(1)} d`;
}

export function Dora() {
  const [win, setWin] = useState<"24h" | "7d" | "all">("7d");
  const { data, error } = useFetch<DoraData>(`/api/dora?window=${win}`, 10000);
  const b = data?.baselines ?? {};
  const df = data?.deployment_frequency;
  const dfLabel = !df ? "—" : df.count === 0 ? "0" : df.per_day >= 1 ? `${df.per_day.toFixed(1)} / day` : df.per_day >= 1 / 7 ? `${(df.per_day * 7).toFixed(1)} / week` : `${(df.per_day * 30).toFixed(1)} / month`;
  const cfr = data?.change_failure_rate.rate;
  const maxTrend = Math.max(1, ...(data?.trend.map((t) => t.deploys) ?? [1]));
  return (
    <section className="dora">
      <header className="board-head">
        <h2 className="panel-title">
          DORA <span className="panel-sub">four keys · agentic pipeline vs the traditional team</span>
        </h2>
        <div className="seg">
          {(["24h", "7d", "all"] as const).map((w) => (
            <button key={w} className={`seg-btn ${win === w ? "on" : ""}`} onClick={() => setWin(w)}>
              {w}
            </button>
          ))}
        </div>
        {error && <span className="muted small">{error}</span>}
      </header>
      <div className="tiles">
        <Tile
          label="Deployment frequency"
          value={dfLabel}
          sub={df ? `${df.count} deploy${df.count === 1 ? "" : "s"} in ${win === "all" ? `${data?.days.toFixed(0)} d` : win}` : ""}
          then={b.deployment_frequency ?? "fortnightly"}
          elite={ELITE.df}
          good={!!df && df.count > 0}
        >
          <Trend data={data?.trend ?? []} max={maxTrend} />
        </Tile>
        <Tile
          label="Lead time for changes"
          value={human(data?.lead_time.median_seconds)}
          sub={data ? `median · PR opened → deployed · ${data.lead_time.samples} sample${data.lead_time.samples === 1 ? "" : "s"}` : ""}
          then={`~${b.lead_time_days ?? 14} days`}
          elite={ELITE.lt}
          good={data?.lead_time.median_seconds != null && data.lead_time.median_seconds < 86400}
        />
        <Tile
          label="Change failure rate"
          value={cfr == null ? "—" : `${Math.round(cfr * 100)}%`}
          sub={data ? `${data.change_failure_rate.failures} failed verification of ${data.change_failure_rate.deploys} deploys` : ""}
          then={`~${Math.round((b.change_failure_rate ?? 0.15) * 100)}%`}
          elite={ELITE.cfr}
          good={cfr != null && cfr <= 0.15}
        />
        <Tile
          label="Time to restore"
          value={human(data?.time_to_restore.median_seconds)}
          sub={data ? `median · first error → verified in production · ${data.time_to_restore.samples} sample${data.time_to_restore.samples === 1 ? "" : "s"}` : ""}
          then={`~${b.time_to_restore_days ?? 2} days`}
          elite={ELITE.ttr}
          good={data?.time_to_restore.median_seconds != null && data.time_to_restore.median_seconds < 3600}
        />
      </div>
      <div className="section-head">
        Per ticket <span className="count">{data?.tickets.length ?? 0}</span>
        <span className="muted small">
          {" "}
          · traditional benchmarks {b.notes ?? "illustrative until supplied"}
        </span>
      </div>
      <div className="table-wrap">
        <table className="tbl">
          <thead>
            <tr>
              <th>Ticket</th>
              <th>Title</th>
              <th className="num">Error → PR</th>
              <th className="num">PR → deploy</th>
              <th className="num">Deploy → verified</th>
              <th className="num">Total</th>
              <th className="num">Cost</th>
              <th>State</th>
            </tr>
          </thead>
          <tbody>
            {(data?.tickets ?? [])
              .slice()
              .reverse()
              .map((t) => (
                <tr key={t.ticket} className={t.verify_failed ? "row-bad" : ""}>
                  <td className="mono">{t.ticket}</td>
                  <td className="ellip">{t.title}</td>
                  <td className="num mono">{human(t.error_to_pr)}</td>
                  <td className="num mono">{human(t.pr_to_deploy)}</td>
                  <td className="num mono">{human(t.deploy_to_verified)}</td>
                  <td className="num mono">{human(t.total)}</td>
                  <td className="num mono">{fmtUSD(t.usd)}</td>
                  <td>
                    <span className={`pill ${t.escalated ? "pill-escalated" : t.verify_failed ? "pill-blocked" : t.closed ? "pill-done" : "pill-working"}`}>
                      {t.escalated ? "escalated" : t.verify_failed ? "verify failed" : t.closed ? "closed" : "in flight"}
                    </span>
                  </td>
                </tr>
              ))}
            {data && data.tickets.length === 0 && (
              <tr>
                <td colSpan={8} className="muted">
                  No tickets in this window.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Tile({ label, value, sub, then, elite, good, children }: { label: string; value: string; sub: string; then: string; elite: string; good: boolean; children?: React.ReactNode }) {
  return (
    <div className={`tile ${good ? "tile-good" : ""}`}>
      <div className="tile-label">{label}</div>
      <div className="tile-value">{value}</div>
      <div className="tile-sub">{sub}</div>
      {children}
      <div className="tile-bench">
        <span>
          <span className="bench-k">traditional</span> <s>{then}</s>
        </span>
        <span>
          <span className="bench-k">DORA elite</span> {elite}
        </span>
      </div>
    </div>
  );
}

function Trend({ data, max }: { data: { label: string; deploys: number }[]; max: number }) {
  return (
    <div className="trend" aria-label="deploys per bucket">
      {data.map((d, i) => (
        <span key={i} className={`trend-bar ${d.deploys ? "on" : ""}`} style={{ height: `${Math.max(8, (d.deploys / max) * 100)}%` }} title={`${d.label}: ${fmtInt(d.deploys)}`} />
      ))}
    </div>
  );
}
