import { useState } from "react";
import { fmtInt, fmtUSD, mmss } from "./time";
import { DataTable, Panel, StatusChip, Tabs, type Column } from "./ui";
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
  type T = DoraData["tickets"][number];
  const ticketCols: Column<T>[] = [
    { key: "ticket", title: "Ticket", width: "6.5rem", mono: true, render: (t) => <span className="b">{t.ticket}</span>, sort: (t) => t.ticket },
    { key: "title", title: "Title", render: (t) => t.title, sort: (t) => t.title },
    { key: "e2p", title: "Error → PR", align: "right", width: "7rem", mono: true, render: (t) => human(t.error_to_pr), sort: (t) => t.error_to_pr },
    { key: "p2d", title: "PR → deploy", align: "right", width: "7rem", mono: true, render: (t) => human(t.pr_to_deploy), sort: (t) => t.pr_to_deploy },
    { key: "d2v", title: "Deploy → verified", align: "right", width: "8.5rem", mono: true, render: (t) => human(t.deploy_to_verified), sort: (t) => t.deploy_to_verified },
    { key: "total", title: "Total", align: "right", width: "6rem", mono: true, render: (t) => human(t.total), sort: (t) => t.total },
    { key: "usd", title: "Cost", align: "right", width: "5.5rem", mono: true, render: (t) => fmtUSD(t.usd), sort: (t) => t.usd },
    { key: "state", title: "State", width: "7.5rem", render: (t) => <StatusChip tone={t.escalated ? "violet" : t.verify_failed ? "bad" : t.closed ? "ok" : "accent"} icon={false}>{t.escalated ? "escalated" : t.verify_failed ? "verify failed" : t.closed ? "closed" : "in flight"}</StatusChip> },
  ];
  return (
    <section className="dora span-12 fill">
      <div className="cicd-head">
        <span className="panel-h">DORA</span>
        <span className="panel-s">four keys · agentic pipeline vs the traditional team{error ? ` · ${error}` : ""}</span>
        <span className="panel-actions">
          <Tabs items={(["24h", "7d", "all"] as const).map((w) => ({ id: w, label: w }))} value={win} onChange={setWin} />
        </span>
      </div>
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
      <Panel title="Per ticket" count={data?.tickets.length ?? 0} sub={`traditional benchmarks ${b.notes ?? "illustrative until supplied"}`} className="fill">
        <DataTable rows={(data?.tickets ?? []).slice().reverse()} columns={ticketCols} rowKey={(t) => t.ticket} defaultSort={{ key: "ticket", desc: true }} dense emptyText="no tickets in this window" rowClass={(t) => (t.verify_failed ? "row-bad" : "")} />
      </Panel>
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
