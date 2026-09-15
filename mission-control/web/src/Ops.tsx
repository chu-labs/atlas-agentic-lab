import { useEffect, useMemo, useRef, useState } from "react";
import type { BoardIssue } from "./Board";
import { Avatar } from "./Avatar";
import { Fleet } from "./Fleet";
import { Timeline } from "./Timeline";
import type { MissionEvent, MissionState, Selection } from "./types";
import { fmtInt, hms, mmss, secondsBetween } from "./time";
import { DataTable, FilterBar, KpiTile, MiniBar, Panel, Sparkline, StatusChip, toneForStatus, type Column } from "./ui";
import { useFetch } from "./useFetch";

export const OPS_SOURCES = new Set(["atlas.platform", "atlas.scout", "atlas.watchtower", "atlas.ops", "atlas.board"]);

export interface Health {
  fetched_at: string;
  source: "aws" | "local";
  error: string | null;
  region?: string;
  cluster?: string;
  services: {
    name: string;
    desired: number | null;
    running: number | null;
    status: string | null;
    image_tag: string | null;
    deployment: { status: string; rollout_state: string | null; in_progress: boolean; updated_at?: string } | null;
    targets: { healthy: number; unhealthy: number; total: number } | null;
    metrics: { request_count: number; target_5xx: number; elb_5xx: number; elb_5xx_last_min: number; p95_ms: number; unhealthy_hosts: number } | null;
  }[];
}

export interface Cluster {
  signature: string | null;
  kind: "crash" | "business_rule" | "performance" | "infra";
  count: number;
  last_10m: number;
  first_ts: string;
  last_ts: string;
  impact: number;
  endpoint: string | null;
  method: string | null;
  error_type: string | null;
  message: string | null;
  status_code: number | null;
  status: "alerting" | "observing" | "ticketed" | "resolved";
  ticket: string | null;
  stage: string | null;
  samples: { ts: string; request_id?: string; message?: string; status_code?: number; method?: string; endpoint?: string; customer_impact?: unknown; stack?: string | null }[];
}

export const KIND_LABEL: Record<Cluster["kind"], string> = { crash: "Crashes", business_rule: "Business rules", performance: "Performance", infra: "Infrastructure" };
export const KIND_ICON: Record<Cluster["kind"], string> = { crash: "💥", business_rule: "⚖️", performance: "🐢", infra: "🧱" };
const KIND_TONE: Record<Cluster["kind"], "danger" | "warning" | "accent" | "info"> = { crash: "danger", business_rule: "warning", performance: "accent", infra: "info" };

/** Keep the last 40 health polls (10 min at 15 s) so the KPI strip has sparklines. */
function useHistory(health: Health | null) {
  const hist = useRef<{ at: string; req: number; err: number; p95: number; x5: number }[]>([]);
  const lastAt = useRef<string | null>(null);
  if (health && health.fetched_at !== lastAt.current) {
    lastAt.current = health.fetched_at;
    const m = health.services.map((s) => s.metrics).filter(Boolean) as NonNullable<Health["services"][number]["metrics"]>[];
    const req = m.reduce((a, x) => a + x.request_count, 0);
    const x5 = m.reduce((a, x) => a + x.target_5xx, 0) + Math.max(0, ...m.map((x) => x.elb_5xx));
    hist.current = [...hist.current, { at: health.fetched_at, req, err: req ? (x5 / req) * 100 : 0, p95: Math.max(0, ...m.map((x) => x.p95_ms)), x5 }].slice(-40);
  }
  return hist.current;
}

export function Operations({
  state,
  events,
  now,
  onSelect,
  selected,
  onGoEngineering,
  query,
  health,
}: {
  state: MissionState;
  events: MissionEvent[];
  now: number;
  onSelect: (s: Selection) => void;
  selected: Selection | null;
  onGoEngineering: () => void;
  query: string;
  health: Health | null;
}) {
  const clusters = useFetch<Cluster[]>("/api/ops/clusters", 5000);
  const issues = useFetch<BoardIssue[]>("/api/board/issues?limit=300", 10000);
  const incidents = useMemo(() => (issues.data ?? []).filter((i) => i.type === "Incident" && i.status !== "Done"), [issues.data]);
  const opsEvents = useMemo(() => events.filter((e) => OPS_SOURCES.has(e.source) || e.actor?.handle === "scout" || e.actor?.handle === "watchtower"), [events]);
  const opsAgents = state.fleet.filter((c) => c.handle === "scout" || c.handle === "watchtower");
  const active = state.pipeline.find((r) => r.ticket === state.active_ticket) ?? null;
  const hist = useHistory(health);
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [text, setText] = useState("");
  useEffect(() => setText(query), [query]);

  const metrics = (health?.services ?? []).map((s) => s.metrics).filter(Boolean) as NonNullable<Health["services"][number]["metrics"]>[];
  const req5 = metrics.reduce((a, m) => a + m.request_count, 0);
  const t5 = metrics.reduce((a, m) => a + m.target_5xx, 0);
  const e5 = Math.max(0, ...metrics.map((m) => m.elb_5xx));
  const p95 = Math.max(0, ...metrics.map((m) => m.p95_ms));
  const targets = (health?.services ?? []).map((s) => s.targets).filter(Boolean) as NonNullable<Health["services"][number]["targets"]>[];
  const healthy = targets.reduce((a, t) => a + t.healthy, 0);
  const total = targets.reduce((a, t) => a + t.total, 0);
  const errRate = req5 ? ((t5 + e5) / req5) * 100 : 0;
  const aws = health?.source === "aws";
  const errSpark = state.signal.rate;

  const allClusters = clusters.data ?? [];
  const shown = allClusters.filter((c) => {
    if (filters.kind && c.kind !== filters.kind) return false;
    if (filters.status ? c.status !== filters.status : c.status === "resolved") return false;
    const q = text.trim().toLowerCase();
    if (q && !`${c.signature} ${c.endpoint} ${c.error_type} ${c.message} ${c.ticket}`.toLowerCase().includes(q)) return false;
    return true;
  });
  const byEndpoint = useMemo(() => {
    const m = new Map<string, number>();
    for (const c of allClusters) if (c.last_10m > 0 && c.kind !== "infra") m.set(`${c.method ?? ""} ${c.endpoint ?? c.signature}`.trim(), (m.get(`${c.method ?? ""} ${c.endpoint ?? c.signature}`.trim()) ?? 0) + c.last_10m);
    return [...m.entries()].sort((a, b) => b[1] - a[1]).slice(0, 8).map(([label, value]) => ({ label, value }));
  }, [allClusters]);

  const clusterCols: Column<Cluster>[] = [
    { key: "kind", title: "", width: "2rem", align: "center", render: (c) => <span title={KIND_LABEL[c.kind]}>{KIND_ICON[c.kind]}</span>, sort: (c) => c.kind },
    { key: "endpoint", title: "Endpoint", width: "17rem", mono: true, render: (c) => `${c.method ? c.method + " " : ""}${c.endpoint ?? "—"}`, sort: (c) => c.endpoint },
    { key: "error", title: "Error", width: "12rem", render: (c) => <span className="b">{c.error_type}</span>, sort: (c) => c.error_type },
    { key: "message", title: "Message", render: (c) => <span className="m">{c.message}</span>, sort: (c) => c.message },
    { key: "count", title: "Count", align: "right", width: "5.5rem", mono: true, render: (c) => <>{fmtInt(c.count)}<span className="m"> · {c.last_10m}</span></>, sort: (c) => c.count, defaultDesc: true },
    { key: "impact", title: "Cust", align: "right", width: "4.5rem", mono: true, render: (c) => (c.impact ? fmtInt(c.impact) : "—"), sort: (c) => c.impact, defaultDesc: true },
    { key: "first", title: "First", width: "5.5rem", mono: true, render: (c) => hms(c.first_ts), sort: (c) => c.first_ts },
    { key: "last", title: "Last", width: "5.5rem", mono: true, render: (c) => hms(c.last_ts), sort: (c) => c.last_ts, defaultDesc: true },
    {
      key: "status", title: "Status", width: "9rem",
      render: (c) => (
        <StatusChip tone={toneForStatus(c.status)} pulse={c.status === "alerting"}>
          {c.status === "ticketed" ? (
            <a onClick={(e) => { e.stopPropagation(); if (c.ticket) onSelect({ kind: "issue", key: c.ticket }); }}>{c.ticket}</a>
          ) : c.status}
        </StatusChip>
      ),
      sort: (c) => c.status,
    },
  ];
  const svcCols: Column<Health["services"][number]>[] = [
    { key: "name", title: "Service", width: "11rem", render: (s) => <span className="b">{s.name}</span>, sort: (s) => s.name },
    { key: "tag", title: "Image", width: "7rem", mono: true, render: (s) => s.image_tag ?? "—" },
    { key: "tasks", title: "Tasks", align: "right", width: "5rem", mono: true, render: (s) => (s.desired == null ? "—" : `${s.running}/${s.desired}`), sort: (s) => s.running },
    { key: "healthy", title: "Healthy", align: "right", width: "5.5rem", mono: true, render: (s) => (s.targets ? `${s.targets.healthy}/${s.targets.total}` : "—") },
    { key: "req", title: "Req/5m", align: "right", width: "6rem", mono: true, render: (s) => (s.metrics ? fmtInt(s.metrics.request_count) : "—"), sort: (s) => s.metrics?.request_count },
    { key: "t5", title: "Tgt 5xx", align: "right", width: "5.5rem", mono: true, render: (s) => (s.metrics ? fmtInt(s.metrics.target_5xx) : "—"), sort: (s) => s.metrics?.target_5xx, className: "" },
    { key: "e5", title: "ELB 5xx", align: "right", width: "5.5rem", mono: true, render: (s) => (s.metrics ? fmtInt(s.metrics.elb_5xx) : "—"), sort: (s) => s.metrics?.elb_5xx },
    { key: "p95", title: "p95", align: "right", width: "5rem", mono: true, render: (s) => (s.metrics ? (s.metrics.p95_ms >= 1000 ? `${(s.metrics.p95_ms / 1000).toFixed(2)} s` : `${s.metrics.p95_ms} ms`) : "—"), sort: (s) => s.metrics?.p95_ms },
    { key: "deploy", title: "Last deploy", width: "8rem", render: (s) => (s.deployment ? <span className="m">{s.deployment.rollout_state?.toLowerCase().replace("_", " ") ?? s.deployment.status}</span> : "—") },
    {
      key: "state", title: "State", width: "8rem",
      render: (s) => {
        const bad = (s.targets?.unhealthy ?? 0) > 0 || (s.desired != null && s.running != null && s.running < s.desired);
        const warn = (s.metrics?.p95_ms ?? 0) > 2000 || (s.metrics?.target_5xx ?? 0) > 0;
        return <StatusChip tone={s.desired == null ? "muted" : bad ? "bad" : warn ? "warn" : "ok"} pulse={s.deployment?.in_progress}>{s.deployment?.in_progress ? "deploying" : s.desired == null ? "unknown" : bad ? "degraded" : warn ? "watch" : "healthy"}</StatusChip>;
      },
    },
  ];
  const incCols: Column<BoardIssue>[] = [
    { key: "key", title: "Key", width: "6.5rem", mono: true, render: (i) => <span className="b">{i.key}</span>, sort: (i) => i.key },
    { key: "prio", title: "Prio", width: "6rem", render: (i) => <StatusChip tone={i.priority === "Highest" ? "bad" : i.priority === "High" ? "warn" : "muted"} icon={false}>{i.priority}</StatusChip>, sort: (i) => i.priority },
    { key: "title", title: "Title", render: (i) => i.title, sort: (i) => i.title },
    { key: "who", title: "Owner", width: "8rem", render: (i) => <span className="avatar-cell"><Avatar handle={i.assignee?.handle} size={20} color={i.assignee?.color} emoji={i.assignee?.avatar} />{i.assignee?.display_name ?? "—"}</span> },
    { key: "status", title: "Status", width: "7rem", render: (i) => <StatusChip tone={toneForStatus(i.status)} icon={false}>{i.status}</StatusChip>, sort: (i) => i.status },
    { key: "upd", title: "Updated", width: "5.5rem", mono: true, render: (i) => hms(i.updated_at), sort: (i) => i.updated_at, defaultDesc: true },
  ];

  return (
    <>
      {state.gate.waiting && (
        <button className="gate-banner span-12" onClick={onGoEngineering}>
          <span className="gate-banner-icon">👤</span>
          <b>{state.gate.awaiting || 1} PR waiting for you</b>
          <span className="muted">· #{state.gate.pr?.number} {state.gate.pr?.title} · {mmss(state.gate.waited_seconds)}</span>
          <span className="gate-banner-go">→ Engineering</span>
        </button>
      )}
      <div className="kpis span-12">
        <KpiTile label="Requests / min" value={aws ? fmtInt(req5 / 5) : "—"} spark={hist.map((h) => h.req)} sparkKind="line" tone="accent" sub={aws ? `${fmtInt(req5)} in 5 min` : "no AWS view here"} />
        <KpiTile label="Error rate" value={aws ? `${errRate.toFixed(2)}` : "—"} unit="%" spark={hist.map((h) => h.err)} sparkKind="line" tone={errRate > 1 ? "danger" : "success"} sub={`${fmtInt(t5 + e5)} 5xx / ${fmtInt(req5)} req`} />
        <KpiTile label="p95 latency" value={aws ? (p95 >= 1000 ? (p95 / 1000).toFixed(2) : String(p95)) : "—"} unit={p95 >= 1000 ? "s" : "ms"} spark={hist.map((h) => h.p95)} sparkKind="line" tone={p95 > 2000 ? "danger" : "accent"} sub="worst service, 5 min" />
        <KpiTile label="Errors reported" value={fmtInt(state.signal.total_10m)} spark={errSpark} tone={state.signal.total_10m ? "danger" : "muted"} sub={`${state.signal.per_minute} in the last minute`} />
        <KpiTile label="Healthy targets" value={aws ? `${healthy}/${total}` : "—"} tone={aws && healthy < total ? "danger" : "success"} sub={aws ? `${health?.services.length} services · ECS` : ""} />
        <KpiTile label="Open incidents" value={fmtInt(incidents.length)} tone={incidents.length ? "warning" : "muted"} sub={`${allClusters.filter((c) => c.status !== "resolved").length} live clusters · ${state.signal.untracked_count} untracked errors`} />
      </div>
      <Panel title="Service health" count={health?.services.length ?? 0} sub={health ? (aws ? `ECS · ALB · CloudWatch · ${hms(health.fetched_at)}` : `local view (${health.error ?? "no AWS"})`) : "…"} className="span-8">
        <DataTable rows={health?.services ?? []} columns={svcCols} rowKey={(s) => s.name} dense emptyText="no services" />
      </Panel>
      <div className="span-4 kind-tiles">
        {(["crash", "business_rule", "performance", "infra"] as Cluster["kind"][]).map((k) => {
          const d = state.signal.by_kind?.[k] ?? { count: 0, rate: [], last_ts: null };
          return (
            <div key={k} className={`kt kt-${k} ${d.count ? "hot" : ""}`} onClick={() => setFilters((f) => ({ ...f, kind: f.kind === k ? "" : k }))} role="button">
              <span className="kt-ico">{KIND_ICON[k]}</span>
              <span className="kt-label">{KIND_LABEL[k]}</span>
              <span className="kt-num">{d.count}</span>
              <Sparkline values={d.rate} width={90} height={22} tone={KIND_TONE[k]} />
              <span className="kt-when">{d.last_ts ? hms(d.last_ts) : ""}</span>
            </div>
          );
        })}
      </div>
      <Panel title="Live clusters" count={shown.length} sub={`${allClusters.filter((c) => c.status === "resolved").length} resolved`} className="span-8 fill">
        <FilterBar
          filters={[
            { key: "kind", label: "kind", options: Object.entries(KIND_LABEL).map(([value, label]) => ({ value, label })) },
            { key: "status", label: "status", options: ["alerting", "observing", "ticketed", "resolved"].map((v) => ({ value: v, label: v })) },
          ]}
          values={filters}
          onChange={(k, v) => setFilters((f) => ({ ...f, [k]: v }))}
          text={text}
          onText={setText}
          placeholder="endpoint, error, ticket…"
        />
        <DataTable
          rows={shown}
          columns={clusterCols}
          rowKey={(c) => c.signature ?? ""}
          onRowClick={(c) => onSelect({ kind: "cluster", signature: c.signature ?? "" })}
          selectedKey={selected?.kind === "cluster" ? selected.signature : null}
          defaultSort={{ key: "last", desc: true }}
          dense
          emptyText="nothing open — production is quiet"
          rowClass={(c) => ((secondsBetween(c.last_ts, new Date(now).toISOString()) ?? 999) < 60 ? "fresh" : "")}
        />
      </Panel>
      <Panel title="Errors by endpoint" sub="last 10 min" className="span-4">
        <MiniBar rows={byEndpoint} tone="danger" format={(v) => fmtInt(v)} />
      </Panel>
      <Panel title="Incidents" count={incidents.length} sub="Watchtower's open incident tickets" className="span-8">
        <DataTable rows={incidents} columns={incCols} rowKey={(i) => i.key} onRowClick={(i) => onSelect({ kind: "issue", key: i.key })} dense emptyText="no open incidents" maxHeight={150} />
      </Panel>
      <Panel title="Ops agents" count={opsAgents.length} className="span-4">
        <Fleet fleet={opsAgents} onSelect={onSelect} selected={selected} compact />
      </Panel>
      <Timeline events={opsEvents} activeRow={active} rows={state.pipeline} onSelect={onSelect} title="Production timeline" dense className="span-12 fill" query={text} />
    </>
  );
}
