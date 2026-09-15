export type UserSummary = {
  handle: string;
  display_name: string;
  kind: "human" | "agent";
  avatar: string;
  color: string;
  mode: "autonomous" | "supervised" | null;
};

export type User = UserSummary & { id: number; remit: string; authority: Record<string, unknown> | null };

export type Status = "Backlog" | "Triage" | "In Progress" | "In Review" | "Done";
export type Priority = "Highest" | "High" | "Medium" | "Low" | "Lowest";
export type IssueType = "Bug" | "Story" | "Task" | "Incident";

export type Card = {
  id: number;
  key: string;
  type: IssueType;
  title: string;
  status: Status;
  priority: Priority;
  assignee: UserSummary | null;
  reporter: UserSummary;
  labels: string[];
  story_points: number | null;
  sprint_id: number | null;
  sprint: { id: number; name: string; state: string } | null;
  pr_url: string | null;
  branch: string | null;
  created_at: string;
  updated_at: string;
  resolved_at: string | null;
  comment_count: number;
};

export type Sprint = {
  id: number;
  name: string;
  goal: string;
  starts_on: string;
  ends_on: string;
  state: "closed" | "active" | "future";
};

export type ActivityKind = "created" | "transitioned" | "commented" | "assigned" | "field_changed" | "reasoning" | "escalated";

export type Activity = {
  id: number;
  kind: ActivityKind;
  actor: UserSummary;
  from_value: string | null;
  to_value: string | null;
  body: string | null;
  created_at: string;
};

export type Issue = Card & {
  description: string;
  source: Record<string, unknown> | null;
  activity: Activity[];
  counts: Record<string, number>;
  allowed_transitions: Status[];
};

export type Board = {
  project: { key: string; name: string };
  sprint: Sprint | null;
  columns: { status: Status; issues: Card[] }[];
  counts: Record<Status, number>;
};

export const STATUSES: Status[] = ["Backlog", "Triage", "In Progress", "In Review", "Done"];
export const PRIORITIES: Priority[] = ["Highest", "High", "Medium", "Low", "Lowest"];
export const TYPES: IssueType[] = ["Bug", "Story", "Task", "Incident"];
export const TYPE_GLYPH: Record<IssueType, string> = { Bug: "●", Story: "◆", Task: "■", Incident: "▲" };
export const TYPE_COLOR: Record<IssueType, string> = {
  Bug: "var(--danger)",
  Story: "var(--success)",
  Task: "var(--accent)",
  Incident: "var(--warning)",
};

export function slug(s: string): string {
  return s.toLowerCase().replace(/\s+/g, "-");
}
