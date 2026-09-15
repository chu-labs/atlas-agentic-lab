import { useEffect, useState } from "react";
import { hms, mmss } from "./time";
import { InlineBar, Panel } from "./ui";
import { useFetch } from "./useFetch";
import { postJSON } from "./useMission";

interface Job {
  id: number;
  name: string;
  status: string;
  conclusion: string | null;
  started_at: string | null;
  completed_at: string | null;
  duration_seconds: number | null;
  url: string | null;
}
interface Run {
  id: number;
  name: string | null;
  title: string | null;
  workflow: "ci" | "deploy";
  status: string;
  conclusion: string | null;
  event: string;
  branch: string;
  sha: string;
  actor: string | null;
  started_at: string | null;
  updated_at: string | null;
  duration_seconds: number | null;
  url: string;
  attempt: number;
  jobs: Job[];
  pending_deployments: { environment: string | null; environment_id: number | null; current_user_can_approve: boolean | null }[];
}
interface Pull {
  number: number;
  title: string;
  url: string;
  author: string;
  branch: string;
  sha: string;
  draft: boolean;
  created_at: string;
  checks: { total: number; success: number; failure: number; pending: number };
  reviews: { user: string; state: string; at: string }[];
}
interface CiCdData {
  repo: string;
  url: string;
  fetched_at: string;
  authenticated: boolean;
  runs: Run[];
  pulls: Pull[];
  deploying: Run | null;
  error: string | null;
}

function tone(status: string, conclusion: string | null): string {
  if (status !== "completed") return status === "waiting" ? "wait" : "run";
  if (conclusion === "success") return "ok";
  if (conclusion === "skipped" || conclusion === "neutral" || conclusion === "cancelled") return "dim";
  return "bad";
}
const ICON: Record<string, string> = { ok: "✓", bad: "✕", run: "◐", wait: "⏸", dim: "–" };

export function CiCd({ toast, humanConfigured }: { toast: (m: string) => void; humanConfigured: boolean }) {
  const { data, error, reload } = useFetch<CiCdData>("/api/cicd", 15000);
  const [sel, setSel] = useState<number | null>(null);
  useEffect(() => {
    if (data && sel == null && data.runs.length) setSel((data.deploying ?? data.runs[0]).id);
  }, [data, sel]);
  const run = data?.runs.find((r) => r.id === sel) ?? null;
  const approve = async (r: Run) => {
    try {
      const res = await postJSON<{ approved: number[]; note?: string }>(`/api/cicd/runs/${r.id}/approve`, {});
      toast(res.approved.length ? `Production deployment approved for run ${r.id}` : (res.note ?? "Nothing pending"));
      void reload();
    } catch (e) {
      toast(`Approve failed: ${(e as Error).message}`);
    }
  };
  return (
    <section className="cicd span-12 fill">
      <div className="cicd-head">
        <span className="panel-h">CI/CD</span>
        <span className="panel-s">{data?.repo ?? "…"} · last 10 runs · refreshed {data ? hms(data.fetched_at) : "…"}{data && !data.authenticated ? " · unauthenticated reads" : ""}</span>
        {data?.url && (
          <a className="link-out" href={`${data.url}/actions`} target="_blank" rel="noreferrer">
            Open on GitHub ↗
          </a>
        )}
      </div>
      {(error || data?.error) && <div className="banner banner-warn">{error ?? data?.error}</div>}
      {data?.deploying && (
        <div className="banner banner-deploy">
          <span className="banner-pulse" />
          <b>Now deploying</b> · run {data.deploying.id} · <code>{data.deploying.sha.slice(0, 10)}</code> on {data.deploying.branch} · {data.deploying.status.replace("_", " ")}
          {data.deploying.pending_deployments.length > 0 && (
            <>
              <span className="muted"> · waiting on the production environment gate</span>
              {humanConfigured ? (
                <button className="btn btn-approve btn-inline" onClick={() => void approve(data.deploying!)}>
                  Approve deployment
                </button>
              ) : (
                <span className="muted small"> (no human token here)</span>
              )}
            </>
          )}
        </div>
      )}
      <div className="cicd-grid">
        <Panel title="Workflow runs" count={data?.runs.length ?? 0} className="fill" scroll>
          {(data?.runs ?? []).map((r) => {
            const t = tone(r.status, r.conclusion);
            return (
              <button key={r.id} className={`run tone-${t} ${sel === r.id ? "on" : ""}`} onClick={() => setSel(r.id)}>
                <span className={`st st-${t}`}>{ICON[t]}</span>
                <span className="run-main">
                  <span className="run-name">
                    <b>{r.workflow}</b> <span className="muted">#{r.id}</span> {r.title && r.title !== r.name ? <span className="run-title">{r.title}</span> : null}
                  </span>
                  <span className="run-meta">
                    {r.event} · {r.branch} · <code>{r.sha.slice(0, 7)}</code> · {r.actor ?? "—"}
                  </span>
                </span>
                <span className="run-side">
                  <span className="mono">{r.started_at ? hms(r.started_at) : ""}</span>
                  <span className="mono muted">{r.duration_seconds != null ? mmss(r.duration_seconds) : ""}</span>
                </span>
              </button>
            );
          })}
          {data && data.runs.length === 0 && <div className="empty-line">No runs visible{data.error ? "" : " for this repository"}.</div>}
        </Panel>
        <div className="run-detail">
          {run ? <RunDetail run={run} onApprove={() => void approve(run)} humanConfigured={humanConfigured} /> : <div className="empty-line">Select a run.</div>}
          <Panel title="Open pull requests" count={data?.pulls.length ?? 0} scroll>
          <div className="pulls">
            {(data?.pulls ?? []).map((p) => (
              <a key={p.number} className="pull" href={p.url} target="_blank" rel="noreferrer">
                <span className="pull-num">#{p.number}</span>
                <span className="pull-title">{p.title}</span>
                <span className="pull-meta">
                  {p.author} · {p.branch}
                </span>
                <span className={`checks ${p.checks.failure ? "bad" : p.checks.pending ? "run" : p.checks.total ? "ok" : "dim"}`}>
                  checks {p.checks.success}/{p.checks.total}
                  {p.checks.pending ? ` · ${p.checks.pending} running` : ""}
                  {p.checks.failure ? ` · ${p.checks.failure} failed` : ""}
                </span>
                <span className="reviews">
                  {p.reviews.length === 0 && <span className="muted">no reviews</span>}
                  {p.reviews.slice(-3).map((rv, i) => (
                    <span key={i} className={`review review-${rv.state.toLowerCase()}`}>
                      {rv.user} · {rv.state.toLowerCase().replace("_", " ")}
                    </span>
                  ))}
                </span>
              </a>
            ))}
            {data && data.pulls.length === 0 && <div className="empty-line">No open pull requests.</div>}
          </div>
          </Panel>
        </div>
      </div>
    </section>
  );
}

function RunDetail({ run, onApprove, humanConfigured }: { run: Run; onApprove: () => void; humanConfigured: boolean }) {
  const t = tone(run.status, run.conclusion);
  const isDeploy = run.workflow === "deploy";
  const gateIdx = isDeploy ? run.jobs.findIndex((j) => /deploy|release|prod/i.test(j.name)) : -1;
  return (
    <div className="run-card">
      <div className="run-card-head">
        <span className={`st st-${t} st-big`}>{ICON[t]}</span>
        <div className="run-card-text">
          <div className="run-card-title">
            {run.workflow} <span className="muted">#{run.id}</span> {run.title}
          </div>
          <div className="run-meta">
            {run.event} · {run.branch} · <code>{run.sha.slice(0, 10)}</code> · {run.actor} · started {run.started_at ? hms(run.started_at) : "—"} ·{" "}
            {run.duration_seconds != null ? mmss(run.duration_seconds) : ""} · attempt {run.attempt}
          </div>
        </div>
        <a className="link-out" href={run.url} target="_blank" rel="noreferrer">
          run ↗
        </a>
      </div>
      <div className="stagebar">
        {run.jobs.length === 0 && <div className="empty-line">No jobs reported yet.</div>}
        {run.jobs.map((j, i) => {
          const jt = tone(j.status, j.conclusion);
          const isGate = i === gateIdx;
          return (
            <div key={j.id} className="stage-slot">
              {i > 0 && <span className={`arrow ${jt !== "dim" ? "arrow-done" : ""}`}>›</span>}
              <div className={`job tone-${jt} ${isGate ? "job-gate" : ""}`}>
                <span className={`st st-${jt}`}>{ICON[jt]}</span>
                <span className="job-name">{j.name}</span>
                <span className="job-dur mono">{j.duration_seconds != null ? mmss(j.duration_seconds) : j.status.replace("_", " ")}</span>
                {isGate && <span className="job-gate-tag">👤 environment gate</span>}
              </div>
            </div>
          );
        })}
      </div>
      {run.jobs.length > 0 && (
        <div className="jobbars">
          {run.jobs.map((j) => {
            const max = Math.max(1, ...run.jobs.map((x) => x.duration_seconds ?? 0));
            const jt = tone(j.status, j.conclusion);
            return (
              <div key={j.id} className="jobbar">
                <span className="jobbar-name">{j.name}</span>
                <InlineBar value={j.duration_seconds ?? 0} max={max} tone={jt} label={`${j.name}: ${mmss(j.duration_seconds ?? 0)}`} />
                <span className="mono m">{j.duration_seconds != null ? mmss(j.duration_seconds) : "—"}</span>
              </div>
            );
          })}
        </div>
      )}
      {run.pending_deployments.length > 0 && (
        <div className="pending">
          <span>
            Waiting for approval on <b>{run.pending_deployments.map((p) => p.environment).join(", ")}</b> — someone merged; a human still has to release.
          </span>
          {humanConfigured ? (
            <button className="btn btn-approve btn-inline" onClick={onApprove}>
              Approve deployment
            </button>
          ) : (
            <span className="muted small">no human token on this instance</span>
          )}
        </div>
      )}
    </div>
  );
}
