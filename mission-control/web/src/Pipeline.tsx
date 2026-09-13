import { useEffect, useState } from "react";
import {
  SEGMENTS,
  SEGMENT_LABEL,
  STAGES,
  STAGE_LABEL,
  type Gate,
  type MissionState,
  type PipelineRow,
  type Segment,
  type Selection,
  type Stage,
} from "./types";
import { hms, mmss, secondsBetween } from "./time";
import { postJSON } from "./useMission";

const ORDER: Record<string, number> = Object.fromEntries(STAGES.map((s, i) => [s, i]));
const MAX_ROWS = 3;

export function Pipeline({
  state,
  stateAt,
  now,
  onSelect,
  selected,
}: {
  state: MissionState;
  stateAt: number;
  now: number;
  onSelect: (sel: Selection) => void;
  selected: Selection | null;
}) {
  const open = state.pipeline.filter((r) => !r.closed);
  const closed = state.pipeline.filter((r) => r.closed);
  let rows = open.slice(0, MAX_ROWS);
  if (rows.length === 0 && closed.length > 0) rows = [closed[0]]; // keep the last closed ticket on screen
  const recently = closed.filter((r) => !rows.includes(r)).slice(0, 4);
  const lastErr = state.signal.last_error_ts ? secondsBetween(state.signal.last_error_ts, new Date(now).toISOString()) : null;
  return (
    <section className="pipeline">
      {rows.length === 0 && (
        <div className="pipeline-row">
          <div className="pipeline-head">
            <span className="ticket-key idle">WATCHING</span>
            <span className="ticket-title muted">
              Watching production · {lastErr == null ? "no errors seen" : `last error ${agoText(lastErr)}`} · Scout opens a ticket when a cluster crosses its threshold
            </span>
          </div>
          <Chain row={null} gate={state.gate} stateAt={stateAt} now={now} onSelect={onSelect} selected={selected} />
        </div>
      )}
      {rows.map((row) => (
        <div
          key={row.signature ?? row.ticket ?? "row"}
          className={`pipeline-row ${row.escalated ? "is-escalated" : ""} ${row.closed ? "is-closed" : ""} ${row.observing ? "is-observing" : ""}`}
        >
          <div className="pipeline-head">
            <span className={`ticket-key ${row.observing ? "observing" : ""}`}>{row.observing ? "OBSERVING" : row.ticket}</span>
            <span className="ticket-title">{row.title}</span>
            <span className="ticket-metas">
              {row.error && (
                <span className="ticket-meta">
                  {row.error.count} error{row.error.count === 1 ? "" : "s"} · first {hms(row.error.first_seen ?? row.first_ts)}
                </span>
              )}
              <span className="ticket-meta">
                {row.closed ? `closed ${hms(row.closed_ts)}` : `${mmss(secondsBetween(row.first_ts, new Date(now).toISOString()))} elapsed`}
              </span>
            </span>
          </div>
          <Chain row={row} gate={state.gate} stateAt={stateAt} now={now} onSelect={onSelect} selected={selected} />
          {row.observing ? (
            <div className="durations">
              <span className="dur dur-live">
                <span className="dur-name">Observing</span> {mmss(secondsBetween(row.first_ts, new Date(now).toISOString()))}
              </span>
              <span className="dur">
                <span className="dur-name">Errors</span> {row.error?.count ?? 0}
              </span>
              <span className="dur">
                <span className="dur-name">Signature</span> <code>{row.signature}</code>
              </span>
              <span className="dur dur-total muted">{row.stage === "triage" ? "Scout is triaging" : "waiting for Scout's threshold"}</span>
            </div>
          ) : (
            <DurationStrip row={row} stateAt={stateAt} now={now} />
          )}
        </div>
      ))}
      {recently.length > 0 && (
        <div className="recent">
          <span className="recent-label">Recently closed</span>
          {recently.map((r) => (
            <button key={r.ticket} className="recent-item" onClick={() => onSelect({ kind: "stage", ticket: r.ticket!, stage: "closed" })}>
              <span className="recent-key">{r.ticket}</span>
              <span className="recent-title">{r.title}</span>
              <span className="recent-dur">
                {mmss(r.durations.total)} <span className="muted">({mmss(r.durations.machine)} machine · </span>
                <span className="amber">{mmss(r.durations.human)} human</span>
                <span className="muted">)</span>
              </span>
            </button>
          ))}
        </div>
      )}
    </section>
  );
}

function agoText(secs: number): string {
  if (secs < 60) return `${Math.round(secs)} s ago`;
  if (secs < 3600) return `${Math.round(secs / 60)} min ago`;
  return `${(secs / 3600).toFixed(1)} h ago`;
}

function DurationStrip({ row, stateAt, now }: { row: PipelineRow; stateAt: number; now: number }) {
  const d = row.durations;
  const drift = d.frozen ? 0 : (now - stateAt) / 1000;
  const val = (s: Segment) => {
    const v = d.segments[s];
    if (v == null) return null;
    return v + (d.open_segment === s ? drift : 0);
  };
  const total = d.total + (d.frozen ? 0 : drift);
  const human = d.human + (d.open_segment === "gate" ? drift : 0);
  return (
    <div className="durations">
      {SEGMENTS.map((s) => {
        const v = val(s);
        if (v == null) return null;
        return (
          <span key={s} className={`dur dur-${s} ${d.open_segment === s ? "dur-live" : ""}`}>
            <span className="dur-name">{SEGMENT_LABEL[s]}</span> {mmss(v)}
          </span>
        );
      })}
      <span className="dur dur-total">
        <span className="dur-name">Total</span> {mmss(total)}
        <span className="dur-split">
          {" "}
          ({mmss(Math.max(0, total - human))} machine, <span className="amber">{mmss(human)} human</span>)
        </span>
      </span>
    </div>
  );
}

function Chain({
  row,
  gate,
  stateAt,
  now,
  onSelect,
  selected,
}: {
  row: PipelineRow | null;
  gate: Gate;
  stateAt: number;
  now: number;
  onSelect: (sel: Selection) => void;
  selected: Selection | null;
}) {
  const current = row ? ORDER[row.stage] : -1;
  const gateHere = !!row && gate.waiting && gate.ticket === row.ticket && row.stage === "human_gate";
  const pick = (s: Stage) => row?.ticket && onSelect({ kind: "stage", ticket: row.ticket, stage: s });
  const live = !!row && !row.observing;
  const isSel = (s: Stage) => !!row && selected?.kind === "stage" && selected.ticket === row.ticket && selected.stage === s;
  return (
    <div className={`chain ${gateHere ? "chain-gate-live" : ""}`}>
      {STAGES.map((s, i) => {
        const cls = ["stage", `stage-${s}`];
        if (row) {
          if (i < current) cls.push("done");
          else if (i === current) cls.push(row.closed ? "done final" : "active");
          if (s === "verify" && row.verify_failed && i <= current) cls.push("failed");
          if (row.stages[s] || i <= current) cls.push("clickable");
        }
        if (row?.escalated) cls.push("dimmed");
        if (isSel(s)) cls.push("selected");
        const entered = row?.stages[s];
        const node =
          s === "human_gate" ? (
            <GateStage key={s} live={gateHere} gate={gate} row={row} entered={entered} stateAt={stateAt} now={now} cls={cls} onPick={() => pick(s)} />
          ) : (
            <button key={s} className={cls.join(" ")} onClick={() => pick(s)} disabled={!live}>
              <span className="stage-label">{STAGE_LABEL[s]}</span>
              <span className="stage-time">
                {s === "error" && row?.observing && row.error ? `${row.error.count}× · first ${hms(row.error.first_seen)}` : entered ? hms(entered) : "\u00a0"}
              </span>
            </button>
          );
        return (
          <div key={s} className="stage-slot">
            {i > 0 && <span className={`arrow ${row && i <= current ? "arrow-done" : ""}`}>›</span>}
            {node}
          </div>
        );
      })}
      {row?.escalated && (
        <div className="stage-slot">
          <span className="arrow arrow-escalated">›</span>
          <button className="stage escalated clickable" onClick={() => pick(row.stage)}>
            <span className="stage-icon">⚠</span>
            <span className="stage-label">Escalated to human</span>
            <span className="stage-time">{row.escalation?.category?.replace(/_/g, " ") ?? "needs a decision"}</span>
          </button>
        </div>
      )}
    </div>
  );
}

function GateStage({
  live,
  gate,
  row,
  entered,
  stateAt,
  now,
  cls,
  onPick,
}: {
  live: boolean;
  gate: Gate;
  row: PipelineRow | null;
  entered?: string;
  stateAt: number;
  now: number;
  cls: string[];
  onPick: () => void;
}) {
  const [busy, setBusy] = useState<"approve" | "reject" | null>(null);
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  useEffect(() => {
    if (!live) {
      setRejecting(false);
      setBusy(null);
      setError(null);
      setDone(null);
    }
  }, [live]);

  const waited = live ? gate.waited_seconds + (now - stateAt) / 1000 : 0;
  const pr = live ? gate.pr : row?.pr;

  const approve = async () => {
    if (!pr) return;
    setBusy("approve");
    setError(null);
    try {
      await postJSON("/api/gate/approve", { pr: pr.number });
      setDone("Approved and merged");
    } catch (e) {
      setError(String((e as Error).message));
    } finally {
      setBusy(null);
    }
  };
  const reject = async () => {
    if (!pr || !reason.trim()) return;
    setBusy("reject");
    setError(null);
    try {
      await postJSON("/api/gate/reject", { pr: pr.number, reason: reason.trim() });
      setDone("Sent back to Forge");
      setRejecting(false);
    } catch (e) {
      setError(String((e as Error).message));
    } finally {
      setBusy(null);
    }
  };

  const stop = (e: React.SyntheticEvent) => e.stopPropagation();

  return (
    <div className={[...cls, "gate", live ? "gate-live" : ""].join(" ")} onClick={onPick} role="button" tabIndex={0}>
      {!live ? (
        <>
          <span className="stage-icon">👤</span>
          <span className="stage-label">Human gate</span>
          <span className="stage-time">{entered ? hms(entered) : "agents cannot merge"}</span>
        </>
      ) : (
        <>
          <div className="gate-top">
            <span className="stage-icon">👤</span>
            <div>
              <div className="gate-title">Waiting on a human</div>
              <div className="gate-counter">{mmss(waited)}</div>
            </div>
          </div>
          {pr && (
            <div className="gate-pr">
              <span className="gate-pr-num">PR #{pr.number}</span>
              <span className="gate-pr-title">{pr.title ?? pr.branch ?? ""}</span>
            </div>
          )}
          {done ? (
            <div className="gate-done">{done}</div>
          ) : rejecting ? (
            <div className="gate-reject" onClick={stop}>
              <input
                autoFocus
                className="gate-reason"
                placeholder="One line: why?"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") void reject();
                  if (e.key === "Escape") setRejecting(false);
                }}
              />
              <button className="btn btn-reject" disabled={busy !== null || !reason.trim()} onClick={() => void reject()}>
                {busy === "reject" ? "Sending…" : "Send back"}
              </button>
              <button className="btn btn-ghost" onClick={() => setRejecting(false)}>
                Cancel
              </button>
            </div>
          ) : (
            <div className="gate-actions" onClick={stop}>
              <button className="btn btn-approve" disabled={busy !== null} onClick={() => void approve()}>
                {busy === "approve" ? "Merging…" : "Approve"}
              </button>
              <button className="btn btn-reject" disabled={busy !== null} onClick={() => setRejecting(true)}>
                Reject
              </button>
            </div>
          )}
          {error && <div className="gate-error">{error}</div>}
        </>
      )}
    </div>
  );
}
