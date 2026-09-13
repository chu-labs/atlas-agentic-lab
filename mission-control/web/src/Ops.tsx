import { useMemo } from "react";
import type { BoardIssue } from "./Board";
import { Avatar } from "./Avatar";
import { Fleet } from "./Fleet";
import { Timeline } from "./Timeline";
import type { MissionEvent, MissionState, Selection, Signal } from "./types";
import { fmtInt, hms, mmss, secondsBetween } from "./time";
import { useFetch } from "./useFetch";
import { useTween } from "./useMission";

export const OPS_SOURCES = new Set(["atlas.platform", "atlas.scout", "atlas.watchtower", "atlas.ops", "atlas.board"]);

interface Health {
  fetched_at: string;
  source: "aws" | "local";
  error: string | null;
  services: {
    name: string;
    desired: number | null;
    running: number | null;
    status: string | null;
    image_tag: string | null;
    deployment: { status: string; rollout_state: string | null; in_progress: boolean } | null;
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

const KIND_LABEL: Record<Cluster["kind"], string> = { crash: "Crashes", business_rule: "Business rules", performance: "Performance", infra: "Infrastructure" };
const KIND_ICON: Record<Cluster["kind"], string> = { crash: "💥", business_rule: "⚖️", performance: "🐢", infra: "🧱" };

export function Operations({
  state,
  events,
  now,
  onSelect,
  selected,
  onGoEngineering,
}: {
  state: MissionState;
  events: MissionEvent[];
  now: number;
  onSelect: (s: Selection) => void;
  selected: Selection | null;
  onGoEngineering: () => void;
}) {
  const health = useFetch<Health>("/api/ops/health", 15000);
  const clusters = useFetch<Cluster[]>("/api/ops/clusters", 5000);
  const issues = useFetch<BoardIssue[]>("/api/board/issues?limit=300", 10000);
  const incidents = useMemo(() => (issues.data ?? []).filter((i) => i.type === "Incident" && i.status !== "Done"), [issues.data]);
  const opsEvents = useMemo(() => events.filter((e) => OPS_SOURCES.has(e.source) || e.actor?.handle === "scout" || e.actor?.handle === "watchtower"), [events]);
  const opsAgents = state.fleet.filter((c) => c.handle === "scout" || c.handle === "watchtower");
  const active = state.pipeline.find((r) => r.ticket === state.active_ticket) ?? null;
  return (
    <>
      {state.gate.waiting && (
        <button className="gate-banner" onClick={onGoEngineering}>
          <span className="gate-banner-icon">👤</span>
          <b>
            {state.gate.awaiting || 1} PR{(state.gate.awaiting || 1) === 1 ? "" : "s"} waiting for you
          </b>
          <span className="muted">
            · #{state.gate.pr?.number} {state.gate.pr?.title} · {mmss(state.gate.waited_seconds)}
          </span>
          <span className="gate-banner-go">→ Engineering</span>
        </button>
      )}
      <HealthStrip health={health.data} />
      <KindTiles signal={state.signal} />
      <div className="ops-lower">
        <div className="ops-left">
          <ClusterTable clusters={clusters.data ?? []} onSelect={onSelect} selected={selected} now={now} />
          <Incidents incidents={incidents} onSelect={onSelect} />
        </div>
        <Timeline events={opsEvents} activeRow={active} rows={state.pipeline} onSelect={onSelect} title="Production" />
        <aside className="side">
          <Fleet fleet={opsAgents} onSelect={onSelect} selected={selected} title="Ops agents" />
        </aside>
      </div>
    </>
  );
}

function HealthStrip({ health }: { health: Health | null }) {
  return (
    <section className="health">
      <span className="signal-label">Service health</span>
      {(health?.services ?? []).map((s) => {
        const m = s.metrics;
        const t = s.targets;
        const bad = (t?.unhealthy ?? 0) > 0 || (m?.elb_5xx_last_min ?? 0) > 5 || (s.desired != null && s.running != null && s.running < s.desired);
        const warn = (m?.p95_ms ?? 0) > 2000 || (m?.target_5xx ?? 0) > 0;
        return (
          <div key={s.name} className={`svc ${bad ? "svc-bad" : warn ? "svc-warn" : s.desired == null ? "svc-dim" : "svc-ok"}`}>
            <div className="svc-head">
              <span className={`dot ${bad ? "dot-bad" : warn ? "dot-warn" : s.desired == null ? "dot-dim" : "dot-ok"}`} />
              <span className="svc-name">{s.name}</span>
              <code className="svc-tag">{s.image_tag ?? "—"}</code>
              {s.deployment?.in_progress && <span className="svc-deploying">deploying</span>}
            </div>
            <div className="svc-metrics">
              <span>
                <b>{s.running ?? "–"}</b>/{s.desired ?? "–"} <span className="muted">tasks</span>
              </span>
              <span>
                <b>{t ? `${t.healthy}/${t.total}` : "–"}</b> <span className="muted">healthy</span>
              </span>
              <span>
                <b>{m ? fmtInt(m.request_count) : "–"}</b> <span className="muted">req/5m</span>
              </span>
              <span className={(m?.target_5xx ?? 0) + (m?.elb_5xx ?? 0) > 0 ? "bad" : ""}>
                <b>{m ? fmtInt(m.target_5xx + m.elb_5xx) : "–"}</b> <span className="muted">5xx</span>
              </span>
              <span className={(m?.p95_ms ?? 0) > 2000 ? "bad" : ""}>
                <b>{m ? (m.p95_ms >= 1000 ? `${(m.p95_ms / 1000).toFixed(1)}s` : `${m.p95_ms}ms`) : "–"}</b> <span className="muted">p95</span>
              </span>
            </div>
          </div>
        );
      })}
      <span className="health-src muted small">
        {health ? (health.source === "aws" ? `ECS · ALB · CloudWatch · ${hms(health.fetched_at)}` : `no AWS view here (${health.error ?? "local"})`) : "…"}
      </span>
    </section>
  );
}

function KindTiles({ signal }: { signal: Signal }) {
  const kinds: Cluster["kind"][] = ["crash", "business_rule", "performance", "infra"];
  return (
    <section className="kinds">
      {kinds.map((k) => (
        <KindTile key={k} kind={k} data={signal.by_kind?.[k] ?? { count: 0, rate: [], last_ts: null }} />
      ))}
    </section>
  );
}

function KindTile({ kind, data }: { kind: Cluster["kind"]; data: { count: number; rate: number[]; last_ts: string | null } }) {
  const n = useTween(data.count);
  const max = Math.max(1, ...data.rate);
  return (
    <div className={`kind kind-${kind} ${data.count > 0 ? "hot" : ""}`}>
      <div className="kind-head">
        <span className="kind-icon">{KIND_ICON[kind]}</span>
        <span className="kind-label">{KIND_LABEL[kind]}</span>
        <span className="kind-when">{data.last_ts ? hms(data.last_ts) : ""}</span>
      </div>
      <div className="kind-body">
        <span className="kind-num">{Math.round(n)}</span>
        <span className="kind-sub">last 10 min</span>
        <svg className="kind-spark" viewBox="0 0 200 34" preserveAspectRatio="none">
          {data.rate.map((v, i) => {
            const w = 200 / Math.max(1, data.rate.length);
            const h = v === 0 ? 1.5 : Math.max(3, (v / max) * 30);
            return <rect key={i} x={i * w + 1} y={34 - h} width={Math.max(2, w - 2)} height={h} rx={1.5} className={v > 0 ? "spark-on" : "spark-off"} />;
          })}
        </svg>
      </div>
    </div>
  );
}

function ClusterTable({ clusters, onSelect, selected, now }: { clusters: Cluster[]; onSelect: (s: Selection) => void; selected: Selection | null; now: number }) {
  const open = clusters.filter((c) => c.status !== "resolved");
  const resolved = clusters.length - open.length;
  return (
    <section className="clusters">
      <div className="section-head">
        Live clusters <span className="count">{open.length}</span>
        <span className="muted small"> · {resolved} resolved</span>
      </div>
      <div className="table-wrap">
        <table className="tbl tbl-clusters">
          <thead>
            <tr>
              <th title="kind"> </th>
              <th>Where · error</th>
              <th className="num">Count</th>
              <th>Last seen</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {open.map((c) => {
              const key = c.signature ?? "";
              const age = secondsBetween(c.last_ts, new Date(now).toISOString()) ?? 0;
              return (
                <tr key={key} className={`clickable ${selected?.kind === "cluster" && selected.signature === key ? "on" : ""} ${age < 60 ? "fresh" : ""}`} onClick={() => onSelect({ kind: "cluster", signature: key })}>
                  <td className="kind-cell" title={KIND_LABEL[c.kind]}>
                    <span className={`kind-chip kind-${c.kind}`}>{KIND_ICON[c.kind]}</span>
                  </td>
                  <td className="ellip where-cell">
                    <div className="mono where-line">
                      {c.method ? `${c.method} ` : ""}
                      {c.endpoint ?? "—"}
                      <span className={`kind-chip kind-${c.kind} kind-inline`}> · {KIND_LABEL[c.kind]}</span>
                    </div>
                    <div className="error-line">
                      <b>{c.error_type}</b> <span className="muted">{c.message}</span>
                    </div>
                  </td>
                  <td className="num mono" title={`${c.last_10m} in the last 10 min · customer impact ${c.impact ? fmtInt(c.impact) : "—"}`}>
                    {fmtInt(c.count)}
                    {c.impact ? <span className="muted small"> · {fmtInt(c.impact)} cust</span> : null}
                  </td>
                  <td className="mono muted" title={`first ${hms(c.first_ts)}`}>
                    {hms(c.last_ts)}
                  </td>
                  <td>
                    <span className={`pill pill-${c.status}`}>{c.status === "ticketed" ? c.ticket : c.status}</span>
                  </td>
                </tr>
              );
            })}
            {open.length === 0 && (
              <tr>
                <td colSpan={7} className="muted">
                  Nothing open. Production is quiet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Incidents({ incidents, onSelect }: { incidents: BoardIssue[]; onSelect: (s: Selection) => void }) {
  return (
    <section className="incidents">
      <div className="section-head">
        Incidents <span className="count">{incidents.length}</span>
        <span className="muted small"> · Watchtower's open incident tickets</span>
      </div>
      {incidents.length === 0 && <div className="muted small empty">No open incidents.</div>}
      <div className="incident-list">
        {incidents.map((i) => (
          <button key={i.key} className="incident" onClick={() => onSelect({ kind: "issue", key: i.key })}>
            <span className="issue-key">{i.key}</span>
            <span className={`prio prio-${i.priority.toLowerCase()}`}>{i.priority}</span>
            <span className="incident-title">{i.title}</span>
            <span className="incident-meta">
              <Avatar handle={i.assignee?.handle} size={24} color={i.assignee?.color} emoji={i.assignee?.avatar} /> {i.assignee?.display_name ?? "unassigned"} · {i.status} · {hms(i.updated_at)}
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}
