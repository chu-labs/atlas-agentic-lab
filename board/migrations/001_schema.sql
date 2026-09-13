-- atlas-board schema. Statuses, priorities and kinds are enforced by check constraints so that a
-- typo from an agent is a 4xx, never a silently corrupted board.

create table users (
  id            serial primary key,
  handle        text not null unique,
  display_name  text not null,
  kind          text not null check (kind in ('human', 'agent')),
  avatar        text not null default '🙂',
  color         text not null default '#6b7280',
  remit         text not null default '',
  authority     jsonb,
  mode          text check (mode in ('autonomous', 'supervised')),
  created_at    timestamptz not null default now()
);

create table projects (
  key           text primary key,
  name          text not null,
  issue_counter int not null default 0
);

create table sprints (
  id         serial primary key,
  name       text not null,
  goal       text not null default '',
  starts_on  date not null,
  ends_on    date not null,
  state      text not null check (state in ('closed', 'active', 'future'))
);

create table issues (
  id            serial primary key,
  key           text not null unique,
  project_key   text not null references projects(key),
  type          text not null check (type in ('Bug', 'Story', 'Task', 'Incident')),
  title         text not null,
  description   text not null default '',
  status        text not null default 'Backlog'
                check (status in ('Backlog', 'Triage', 'In Progress', 'In Review', 'Done')),
  priority      text not null default 'Medium'
                check (priority in ('Highest', 'High', 'Medium', 'Low', 'Lowest')),
  assignee_id   int references users(id),
  reporter_id   int not null references users(id),
  labels        text[] not null default '{}',
  story_points  int,
  sprint_id     int references sprints(id),
  pr_url        text,
  branch        text,
  source        jsonb,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  resolved_at   timestamptz
);
create index issues_status_idx on issues(status);
create index issues_sprint_idx on issues(sprint_id);
create index issues_assignee_idx on issues(assignee_id);
create index issues_created_idx on issues(created_at desc);

create table comments (
  id          serial primary key,
  issue_id    int not null references issues(id) on delete cascade,
  author_id   int not null references users(id),
  body        text not null,
  created_at  timestamptz not null default now()
);
create index comments_issue_idx on comments(issue_id, created_at);

create table activity (
  id          serial primary key,
  issue_id    int not null references issues(id) on delete cascade,
  actor_id    int not null references users(id),
  kind        text not null check (kind in
                ('created', 'transitioned', 'commented', 'assigned', 'field_changed', 'reasoning', 'escalated')),
  from_value  text,
  to_value    text,
  body        text,
  created_at  timestamptz not null default now()
);
create index activity_issue_idx on activity(issue_id, created_at, id);
