import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { api, usePoll } from "./api";
import { useShell } from "./App";
import { render } from "./markdown";
import { absolute, relative } from "./time";
import { PRIORITIES, slug, type Activity, type Issue, type Priority, type UserSummary } from "./types";
import { AgentTag, Avatar } from "./ui/Avatar";
import { Popover, type PopoverItem } from "./ui/Popover";
import { LabelChip, PriorityChip, StatusChip, TypeGlyph } from "./ui/StatusChip";

export default function IssuePage() {
  const { key = "" } = useParams();
  const { users } = useShell();
  const { data, error, refresh } = usePoll<Issue>(`/api/issues/${encodeURIComponent(key)}`, 2000);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const seen = useRef(-1);

  useEffect(() => {
    if (!data) return;
    const n = data.activity.length;
    if (seen.current >= 0 && n > seen.current) endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    seen.current = n;
  }, [data]);
  useEffect(() => {
    seen.current = -1;
  }, [key]);

  const act = async (label: string, fn: () => Promise<unknown>) => {
    setBusy(label);
    setErr(null);
    try {
      await fn();
      refresh();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  if (!data) {
    return (
      <main className="page center muted">
        {error ? (
          <div>
            <p>{error.toLowerCase().includes("not found") ? `No issue ${key}` : `Cannot load ${key}: ${error}`}</p>
            <Link to="/">← back to the board</Link>
          </div>
        ) : (
          "Loading…"
        )}
      </main>
    );
  }
  const i = data;
  const transitions = i.activity.filter((a) => a.kind === "transitioned" || a.kind === "created");

  return (
    <main className="page issue-page">
      <div className="issue-head">
        <div className="crumbs mono">
          <Link to="/">Board</Link> <span className="dim">/</span> <span>{i.sprint?.name ?? "Unplanned"}</span> <span className="dim">/</span>{" "}
          <span className="key-link">{i.key}</span>
        </div>
        <h1 className="issue-title">
          <TypeGlyph type={i.type} />
          <span>{i.title}</span>
          <StatusChip status={i.status} />
        </h1>
        <div className="history-strip" aria-label="status history">
          {transitions.map((t, idx) => (
            <span key={t.id} className="hist">
              {idx > 0 && <span className="hist-arrow">→</span>}
              <span className={`hist-dot status-${slug(t.to_value ?? "")}`} />
              <span className="hist-status">{t.to_value}</span>
              <span className="hist-time mono" title={absolute(t.created_at)}>
                {absolute(t.created_at)}
              </span>
              <Avatar user={t.actor} size={16} />
            </span>
          ))}
        </div>
      </div>

      {err && <div className="form-error">{err}</div>}

      <div className="issue-body">
        <section className="issue-main">
          <div className="panel">
            <div className="panel-title">Description</div>
            {i.description ? (
              <article className="markdown" dangerouslySetInnerHTML={{ __html: render(i.description) }} />
            ) : (
              <p className="muted">No description.</p>
            )}
          </div>

          <div className="panel feed-panel">
            <div className="panel-title">
              Activity
              <span className="panel-sub mono">
                {i.counts.commented} comments · {i.counts.reasoning} reasoning · {i.counts.transitioned} transitions
              </span>
            </div>
            <ol className="feed">
              {i.activity.map((a) => (
                <FeedItem key={a.id} a={a} />
              ))}
            </ol>
            <CommentBox issueKey={i.key} busy={busy === "comment"} onSubmit={(body) => act("comment", () => api.post(`/api/issues/${i.key}/comments`, { body }))} />
            <div ref={endRef} />
          </div>
        </section>

        <aside className="side">
          <div className="panel fields">
            <Field label="Status">
              <StatusChip status={i.status} />
              <div className="transitions">
                {i.allowed_transitions.map((s) => (
                  <button
                    key={s}
                    type="button"
                    className={`btn btn-sm transition-btn status-${slug(s)}`}
                    disabled={busy != null}
                    onClick={() => act(s, () => api.post(`/api/issues/${i.key}/transition`, { status: s }))}
                  >
                    → {s}
                  </button>
                ))}
              </div>
            </Field>
            <Field label="Assignee">
              <AssigneePicker current={i.assignee} users={users} busy={busy === "assign"} onPick={(h) => act("assign", () => api.patch(`/api/issues/${i.key}`, { assignee: h }))} />
            </Field>
            <Field label="Priority">
              <PriorityPicker current={i.priority} busy={busy === "priority"} onPick={(p) => act("priority", () => api.patch(`/api/issues/${i.key}`, { priority: p }))} />
            </Field>
            <Field label="Type">
              <TypeGlyph type={i.type} label />
            </Field>
            <Field label="Labels">{i.labels.length ? i.labels.map((l) => <LabelChip key={l} label={l} />) : <span className="muted">—</span>}</Field>
            <div className="field-grid">
              <Field label="Points">
                <span className="mono">{i.story_points ?? "–"}</span>
              </Field>
              <Field label="Sprint">{i.sprint ? i.sprint.name : <span className="muted">none</span>}</Field>
            </div>
            <Field label="Reporter">
              <span className="who">
                <Avatar user={i.reporter} size={24} />
                <span>{i.reporter.display_name}</span>
                <AgentTag user={i.reporter} />
              </span>
            </Field>
            <div className="field-grid">
              <Field label="Created">
                <Time iso={i.created_at} />
              </Field>
              <Field label="Updated">
                <Time iso={i.updated_at} />
              </Field>
              {i.resolved_at && (
                <Field label="Resolved">
                  <Time iso={i.resolved_at} />
                </Field>
              )}
            </div>
            <Field label="Pull request">
              {i.pr_url ? (
                <a href={i.pr_url} target="_blank" rel="noreferrer" className="pr-link mono">
                  #{i.pr_url.split("/").pop()} ↗
                </a>
              ) : (
                <span className="muted">—</span>
              )}
            </Field>
            {i.branch && (
              <Field label="Branch">
                <code className="mono">{i.branch}</code>
              </Field>
            )}
          </div>
          {i.source && (
            <div className="panel">
              <div className="panel-title">Source evidence</div>
              <dl className="kv">
                {Object.entries(i.source).map(([k, v]) => (
                  <div key={k}>
                    <dt>{k.replace(/_/g, " ")}</dt>
                    <dd className="mono">{typeof v === "string" ? v : JSON.stringify(v)}</dd>
                  </div>
                ))}
              </dl>
            </div>
          )}
        </aside>
      </div>
    </main>
  );
}

function Time({ iso }: { iso: string }) {
  return (
    <span className="time">
      <span className="mono">{absolute(iso)}</span> <span className="muted">· {relative(iso)}</span>
    </span>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="field">
      <div className="field-label">{label}</div>
      <div className="field-value">{children}</div>
    </div>
  );
}

function AssigneePicker({ current, users, busy, onPick }: { current: UserSummary | null; users: UserSummary[]; busy: boolean; onPick: (h: string | null) => void }) {
  const ref = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);
  const items: PopoverItem[] = [
    { key: "__none", label: "Unassigned", icon: <Avatar user={null} size={20} />, active: !current, onPick: () => onPick(null) },
    ...users.map((u) => ({
      key: u.handle,
      label: u.display_name,
      icon: <Avatar user={u} size={20} />,
      group: u.kind === "agent" ? "Agents" : "Humans",
      meta: u.kind === "agent" ? <span className="agent-tag">{u.mode ?? "agent"}</span> : undefined,
      active: current?.handle === u.handle,
      onPick: () => onPick(u.handle),
    })),
  ];
  return (
    <>
      <button ref={ref} type="button" className="picker" disabled={busy} onClick={() => setOpen((o) => !o)}>
        <Avatar user={current} size={24} />
        <span className="picker-text">
          <span>{current?.display_name ?? "Unassigned"}</span>
          <AgentTag user={current} />
        </span>
        <span className="caret">▾</span>
      </button>
      {open && ref.current && <Popover anchor={ref.current} items={items} onClose={() => setOpen(false)} />}
    </>
  );
}

function PriorityPicker({ current, busy, onPick }: { current: Priority; busy: boolean; onPick: (p: Priority) => void }) {
  const ref = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);
  const items: PopoverItem[] = PRIORITIES.map((p) => ({ key: p, label: p, icon: <PriorityChip priority={p} compact />, active: p === current, onPick: () => onPick(p) }));
  return (
    <>
      <button ref={ref} type="button" className="picker" disabled={busy} onClick={() => setOpen((o) => !o)}>
        <PriorityChip priority={current} />
        <span className="caret">▾</span>
      </button>
      {open && ref.current && <Popover anchor={ref.current} items={items} onClose={() => setOpen(false)} width={200} />}
    </>
  );
}

function CommentBox({ issueKey, busy, onSubmit }: { issueKey: string; busy: boolean; onSubmit: (body: string) => void }) {
  const [body, setBody] = useState("");
  useEffect(() => setBody(""), [issueKey]);
  return (
    <form
      className="comment-box"
      onSubmit={(e) => {
        e.preventDefault();
        if (!body.trim()) return;
        onSubmit(body.trim());
        setBody("");
      }}
    >
      <textarea rows={2} value={body} onChange={(e) => setBody(e.target.value)} placeholder="Comment as maroun… (markdown, ⌘↵ to send)" onKeyDown={(e) => {
        if ((e.metaKey || e.ctrlKey) && e.key === "Enter") (e.currentTarget.form as HTMLFormElement).requestSubmit();
      }} />
      <button type="submit" className="btn btn-primary btn-sm" disabled={busy || !body.trim()}>
        {busy ? "Sending…" : "Comment"}
      </button>
    </form>
  );
}

const LONG = 280;

function FeedItem({ a }: { a: Activity }) {
  const u = a.actor;
  const [expanded, setExpanded] = useState(false);
  const isThought = a.kind === "reasoning";
  const long = isThought && (a.body?.length ?? 0) > LONG;
  const text = long && !expanded ? `${a.body!.slice(0, LONG).trimEnd()}…` : a.body;
  return (
    <li className={`entry entry-${a.kind}`}>
      <Avatar user={u} size={32} />
      <div className="entry-body">
        <div className="entry-head">
          <span className="entry-name">{u.display_name}</span>
          <AgentTag user={u} />
          <span className="entry-verb">{verb(a)}</span>
          <span className="entry-time mono" title={absolute(a.created_at)}>
            {relative(a.created_at)} <span className="dim">·</span> {absolute(a.created_at)}
          </span>
        </div>
        {isThought && a.body && (
          <div className="thought">
            {text}
            {long && (
              <button type="button" className="link-btn" onClick={() => setExpanded((x) => !x)}>
                {expanded ? "show less" : "show more"}
              </button>
            )}
          </div>
        )}
        {(a.kind === "commented" || a.kind === "escalated") && a.body && <div className="markdown entry-text" dangerouslySetInnerHTML={{ __html: render(a.body) }} />}
        {a.kind === "transitioned" && a.body && <div className="entry-note">{a.body}</div>}
      </div>
    </li>
  );
}

function verb(a: Activity): ReactNode {
  switch (a.kind) {
    case "created":
      return <>opened this issue{a.to_value ? <> in <StatusChip status={a.to_value} size="sm" /></> : null}</>;
    case "transitioned":
      return (
        <>
          moved <StatusChip status={a.from_value ?? ""} size="sm" /> → <StatusChip status={a.to_value ?? ""} size="sm" />
        </>
      );
    case "commented":
      return "commented";
    case "reasoning":
      return <i className="reasoning-label">reasoning</i>;
    case "assigned":
      return a.to_value ? <>assigned to <b>{a.to_value}</b>{a.from_value ? <span className="dim"> (was {a.from_value})</span> : null}</> : <>unassigned{a.from_value ? <span className="dim"> (was {a.from_value})</span> : null}</>;
    case "field_changed":
      return (
        <>
          set <b>{a.body}</b>
          {a.from_value ? <> from <code className="inline mono">{a.from_value}</code></> : null}
          {a.to_value ? <> to <code className="inline mono">{a.to_value}</code></> : <> to <span className="dim">empty</span></>}
        </>
      );
    case "escalated":
      return <>escalated to <b>{a.to_value}</b></>;
  }
}
