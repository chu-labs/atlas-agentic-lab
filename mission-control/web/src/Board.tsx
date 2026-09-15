import { useEffect, useMemo, useRef, useState } from "react";
import { Popover, type PopoverItem } from "./Popover";
import { DataTable, FilterBar, Panel, StatusChip, Tabs, toneForStatus, type Column } from "./ui";
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

function age(iso: string): string {
  const s = (Date.now() - Date.parse(iso)) / 1000;
  if (!Number.isFinite(s)) return "";
  if (s < 3600) return `${Math.max(1, Math.round(s / 60))}m`;
  if (s < 86400) return `${Math.round(s / 3600)}h`;
  return `${Math.round(s / 86400)}d`;
}

const TYPE_GLYPH: Record<BoardIssue["type"], string> = { Bug: "🐞", Story: "📗", Task: "☑︎", Incident: "🚨" };
const PRIO_RANK: Record<BoardIssue["priority"], number> = { Highest: 0, High: 1, Medium: 2, Low: 3, Lowest: 4 };

export function Board({
  fleet,
  onSelect,
  selected,
  toast,
  query = "",
}: {
  fleet: FleetCard[];
  onSelect: (s: Selection) => void;
  selected: Selection | null;
  toast: (msg: string) => void;
  query?: string;
}) {
  const issues = useFetch<BoardIssue[]>("/api/board/issues?limit=300", 5000);
  const users = useFetch<BoardUser[]>("/api/board/users", 60000);
  const [creating, setCreating] = useState(false);
  const [filter, setFilter] = useState("");
  const [f, setF] = useState<Record<string, string>>({});
  const [mode, setMode] = useState<"columns" | "table">("columns");
  useEffect(() => setFilter(query), [query]);
  const list = useMemo(() => {
    const all = issues.data ?? [];
    const q = filter.trim().toLowerCase();
    return all.filter((i) => {
      if (f.type && i.type !== f.type) return false;
      if (f.priority && i.priority !== f.priority) return false;
      if (f.assignee && (i.assignee?.handle ?? "none") !== f.assignee) return false;
      return !q || `${i.key} ${i.title} ${i.assignee?.handle ?? ""} ${i.labels.join(" ")}`.toLowerCase().includes(q);
    });
  }, [issues.data, filter, f]);
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

  const assignees = [...new Map((issues.data ?? []).filter((i) => i.assignee).map((i) => [i.assignee!.handle, i.assignee!.display_name])).entries()];
  const tableCols: Column<BoardIssue>[] = [
    { key: "key", title: "Key", width: "6.5rem", mono: true, render: (i) => <span className="b">{i.key}</span>, sort: (i) => i.key },
    { key: "type", title: "Type", width: "5.5rem", render: (i) => <>{TYPE_GLYPH[i.type]} {i.type}</>, sort: (i) => i.type },
    { key: "title", title: "Title", render: (i) => i.title, sort: (i) => i.title },
    { key: "status", title: "Status", width: "7.5rem", render: (i) => <StatusChip tone={toneForStatus(i.status)} icon={false}>{i.status}</StatusChip>, sort: (i) => STATUSES.indexOf(i.status) },
    { key: "prio", title: "Priority", width: "6.5rem", render: (i) => <StatusChip tone={i.priority === "Highest" ? "bad" : i.priority === "High" ? "warn" : "muted"} icon={false}>{i.priority}</StatusChip>, sort: (i) => PRIO_RANK[i.priority] },
    { key: "who", title: "Assignee", width: "9rem", render: (i) => <span className="avatar-cell"><Avatar handle={i.assignee?.handle} size={20} color={i.assignee?.color} emoji={i.assignee?.avatar} />{i.assignee?.display_name ?? "—"}</span>, sort: (i) => i.assignee?.display_name },
    { key: "labels", title: "Labels", width: "12rem", render: (i) => <span className="m">{i.labels.join(", ")}</span> },
    { key: "pr", title: "PR", width: "4rem", render: (i) => (i.pr_url ? <a href={i.pr_url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>PR</a> : "—") },
    { key: "upd", title: "Updated", width: "5.5rem", mono: true, render: (i) => hms(i.updated_at), sort: (i) => i.updated_at, defaultDesc: true },
  ];
  return (
    <section className="board span-12 fill">
      <Panel
        title="Board"
        count={list.length}
        sub={`ATLAS · ${(issues.data ?? []).length} issues${issues.error ? ` · ${issues.error}` : ""}`}
        className="fill"
        actions={
          <>
            <Tabs items={[{ id: "columns", label: "Columns" }, { id: "table", label: "Table" }]} value={mode} onChange={setMode} />
            <button className="btn-primary" onClick={() => setCreating(true)}>+ New ticket</button>
          </>
        }
      >
        <FilterBar
          filters={[
            { key: "type", label: "type", options: ["Bug", "Story", "Task", "Incident"].map((v) => ({ value: v, label: v })) },
            { key: "priority", label: "priority", options: ["Highest", "High", "Medium", "Low", "Lowest"].map((v) => ({ value: v, label: v })) },
            { key: "assignee", label: "assignee", options: [{ value: "none", label: "unassigned" }, ...assignees.map(([value, label]) => ({ value, label }))] },
          ]}
          values={f}
          onChange={(k, v) => setF((x) => ({ ...x, [k]: v }))}
          text={filter}
          onText={setFilter}
          placeholder="key, title, label…"
          right={<span className="m small">{STATUSES.map((st) => `${st} ${list.filter((i) => i.status === st).length}`).join(" · ")}</span>}
        />
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
      {mode === "table" ? (
        <DataTable rows={list} columns={tableCols} rowKey={(i) => i.key} onRowClick={(i) => onSelect({ kind: "issue", key: i.key })} selectedKey={selected?.kind === "issue" ? selected.key : null} defaultSort={{ key: "upd", desc: true }} dense emptyText="no issues match" />
      ) : (
      <div className="columns">
        {STATUSES.map((s) => {
          const col = list.filter((i) => i.status === s).sort((a, b) => PRIO_RANK[a.priority] - PRIO_RANK[b.priority] || b.updated_at.localeCompare(a.updated_at));
          return (
            <div key={s} className={`column col-${s.toLowerCase().replace(/\s+/g, "-")}`}>
              <div className="column-head">
                <span className="column-name">{s}</span>
                <span className="column-wip">{s === "In Progress" || s === "In Review" ? "WIP" : ""}</span>
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
      )}
      </Panel>
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
          <Avatar handle={a?.handle} size={20} color={a?.color} emoji={a?.avatar} />
          <span className="assignee-name">{a ? a.display_name : "Assign…"}</span>
          <span className="caret">▾</span>
        </button>
        {issue.pr_url && (
          <a className="issue-pr" href={issue.pr_url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>
            PR
          </a>
        )}
        <span className="issue-when" title={hms(issue.updated_at)}>{age(issue.updated_at)}</span>
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
