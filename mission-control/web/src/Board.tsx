import { useMemo, useRef, useState } from "react";
import { Popover, type PopoverItem } from "./Popover";
import { Avatar } from "./Avatar";
import type { FleetCard, Selection } from "./types";
import { hms } from "./time";
import { useFetch } from "./useFetch";
import { postJSON } from "./useMission";

export const STATUSES = ["Backlog", "Triage", "In Progress", "In Review", "Done"] as const;
export interface BoardUser {
  handle: string;
  display_name: string;
  kind: "human" | "agent";
  avatar: string;
  color: string;
  mode: string | null;
  remit?: string;
}
export interface BoardIssue {
  key: string;
  type: "Bug" | "Story" | "Task" | "Incident";
  title: string;
  status: (typeof STATUSES)[number];
  priority: "Highest" | "High" | "Medium" | "Low" | "Lowest";
  assignee: BoardUser | null;
  reporter?: BoardUser | null;
  labels: string[];
  pr_url: string | null;
  branch?: string | null;
  created_at: string;
  updated_at: string;
  description?: string;
  story_points?: number | null;
}

const TYPE_GLYPH: Record<BoardIssue["type"], string> = { Bug: "🐞", Story: "📗", Task: "☑︎", Incident: "🚨" };
const PRIO_RANK: Record<BoardIssue["priority"], number> = { Highest: 0, High: 1, Medium: 2, Low: 3, Lowest: 4 };

export function Board({
  fleet,
  onSelect,
  selected,
  toast,
}: {
  fleet: FleetCard[];
  onSelect: (s: Selection) => void;
  selected: Selection | null;
  toast: (msg: string) => void;
}) {
  const issues = useFetch<BoardIssue[]>("/api/board/issues?limit=300", 5000);
  const users = useFetch<BoardUser[]>("/api/board/users", 60000);
  const [creating, setCreating] = useState(false);
  const [filter, setFilter] = useState("");
  const list = useMemo(() => {
    const all = issues.data ?? [];
    const q = filter.trim().toLowerCase();
    return q ? all.filter((i) => `${i.key} ${i.title} ${i.assignee?.handle ?? ""}`.toLowerCase().includes(q)) : all;
  }, [issues.data, filter]);
  const agents = fleet.filter((c) => c.kind === "fleet");
  const humans = (users.data ?? []).filter((u) => u.kind === "human");

  const assign = async (issue: BoardIssue, handle: string | null) => {
    try {
      await postJSON(`/api/board/issues/${issue.key}/assign`, { handle });
      const agent = agents.find((a) => a.handle === handle);
      toast(agent ? `${issue.key} → ${agent.display_name}. ${agent.display_name === "Forge" ? "Forge will pick this up within ~20 s." : "On its queue."}` : `${issue.key} assigned to ${handle ?? "nobody"}`);
      void issues.reload();
    } catch (e) {
      toast(`Could not assign: ${(e as Error).message}`);
    }
  };

  return (
    <section className="board">
      <header className="board-head">
        <h2 className="panel-title">
          Board <span className="panel-sub">ATLAS · {list.length} issues{issues.error ? ` · ${issues.error}` : ""}</span>
        </h2>
        <input className="board-filter" placeholder="filter…" value={filter} onChange={(e) => setFilter(e.target.value)} />
        <button className="btn-primary" onClick={() => setCreating(true)}>
          + New ticket
        </button>
      </header>
      {creating && (
        <NewTicket
          agents={agents}
          humans={humans}
          onClose={() => setCreating(false)}
          onCreated={(issue, handle) => {
            setCreating(false);
            const agent = agents.find((a) => a.handle === handle);
            toast(agent ? `${issue.key} filed and handed to ${agent.display_name}. ${agent.display_name === "Forge" ? "Forge will pick this up within ~20 s." : ""}` : `${issue.key} filed.`);
            void issues.reload();
          }}
        />
      )}
      <div className="columns">
        {STATUSES.map((s) => {
          const col = list.filter((i) => i.status === s).sort((a, b) => PRIO_RANK[a.priority] - PRIO_RANK[b.priority] || b.updated_at.localeCompare(a.updated_at));
          return (
            <div key={s} className={`column col-${s.toLowerCase().replace(/\s+/g, "-")}`}>
              <div className="column-head">
                <span className="column-name">{s}</span>
                <span className="column-count">{col.length}</span>
              </div>
              <div className="column-cards">
                {col.map((i) => (
                  <IssueCard
                    key={i.key}
                    issue={i}
                    agents={agents}
                    humans={humans}
                    selected={selected?.kind === "issue" && selected.key === i.key}
                    onOpen={() => onSelect({ kind: "issue", key: i.key })}
                    onAssign={(h) => void assign(i, h)}
                  />
                ))}
                {col.length === 0 && <div className="column-empty">—</div>}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function IssueCard({
  issue,
  agents,
  humans,
  selected,
  onOpen,
  onAssign,
}: {
  issue: BoardIssue;
  agents: FleetCard[];
  humans: BoardUser[];
  selected: boolean;
  onOpen: () => void;
  onAssign: (handle: string | null) => void;
}) {
  const [menu, setMenu] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const a = issue.assignee;
  const items: PopoverItem[] = [
    ...agents.map((c) => ({
      key: c.handle,
      group: "agents",
      label: c.display_name,
      icon: <Avatar handle={c.handle} size={28} color={c.color} emoji={c.avatar} />,
      meta: <span className={`mode-tag mode-${c.mode}`}>{c.mode}</span>,
      onPick: () => onAssign(c.handle),
    })),
    ...humans.map((u) => ({
      key: u.handle,
      group: "humans",
      label: u.display_name,
      icon: <Avatar handle={u.handle} size={28} color={u.color} emoji={u.avatar} />,
      meta: <span className="muted small">{u.remit}</span>,
      onPick: () => onAssign(u.handle),
    })),
    {
      key: "__none",
      group: "",
      label: "Unassign",
      icon: (
        <span className="av av-emoji" style={{ width: 28, height: 28 }}>
          ?
        </span>
      ),
      onPick: () => onAssign(null),
    },
  ];
  return (
    <article className={`issue ${selected ? "selected" : ""} prio-${issue.priority.toLowerCase()}`} onClick={onOpen}>
      <div className="issue-top">
        <span className="issue-type" title={issue.type}>
          {TYPE_GLYPH[issue.type]}
        </span>
        <span className="issue-key">{issue.key}</span>
        <span className={`prio prio-${issue.priority.toLowerCase()}`}>{issue.priority}</span>
      </div>
      <div className="issue-title">{issue.title}</div>
      <div className="issue-bottom">
        <button
          ref={trigger}
          className="assignee"
          aria-haspopup="menu"
          aria-expanded={menu}
          title={a ? `${a.display_name} · click or press Enter to reassign` : "unassigned · click or press Enter to assign"}
          onClick={(e) => {
            e.stopPropagation();
            setMenu((v) => !v);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " " || e.key === "ArrowDown") {
              e.preventDefault();
              e.stopPropagation();
              setMenu(true);
            }
          }}
        >
          <Avatar handle={a?.handle} size={28} color={a?.color} emoji={a?.avatar} />
          <span className="assignee-name">{a ? a.display_name : "Assign to…"}</span>
          <span className="caret">▾</span>
        </button>
        {issue.pr_url && (
          <a className="issue-pr" href={issue.pr_url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>
            PR
          </a>
        )}
        <span className="issue-when">{hms(issue.updated_at)}</span>
      </div>
      {menu && trigger.current && <Popover anchor={trigger.current} items={items} onClose={() => setMenu(false)} />}
    </article>
  );
}

function NewTicket({
  agents,
  humans,
  onClose,
  onCreated,
}: {
  agents: FleetCard[];
  humans: BoardUser[];
  onClose: () => void;
  onCreated: (issue: BoardIssue, handle: string | null) => void;
}) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [type, setType] = useState<"Bug" | "Story" | "Task">("Story");
  const [priority, setPriority] = useState<BoardIssue["priority"]>("Medium");
  const [assignee, setAssignee] = useState<string>("forge");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submit = async () => {
    if (!title.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const issue = await postJSON<BoardIssue>("/api/board/issues", {
        title: title.trim(),
        description,
        type,
        priority,
        assignee: assignee || null,
        status: assignee ? "Triage" : "Backlog",
      });
      onCreated(issue, assignee || null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <form
      className="new-ticket"
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
    >
      <input autoFocus className="nt-title" placeholder="Title — what should change?" value={title} onChange={(e) => setTitle(e.target.value)} />
      <textarea className="nt-desc" placeholder="Description (markdown). Acceptance criteria help the agent." value={description} onChange={(e) => setDescription(e.target.value)} rows={3} />
      <div className="nt-row">
        <label>
          Type
          <select value={type} onChange={(e) => setType(e.target.value as "Bug" | "Story" | "Task")}>
            <option>Bug</option>
            <option>Story</option>
            <option>Task</option>
          </select>
        </label>
        <label>
          Priority
          <select value={priority} onChange={(e) => setPriority(e.target.value as BoardIssue["priority"])}>
            {(["Highest", "High", "Medium", "Low", "Lowest"] as const).map((p) => (
              <option key={p}>{p}</option>
            ))}
          </select>
        </label>
        <label>
          Assign to
          <select value={assignee} onChange={(e) => setAssignee(e.target.value)}>
            <option value="">— nobody (backlog) —</option>
            <optgroup label="agents">
              {agents.map((a) => (
                <option key={a.handle} value={a.handle}>
                  {a.display_name} · {a.mode}
                </option>
              ))}
            </optgroup>
            <optgroup label="humans">
              {humans.map((h) => (
                <option key={h.handle} value={h.handle}>
                  {h.display_name}
                </option>
              ))}
            </optgroup>
          </select>
        </label>
        <span className="nt-spacer" />
        <button type="button" className="btn-ghost2" onClick={onClose}>
          Cancel
        </button>
        <button type="submit" className="btn-primary" disabled={busy || !title.trim()}>
          {busy ? "Filing…" : assignee ? `File & hand to ${agents.find((a) => a.handle === assignee)?.display_name ?? assignee}` : "File"}
        </button>
      </div>
      {error && <div className="gate-error">{error}</div>}
    </form>
  );
}
