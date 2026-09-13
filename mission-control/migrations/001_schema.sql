-- mission-control schema: every bus event as it arrived, plus named recordings for replay.

create table events (
  id           bigserial primary key,
  received_at  timestamptz not null default now(),
  ts           timestamptz not null,
  source       text not null,
  detail_type  text not null,
  ticket       text,
  actor        jsonb,
  summary      text not null default '',
  detail       jsonb not null,
  replay       boolean not null default false
);
create index events_ticket_idx on events(ticket, id);
create index events_ts_idx on events(ts);

create table recordings (
  id          serial primary key,
  name        text not null unique,
  created_at  timestamptz not null default now(),
  events      jsonb not null
);
