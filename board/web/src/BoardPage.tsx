import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useShell } from "./App";
import { absolute, daysBetween, relative, shortDate } from "./time";
import { PRIORITIES, STATUSES, TYPES, slug, type Card, type Status, type UserSummary } from "./types";
import { Avatar } from "./ui/Avatar";
import { DataTable, type Column } from "./ui/DataTable";
import { FilterBar, type FilterDef, type Filters } from "./ui/FilterBar";
import { BarRows, MiniBar } from "./ui/MiniBar";
import { LabelChip, Points, PriorityChip, StatusChip, TypeGlyph } from "./ui/StatusChip";

const STATUS_VAR: Record<Status, string> = {
  Backlog: "var(--status-backlog)",
  Triage: "var(--status-triage)",
  "In Progress": "var(--status-in-progress)",
  "In Review": "var(--status-in-review)",
  Done: "var(--status-done)",
};

export default function BoardPage() {
  const { board, users, view, q, sprintParam } = useShell();
  const [filters, setFilters] = useState<Filters>({});
  const [swimlanes, setSwimlanes] = useState(false);
  const [summaryOpen, setSummaryOpen] = useState(true);

  const all = useMemo(() => board?.columns.flatMap((c) => c.issues) ?? [], [board]);
  const labels = useMemo(() => Array.from(new Set(all.flatMap((i) => i.labels))).sort(), [all]);

  const defs: FilterDef[] = useMemo(
    () => [
      { key: "type", label: "Type", options: TYPES.map((t) => ({ value: t, label: t, icon: <TypeGlyph type={t} /> })) },
      { key: "priority", label: "Priority", options: PRIORITIES.map((p) => ({ value: p, label: p, icon: <PriorityChip priority={p} compact /> })) },
      {
        key: "assignee",
        label: "Assignee",
        options: [
          { value: "__none", label: "Unassigned", icon: <Avatar user={null} size={20} /> },
          ...users.map((u) => ({ value: u.handle, label: u.display_name, icon: <Avatar user={u} size={20} />, group: u.kind === "agent" ? "Agents" : "Humans" })),
        ],
      },
      { key: "label", label: "Label", options: labels.map((l) => ({ value: l, label: l })) },
    ],
    [users, labels],
  );

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const has = (k: string) => (filters[k] ?? []).length > 0;
    return all.filter((i) => {
      if (has("type") && !filters.type.includes(i.type)) return false;
      if (has("priority") && !filters.priority.includes(i.priority)) return false;
      if (has("assignee") && !filters.assignee.includes(i.assignee?.handle ?? "__none")) return false;
      if (has("label") && !i.labels.some((l) => filters.label.includes(l))) return false;
      if (needle && !`${i.key} ${i.title} ${i.labels.join(" ")} ${i.assignee?.display_name ?? ""}`.toLowerCase().includes(needle)) return false;
      return true;
    });
  }, [all, filters, q]);

  if (!board) return <main className="page center muted">Loading board…</main>;

  return (
    <main className="page board-page">
      <div className="toolbar">
        <FilterBar defs={defs} value={filters} onChange={setFilters}>
          {view === "board" && (
            <label className="toggle">
              <input type="checkbox" checked={swimlanes} onChange={(e) => setSwimlanes(e.target.checked)} />
              Swimlanes by assignee
            </label>
          )}
          <span className="toolbar-spacer" />
          <span className="muted mono toolbar-meta">
            {filtered.length}/{all.length} issues
          </span>
          <button type="button" className={`btn btn-sm btn-ghost ${summaryOpen ? "on" : ""}`} onClick={() => setSummaryOpen((o) => !o)}>
            Summary {summaryOpen ? "▾" : "▸"}
          </button>
        </FilterBar>
      </div>

      {summaryOpen && <SprintSummary issues={all} sprint={board.sprint} sprintParam={sprintParam} />}

      {view === "table" ? (
        <TableView issues={filtered} />
      ) : view === "timeline" ? (
        <TimelineView issues={filtered} sprint={board.sprint} />
      ) : (
        <BoardView issues={filtered} swimlanes={swimlanes} users={users} />
      )}
    </main>
  );
}

// ----------------------------------------------------------------------------- summary

function SprintSummary({ issues, sprint, sprintParam }: { issues: Card[]; sprint: { name: string; goal: string; starts_on: string; ends_on: string; state: string } | null; sprintParam: string }) {
  const byStatus = STATUSES.map((s) => ({ label: s, value: issues.filter((i) => i.status === s).reduce((a, i) => a + (i.story_points ?? 0), 0), color: STATUS_VAR[s] }));
  const countByStatus = STATUSES.map((s) => ({ label: s, value: issues.filter((i) => i.status === s).length, color: STATUS_VAR[s] }));
  const byType = TYPES.map((t) => ({ label: <TypeGlyph type={t} label />, value: issues.filter((i) => i.type === t).length }));
  const agent = issues.filter((i) => i.assignee?.kind === "agent").length;
  const human = issues.filter((i) => i.assignee?.kind === "human").length;
  const none = issues.length - agent - human;
  const totalPts = byStatus.reduce((a, s) => a + s.value, 0);
  const donePts = byStatus[4].value;
  const today = new Date().toISOString().slice(0, 10);
  const elapsed = sprint ? Math.min(100, Math.max(0, (daysBetween(sprint.starts_on, today) / Math.max(1, daysBetween(sprint.starts_on, sprint.ends_on))) * 100)) : 0;
  const prs = issues.filter((i) => i.pr_url).length;
  const agentDone = issues.filter((i) => i.status === "Done" && i.assignee?.kind === "agent").length;
  const agentAll = issues.filter((i) => i.assignee?.kind === "agent").length;

  return (
    <section className="summary">
      <div className="panel summary-goal">
        <div className="panel-title">{sprint ? sprint.name : sprintParam === "none" ? "Unplanned" : "Sprint"}</div>
        <p className="goal">{sprint?.goal ?? "Issues not yet placed in a sprint."}</p>
        {sprint && (
          <div className="progress" title={`${elapsed.toFixed(0)}% of the sprint elapsed`}>
            <div className="progress-track">
              <div className="progress-fill" style={{ width: `${elapsed}%` }} />
            </div>
            <span className="mono muted">
              {shortDate(sprint.starts_on)} → {shortDate(sprint.ends_on)}
            </span>
          </div>
        )}
      </div>
      <div className="panel">
        <div className="panel-title">
          Points by status <span className="panel-sub mono">{donePts}/{totalPts} done</span>
        </div>
        <MiniBar segments={byStatus} height={12} />
      </div>
      <div className="panel">
        <div className="panel-title">
          Issues by status <span className="panel-sub mono">{issues.length}</span>
        </div>
        <MiniBar segments={countByStatus} height={12} />
      </div>
      <div className="panel">
        <div className="panel-title">By type</div>
        <BarRows rows={byType} />
      </div>
      <div className="panel">
        <div className="panel-title">
          Assignment <span className="panel-sub mono">{prs} with PR</span>
        </div>
        <MiniBar
          segments={[
            { label: "Agents", value: agent, color: "var(--info)" },
            { label: "Humans", value: human, color: "var(--accent)" },
            { label: "Unassigned", value: none, color: "var(--status-backlog)" },
          ]}
          height={12}
        />
        <div className="kpi-row">
          <span className="kpi">
            <b className="mono">{agentAll ? Math.round((agentDone / agentAll) * 100) : 0}%</b>
            <span>agent tickets done</span>
          </span>
        </div>
      </div>
    </section>
  );
}

// ----------------------------------------------------------------------------- board

function BoardView({ issues, swimlanes, users }: { issues: Card[]; swimlanes: boolean; users: UserSummary[] }) {
  if (!swimlanes) {
    return (
      <section className="columns">
        {STATUSES.map((s) => (
          <Column key={s} status={s} issues={issues.filter((i) => i.status === s)} />
        ))}
      </section>
    );
  }
  const lanes: { user: UserSummary | null; issues: Card[] }[] = [];
  for (const u of users) {
    const mine = issues.filter((i) => i.assignee?.handle === u.handle);
    if (mine.length) lanes.push({ user: u, issues: mine });
  }
  const unassigned = issues.filter((i) => !i.assignee);
  if (unassigned.length) lanes.push({ user: null, issues: unassigned });
  return (
    <section className="swimlanes">
      <div className="lane-head columns">
        {STATUSES.map((s) => (
          <div key={s} className={`column-title column-${slug(s)}`}>
            <span>{s}</span>
            <span className="column-meta mono">{issues.filter((i) => i.status === s).length}</span>
          </div>
        ))}
      </div>
      {lanes.map((lane) => (
        <div key={lane.user?.handle ?? "__none"} className="lane">
          <div className="lane-label">
            <Avatar user={lane.user} size={24} />
            <span className="lane-name">{lane.user?.display_name ?? "Unassigned"}</span>
            {lane.user?.kind === "agent" && <span className="agent-tag">agent</span>}
            <span className="mono muted">{lane.issues.length}</span>
          </div>
          <div className="columns lane-columns">
            {STATUSES.map((s) => (
              <div key={s} className="lane-cell">
                {lane.issues
                  .filter((i) => i.status === s)
                  .map((i) => (
                    <IssueCard key={i.key} card={i} />
                  ))}
              </div>
            ))}
          </div>
        </div>
      ))}
    </section>
  );
}

function Column({ status, issues }: { status: Status; issues: Card[] }) {
  const pts = issues.reduce((a, i) => a + (i.story_points ?? 0), 0);
  return (
    <div className={`column column-${slug(status)}`}>
      <h2 className="column-title">
        <span>{status}</span>
        <span className="column-meta mono">
          {issues.length} <span className="dim">·</span> {pts} pts
        </span>
      </h2>
      <div className="cards">
        {issues.map((c) => (
          <IssueCard key={c.key} card={c} />
        ))}
        {issues.length === 0 && <div className="column-empty">—</div>}
      </div>
    </div>
  );
}

function IssueCard({ card }: { card: Card }) {
  return (
    <Link to={`/issue/${card.key}`} className={`card type-${card.type.toLowerCase()}`}>
      <div className="card-top">
        <TypeGlyph type={card.type} />
        <span className="card-key mono">{card.key}</span>
        <PriorityChip priority={card.priority} compact />
        <span className="spacer" />
        {card.pr_url && (
          <span className="chip pr-chip mono" title={card.pr_url}>
            PR #{card.pr_url.split("/").pop()}
          </span>
        )}
        <Points value={card.story_points} />
      </div>
      <div className="card-title">{card.title}</div>
      {card.labels.length > 0 && (
        <div className="card-labels">
          {card.labels.slice(0, 4).map((l) => (
            <LabelChip key={l} label={l} />
          ))}
        </div>
      )}
      <div className="card-bottom">
        <Avatar user={card.assignee} size={24} />
        <span className="card-assignee">{card.assignee?.display_name ?? "Unassigned"}</span>
        <span className="spacer" />
        {card.comment_count > 0 && (
          <span className="card-meta mono" title={`${card.comment_count} comments`}>
            ▭ {card.comment_count}
          </span>
        )}
        <span className="card-meta mono" title={`updated ${absolute(card.updated_at)}`}>
          {relative(card.updated_at)}
        </span>
      </div>
    </Link>
  );
}

// ----------------------------------------------------------------------------- table

function TableView({ issues }: { issues: Card[] }) {
  const nav = useNavigate();
  const cols: Column<Card>[] = [
    { key: "key", title: "Key", width: "110px", mono: true, sortValue: (r) => r.id, render: (r) => <Link to={`/issue/${r.key}`} className="key-link">{r.key}</Link> },
    { key: "type", title: "Type", width: "110px", sortValue: (r) => r.type, render: (r) => <TypeGlyph type={r.type} label /> },
    { key: "title", title: "Title", sortValue: (r) => r.title, render: (r) => <span className="cell-title">{r.title}</span> },
    { key: "status", title: "Status", width: "130px", sortValue: (r) => STATUSES.indexOf(r.status), render: (r) => <StatusChip status={r.status} size="sm" /> },
    { key: "priority", title: "Priority", width: "120px", sortValue: (r) => PRIORITIES.indexOf(r.priority), render: (r) => <PriorityChip priority={r.priority} /> },
    {
      key: "assignee",
      title: "Assignee",
      width: "160px",
      sortValue: (r) => r.assignee?.display_name ?? "~",
      render: (r) => (
        <span className="who">
          <Avatar user={r.assignee} size={24} />
          <span>{r.assignee?.display_name ?? <span className="muted">—</span>}</span>
        </span>
      ),
    },
    { key: "labels", title: "Labels", width: "220px", render: (r) => r.labels.map((l) => <LabelChip key={l} label={l} />) },
    { key: "points", title: "Pts", width: "72px", align: "right", mono: true, sortValue: (r) => r.story_points, render: (r) => r.story_points ?? <span className="muted">–</span> },
    { key: "comments", title: "▭", width: "60px", align: "right", mono: true, sortValue: (r) => r.comment_count, render: (r) => r.comment_count || <span className="muted">–</span> },
    { key: "sprint", title: "Sprint", width: "100px", sortValue: (r) => r.sprint?.name ?? "~", render: (r) => r.sprint?.name ?? <span className="muted">—</span> },
    { key: "updated", title: "Updated", width: "160px", align: "right", mono: true, sortValue: (r) => r.updated_at, render: (r) => <span title={absolute(r.updated_at)}>{absolute(r.updated_at)}</span> },
    {
      key: "pr",
      title: "PR",
      width: "80px",
      align: "right",
      mono: true,
      sortValue: (r) => (r.pr_url ? Number(r.pr_url.split("/").pop()) : null),
      render: (r) =>
        r.pr_url ? (
          <a href={r.pr_url} target="_blank" rel="noreferrer" className="pr-link" onClick={(e) => e.stopPropagation()}>
            #{r.pr_url.split("/").pop()}
          </a>
        ) : (
          <span className="muted">–</span>
        ),
    },
  ];
  return <DataTable rows={issues} columns={cols} rowKey={(r) => r.key} initialSort={{ key: "updated", dir: "desc" }} onRowClick={(r) => nav(`/issue/${r.key}`)} className="panel table-panel" />;
}

// ----------------------------------------------------------------------------- timeline

function TimelineView({ issues, sprint }: { issues: Card[]; sprint: { starts_on: string; ends_on: string } | null }) {
  const nav = useNavigate();
  const rows = [...issues].sort((a, b) => a.created_at.localeCompare(b.created_at));
  const start = sprint ? new Date(sprint.starts_on).getTime() - 86_400_000 : Math.min(...rows.map((r) => new Date(r.created_at).getTime()));
  const end = Math.max(sprint ? new Date(sprint.ends_on).getTime() + 86_400_000 : 0, Date.now(), ...rows.map((r) => new Date(r.updated_at).getTime()));
  const span = Math.max(1, end - start);
  const pct = (t: number) => Math.max(0, Math.min(100, ((t - start) / span) * 100));
  const days: number[] = [];
  for (let t = start; t <= end; t += 86_400_000) days.push(t);
  const now = Date.now();
  return (
    <section className="panel timeline">
      <div className="tl-row tl-head">
        <div className="tl-label" />
        <div className="tl-track">
          {days.map((t, i) => (
            <span key={t} className="tl-day mono" style={{ left: `${pct(t)}%` }}>
              {i % 2 === 0 ? shortDate(new Date(t).toISOString()) : ""}
            </span>
          ))}
          <span className="tl-now" style={{ left: `${pct(now)}%` }} />
        </div>
      </div>
      {rows.map((r) => {
        const a = new Date(r.created_at).getTime();
        const b = r.resolved_at ? new Date(r.resolved_at).getTime() : Math.max(new Date(r.updated_at).getTime(), Math.min(now, end));
        const left = pct(a);
        const width = Math.max(0.6, pct(b) - left);
        return (
          <div key={r.key} className="tl-row clickable" onClick={() => nav(`/issue/${r.key}`)}>
            <div className="tl-label">
              <TypeGlyph type={r.type} />
              <span className="mono key-link">{r.key}</span>
              <span className="tl-title">{r.title}</span>
            </div>
            <div className="tl-track">
              {days.map((t) => (
                <span key={t} className="tl-grid" style={{ left: `${pct(t)}%` }} />
              ))}
              <span className={`tl-bar status-${slug(r.status)}`} style={{ left: `${left}%`, width: `${width}%` }} title={`${absolute(r.created_at)} → ${r.resolved_at ? absolute(r.resolved_at) : "open"}`}>
                <Avatar user={r.assignee} size={16} />
                <span className="tl-bar-text">{r.status}</span>
              </span>
            </div>
          </div>
        );
      })}
      {rows.length === 0 && <div className="column-empty">No issues match.</div>}
    </section>
  );
}
