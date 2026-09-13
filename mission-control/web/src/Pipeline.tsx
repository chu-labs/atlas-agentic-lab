import { useEffect, useState } from "react";
import { STAGES, STAGE_LABEL, type Gate, type MissionState, type PipelineRow, type Stage } from "./types";
import { hms, mmss, secondsBetween } from "./time";
import { postJSON } from "./useMission";

const ORDER: Record<string, number> = Object.fromEntries(STAGES.map((s, i) => [s, i]));

export function Pipeline({ state, stateAt, now }: { state: MissionState; stateAt: number; now: number }) {
  const open = state.pipeline.filter((r) => !r.closed);
  let rows = open.slice(0, 3);
  if (rows.length === 0 && state.pipeline.length > 0) rows = [state.pipeline[0]]; // show the last closed ticket
  if (rows.length === 0) {
    return (
      <section className="pipeline">
        <div className="pipeline-head">
          <span className="ticket-key idle">PIPELINE</span>
          <span className="ticket-title muted">Waiting for the first production error…</span>
        </div>
        <Chain row={null} gate={state.gate} stateAt={stateAt} now={now} />
      </section>
    );
  }
  return (
    <section className="pipeline">
      {rows.map((row) => (
        <div key={row.ticket ?? "pending"} className={`pipeline-row ${row.escalated ? "is-escalated" : ""}`}>
          <div className="pipeline-head">
            <span className={`ticket-key ${row.ticket ? "" : "idle"}`}>{row.ticket ?? "NEW ERROR"}</span>
            <span className="ticket-title">{row.title || (row.error?.endpoint ? `${row.error.count}× ${row.error.endpoint}` : "")}</span>
            <span className="ticket-metas">
              {row.error && row.error.count > 1 && row.ticket && <span className="ticket-meta">{row.error.count} errors</span>}
              <span className="ticket-meta">
                started {hms(row.first_ts)} · {mmss(secondsBetween(row.first_ts, new Date(now).toISOString()))} ago
              </span>
            </span>
          </div>
          <Chain row={row} gate={state.gate} stateAt={stateAt} now={now} />
        </div>
      ))}
    </section>
  );
}

function Chain({ row, gate, stateAt, now }: { row: PipelineRow | null; gate: Gate; stateAt: number; now: number }) {
  const current = row ? ORDER[row.stage] : -1;
  const gateHere = !!row && gate.waiting && gate.ticket === row.ticket && row.stage === "human_gate";
  return (
    <div className={`chain ${gateHere ? "chain-gate-live" : ""}`}>
      {STAGES.map((s, i) => {
        const cls = ["stage", `stage-${s}`];
        if (row) {
          if (i < current) cls.push("done");
          else if (i === current) cls.push(row.closed ? "done final" : "active");
          if (s === "verify" && row.verify_failed && i <= current) cls.push("failed");
        }
        if (row?.escalated) cls.push("dimmed");
        const entered = row?.stages[s];
        const node =
          s === "human_gate" ? (
            <GateStage key={s} live={gateHere} gate={gate} row={row} entered={entered} stateAt={stateAt} now={now} cls={cls} />
          ) : (
            <div key={s} className={cls.join(" ")}>
              <span className="stage-label">{STAGE_LABEL[s]}</span>
              <span className="stage-time">{entered ? hms(entered) : " "}</span>
            </div>
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
          <div className="stage escalated">
            <span className="stage-icon">⚠</span>
            <span className="stage-label">Escalated to human</span>
            <span className="stage-time">{row.escalation?.category?.replace(/_/g, " ") ?? "needs a decision"}</span>
          </div>
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
}: {
  live: boolean;
  gate: Gate;
  row: PipelineRow | null;
  entered?: string;
  stateAt: number;
  now: number;
  cls: string[];
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

  if (!live) {
    return (
      <div className={[...cls, "gate"].join(" ")}>
        <span className="stage-icon">👤</span>
        <span className="stage-label">Human gate</span>
        <span className="stage-time">{entered ? hms(entered) : "agents cannot merge"}</span>
      </div>
    );
  }
  return (
    <div className={[...cls, "gate", "gate-live"].join(" ")}>
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
        <div className="gate-reject">
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
        <div className="gate-actions">
          <button className="btn btn-approve" disabled={busy !== null} onClick={() => void approve()}>
            {busy === "approve" ? "Merging…" : "Approve"}
          </button>
          <button className="btn btn-reject" disabled={busy !== null} onClick={() => setRejecting(true)}>
            Reject
          </button>
        </div>
      )}
      {error && <div className="gate-error">{error}</div>}
    </div>
  );
}

export function stageIndex(s: Stage): number {
  return ORDER[s];
}
