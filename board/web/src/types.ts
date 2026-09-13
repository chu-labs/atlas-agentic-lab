export type UserSummary = {
  handle: string;
  display_name: string;
  kind: "human" | "agent";
  avatar: string;
  color: string;
  mode: "autonomous" | "supervised" | null;
};

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
  pr_url: string | null;
  updated_at: string;
};

export type Sprint = {
  id: number;
  name: string;
  goal: string;
  starts_on: string;
  ends_on: string;
  state: "closed" | "active" | "future";
};

export type Activity = {
  id: number;
  kind: "created" | "transitioned" | "commented" | "assigned" | "field_changed" | "reasoning" | "escalated";
  actor: UserSummary;
  from_value: string | null;
  to_value: string | null;
  body: string | null;
  created_at: string;
};

export type Issue = Card & {
  description: string;
  branch: string | null;
  sprint: { id: number; name: string; state: string } | null;
  created_at: string;
  resolved_at: string | null;
  activity: Activity[];
  counts: Record<string, number>;
};

export type Board = {
  project: { key: string; name: string };
  sprint: Sprint | null;
  columns: { status: Status; issues: Card[] }[];
  counts: Record<Status, number>;
};

export const STATUSES: Status[] = ["Backlog", "Triage", "In Progress", "In Review", "Done"];
export const TYPE_GLYPH: Record<IssueType, string> = { Bug: "🐞", Story: "📗", Task: "☑️", Incident: "🚨" };
