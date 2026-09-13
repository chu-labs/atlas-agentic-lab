import { useEffect, useRef } from "react";
import { Link, useParams } from "react-router-dom";
import { usePoll } from "./api";
import { slug } from "./App";
import { Avatar, Who } from "./Avatar";
import { render } from "./markdown";
import { relative } from "./time";
import { TYPE_GLYPH, type Activity, type Issue } from "./types";

export default function IssuePage() {
  const { key = "" } = useParams();
  const { data, error } = usePoll<Issue>(`/api/issues/${encodeURIComponent(key)}`, 2000);
  const endRef = useRef<HTMLDivElement>(null);
  const seen = useRef<number>(-1);

  useEffect(() => {
    if (!data) return;
    const n = data.activity.length;
    if (seen.current >= 0 && n > seen.current) {
      endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    }
    seen.current = n;
  }, [data]);

  if (!data) {
    return (
      <main className="page center muted">
        {error ? (
          <>
            <p>{error.includes("404") ? `No issue ${key}` : `Cannot load ${key}: ${error}`}</p>
            <Link to="/">← back to the board</Link>
          </>
        ) : (
          "Loading…"
        )}
      </main>
    );
  }
  const i = data;
  return (
    <main className="page issue-page">
      <div className="issue-head">
        <Link to="/" className="back">
          ← board
        </Link>
        <div className="issue-key">
          <span className="type-glyph">{TYPE_GLYPH[i.type]}</span> {i.key}
          <span className="muted"> · {i.type}</span>
        </div>
        <h1 className="issue-title">
          {i.title} <span className={`status-pill status-${slug(i.status)}`}>{i.status}</span>
        </h1>
      </div>

      <div className="issue-body">
        <section className="issue-main">
          {i.description && (
            <article className="markdown description" dangerouslySetInnerHTML={{ __html: render(i.description) }} />
          )}
          <h2 className="feed-title">
            Activity <span className="muted">· {i.activity.length}</span>
          </h2>
          <ol className="feed">
            {i.activity.map((a) => (
              <FeedItem key={a.id} a={a} />
            ))}
          </ol>
          <div ref={endRef} />
        </section>

        <aside className="side">
          <Field label="Assignee">
            <Who user={i.assignee} size={48} />
          </Field>
          <Field label="Reporter">
            <Who user={i.reporter} size={48} />
          </Field>
          <Field label="Priority">
            <span className={`chip prio prio-${i.priority.toLowerCase()}`}>{i.priority}</span>
          </Field>
          <Field label="Points">{i.story_points ?? <span className="muted">—</span>}</Field>
          <Field label="Sprint">{i.sprint ? i.sprint.name : <span className="muted">none</span>}</Field>
          <Field label="Labels">
            {i.labels.length ? i.labels.map((l) => <span key={l} className="chip label">{l}</span>) : <span className="muted">—</span>}
          </Field>
          <Field label="Pull request">
            {i.pr_url ? (
              <a href={i.pr_url} target="_blank" rel="noreferrer" className="pr-link">
                #{i.pr_url.split("/").pop()} ↗
              </a>
            ) : (
              <span className="muted">—</span>
            )}
          </Field>
          {i.branch && (
            <Field label="Branch">
              <code>{i.branch}</code>
            </Field>
          )}
          <Field label="Created">{relative(i.created_at)}</Field>
          {i.resolved_at && <Field label="Resolved">{relative(i.resolved_at)}</Field>}
        </aside>
      </div>
    </main>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="field">
      <div className="field-label">{label}</div>
      <div className="field-value">{children}</div>
    </div>
  );
}

function FeedItem({ a }: { a: Activity }) {
  const u = a.actor;
  const isThought = a.kind === "reasoning";
  return (
    <li className={`entry entry-${a.kind}`}>
      <Avatar user={u} size={48} />
      <div className="entry-body">
        <div className="entry-head">
          <span className="entry-name">{u.display_name}</span>
          {u.kind === "agent" && <span className="agent-tag">agent</span>}
          <span className="entry-verb">{verb(a)}</span>
          <span className="entry-time">{relative(a.created_at)}</span>
        </div>
        {isThought && a.body && <div className="thought">{a.body}</div>}
        {!isThought && a.body && a.kind !== "field_changed" && a.kind !== "transitioned" && (
          <div className="markdown entry-text" dangerouslySetInnerHTML={{ __html: render(a.body) }} />
        )}
        {a.kind === "transitioned" && a.body && <div className="entry-note">{a.body}</div>}
      </div>
    </li>
  );
}

function verb(a: Activity): React.ReactNode {
  switch (a.kind) {
    case "created":
      return <>opened this issue{a.to_value ? <> in <b>{a.to_value}</b></> : null}</>;
    case "transitioned":
      return (
        <>
          moved <span className={`status-pill small status-${slug(a.from_value ?? "")}`}>{a.from_value}</span> →{" "}
          <span className={`status-pill small status-${slug(a.to_value ?? "")}`}>{a.to_value}</span>
        </>
      );
    case "commented":
      return "commented";
    case "reasoning":
      return <i className="reasoning-label">reasoning</i>;
    case "assigned":
      return a.to_value ? <>assigned to <b>{a.to_value}</b></> : "unassigned";
    case "field_changed":
      return (
        <>
          set <b>{a.body}</b>
          {a.to_value ? <> to <code className="inline">{a.to_value}</code></> : null}
        </>
      );
    case "escalated":
      return <>escalated to <b>{a.to_value}</b></>;
  }
}
