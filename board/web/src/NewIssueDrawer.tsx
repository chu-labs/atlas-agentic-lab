import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "./api";
import { useShell } from "./App";
import { PRIORITIES, TYPES, type Card, type IssueType, type Priority } from "./types";
import { Avatar } from "./ui/Avatar";
import { Drawer } from "./ui/Popover";

export function NewIssueDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { users, sprints, board } = useShell();
  const nav = useNavigate();
  const [type, setType] = useState<IssueType>("Task");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [priority, setPriority] = useState<Priority>("Medium");
  const [assignee, setAssignee] = useState<string>("");
  const [points, setPoints] = useState<string>("");
  const [labels, setLabels] = useState("");
  const [sprintId, setSprintId] = useState<string>(board?.sprint ? String(board.sprint.id) : "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const issue = await api.post<Card>("/api/issues", {
        type,
        title: title.trim(),
        description,
        priority,
        assignee: assignee || null,
        story_points: points === "" ? null : Number(points),
        labels: labels.split(",").map((s) => s.trim()).filter(Boolean),
        sprint_id: sprintId === "" ? -1 : Number(sprintId),
        status: "Backlog",
      });
      setTitle("");
      setDescription("");
      setLabels("");
      setPoints("");
      onClose();
      nav(`/issue/${issue.key}`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Drawer open={open} onClose={onClose} title="New issue">
      <form className="form" onSubmit={submit}>
        <div className="form-row">
          <label>
            Type
            <select value={type} onChange={(e) => setType(e.target.value as IssueType)}>
              {TYPES.map((t) => (
                <option key={t}>{t}</option>
              ))}
            </select>
          </label>
          <label>
            Priority
            <select value={priority} onChange={(e) => setPriority(e.target.value as Priority)}>
              {PRIORITIES.map((p) => (
                <option key={p}>{p}</option>
              ))}
            </select>
          </label>
          <label>
            Points
            <input type="number" min={0} max={100} value={points} onChange={(e) => setPoints(e.target.value)} placeholder="–" />
          </label>
        </div>
        <label>
          Title
          <input autoFocus value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Short, specific, imperative" required />
        </label>
        <label>
          Description <span className="muted">markdown</span>
          <textarea rows={8} value={description} onChange={(e) => setDescription(e.target.value)} placeholder="## What\n\n## Why\n\n## Acceptance" />
        </label>
        <div className="form-row">
          <label>
            Assignee
            <div className="select-with-avatar">
              <Avatar user={users.find((u) => u.handle === assignee) ?? null} size={24} />
              <select value={assignee} onChange={(e) => setAssignee(e.target.value)}>
                <option value="">Unassigned</option>
                <optgroup label="Humans">
                  {users.filter((u) => u.kind === "human").map((u) => (
                    <option key={u.handle} value={u.handle}>
                      {u.display_name}
                    </option>
                  ))}
                </optgroup>
                <optgroup label="Agents">
                  {users.filter((u) => u.kind === "agent").map((u) => (
                    <option key={u.handle} value={u.handle}>
                      {u.display_name}
                    </option>
                  ))}
                </optgroup>
              </select>
            </div>
          </label>
          <label>
            Sprint
            <select value={sprintId} onChange={(e) => setSprintId(e.target.value)}>
              <option value="">None</option>
              {sprints.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} · {s.state}
                </option>
              ))}
            </select>
          </label>
        </div>
        <label>
          Labels <span className="muted">comma separated</span>
          <input value={labels} onChange={(e) => setLabels(e.target.value)} placeholder="renewals, rating" />
        </label>
        {error && <div className="form-error">{error}</div>}
        <div className="form-actions">
          <span className="muted">
            Reported as <b>maroun</b>
          </span>
          <button type="button" className="btn" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary" disabled={busy || !title.trim()}>
            {busy ? "Creating…" : "Create issue"}
          </button>
        </div>
      </form>
    </Drawer>
  );
}
