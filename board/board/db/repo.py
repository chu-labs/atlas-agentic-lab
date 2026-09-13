"""Repositories: SQL in, dicts out. Keep queries here and only here.

Every function takes an open connection so a route can compose several steps in one transaction.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

USER_COLS = "id, handle, display_name, kind, avatar, color, remit, authority, mode"


def user_summary(r: dict | None, prefix: str = "") -> dict | None:
    if not r or r.get(f"{prefix}handle") is None:
        return None
    return {
        "handle": r[f"{prefix}handle"],
        "display_name": r[f"{prefix}display_name"],
        "kind": r[f"{prefix}kind"],
        "avatar": r[f"{prefix}avatar"],
        "color": r[f"{prefix}color"],
        "mode": r.get(f"{prefix}mode"),
    }


# ---------------------------------------------------------------- users


def list_users(c: Connection) -> list[dict]:
    return c.execute(f"select {USER_COLS} from users order by kind desc, id").fetchall()


def get_user(c: Connection, handle: str) -> dict | None:
    return c.execute(f"select {USER_COLS} from users where handle = %s", (handle,)).fetchone()


def upsert_user(c: Connection, u: dict) -> dict:
    return c.execute(
        f"""
        insert into users (handle, display_name, kind, avatar, color, remit, authority, mode)
        values (%(handle)s, %(display_name)s, %(kind)s, %(avatar)s, %(color)s, %(remit)s, %(authority)s, %(mode)s)
        on conflict (handle) do update set
          display_name = excluded.display_name, kind = excluded.kind, avatar = excluded.avatar,
          color = excluded.color, remit = excluded.remit,
          authority = coalesce(excluded.authority, users.authority),
          mode = coalesce(excluded.mode, users.mode)
        returning {USER_COLS}
        """,
        {**u, "authority": Jsonb(u["authority"]) if u.get("authority") is not None else None},
    ).fetchone()


# ---------------------------------------------------------------- sprints / project


def list_sprints(c: Connection) -> list[dict]:
    return c.execute("select * from sprints order by starts_on").fetchall()


def active_sprint(c: Connection) -> dict | None:
    return c.execute("select * from sprints where state = 'active' order by starts_on limit 1").fetchone()


def get_sprint(c: Connection, sprint_id: int) -> dict | None:
    return c.execute("select * from sprints where id = %s", (sprint_id,)).fetchone()


def next_issue_key(c: Connection, project_key: str = "ATLAS") -> str:
    r = c.execute(
        "update projects set issue_counter = issue_counter + 1 where key = %s returning issue_counter",
        (project_key,),
    ).fetchone()
    return f"{project_key}-{r['issue_counter']}"


# ---------------------------------------------------------------- issues

_ISSUE_SELECT = """
select i.*,
       a.handle as assignee_handle, a.display_name as assignee_display_name, a.kind as assignee_kind,
       a.avatar as assignee_avatar, a.color as assignee_color, a.mode as assignee_mode,
       r.handle as reporter_handle, r.display_name as reporter_display_name, r.kind as reporter_kind,
       r.avatar as reporter_avatar, r.color as reporter_color, r.mode as reporter_mode,
       s.name as sprint_name, s.state as sprint_state
from issues i
left join users a on a.id = i.assignee_id
join users r on r.id = i.reporter_id
left join sprints s on s.id = i.sprint_id
"""


def shape_issue(r: dict) -> dict:
    return {
        "id": r["id"],
        "key": r["key"],
        "type": r["type"],
        "title": r["title"],
        "description": r["description"],
        "status": r["status"],
        "priority": r["priority"],
        "assignee": user_summary(r, "assignee_"),
        "reporter": user_summary(r, "reporter_"),
        "labels": list(r["labels"] or []),
        "story_points": r["story_points"],
        "sprint": {"id": r["sprint_id"], "name": r["sprint_name"], "state": r["sprint_state"]} if r["sprint_id"] else None,
        "sprint_id": r["sprint_id"],
        "pr_url": r["pr_url"],
        "branch": r["branch"],
        "source": r["source"],
        "created_at": r["created_at"],
        "updated_at": r["updated_at"],
        "resolved_at": r["resolved_at"],
    }


def issue_summary(issue: dict) -> dict:
    """The compact shape carried on every event (EVENTS.md)."""
    return {
        "key": issue["key"],
        "type": issue["type"],
        "title": issue["title"],
        "status": issue["status"],
        "priority": issue["priority"],
        "assignee": issue["assignee"]["handle"] if issue.get("assignee") else None,
        "labels": issue["labels"],
        "pr_url": issue["pr_url"],
    }


def get_issue(c: Connection, key: str) -> dict | None:
    r = c.execute(_ISSUE_SELECT + " where i.key = %s", (key,)).fetchone()
    return shape_issue(r) if r else None


def list_issues(
    c: Connection,
    *,
    status: str | None = None,
    assignee: str | None = None,
    sprint: str | None = None,
    type_: str | None = None,
    label: str | None = None,
    q: str | None = None,
    limit: int = 200,
) -> list[dict]:
    where: list[str] = []
    params: list[Any] = []
    if status:
        where.append("i.status = %s")
        params.append(status)
    if assignee:
        where.append("a.handle = %s")
        params.append(assignee)
    if sprint:
        if sprint == "active":
            where.append("s.state = 'active'")
        elif sprint == "none":
            where.append("i.sprint_id is null")
        else:
            where.append("i.sprint_id = %s")
            params.append(int(sprint))
    if type_:
        where.append("i.type = %s")
        params.append(type_)
    if label:
        where.append("%s = any(i.labels)")
        params.append(label)
    if q:
        where.append("(i.title ilike %s or i.description ilike %s or i.key ilike %s)")
        params += [f"%{q}%", f"%{q}%", f"%{q}%"]
    sql = _ISSUE_SELECT + (" where " + " and ".join(where) if where else "") + " order by i.created_at desc, i.id desc limit %s"
    params.append(limit)
    return [shape_issue(r) for r in c.execute(sql, params).fetchall()]


def board_issues(c: Connection, sprint_id: int | None) -> list[dict]:
    """Issues shown on the board: the sprint's plus anything not yet placed in a sprint."""
    if sprint_id is None:
        sql = _ISSUE_SELECT + " where i.sprint_id is null order by i.created_at desc, i.id desc"
        rows = c.execute(sql).fetchall()
    else:
        sql = _ISSUE_SELECT + " where i.sprint_id = %s or i.sprint_id is null order by i.created_at desc, i.id desc"
        rows = c.execute(sql, (sprint_id,)).fetchall()
    return [shape_issue(r) for r in rows]


def insert_issue(c: Connection, fields: dict, created_at: datetime | None = None) -> dict:
    key = next_issue_key(c, fields.get("project_key", "ATLAS"))
    r = c.execute(
        """
        insert into issues (key, project_key, type, title, description, status, priority, assignee_id, reporter_id,
                            labels, story_points, sprint_id, pr_url, branch, source, created_at, updated_at, resolved_at)
        values (%(key)s, %(project_key)s, %(type)s, %(title)s, %(description)s, %(status)s, %(priority)s,
                %(assignee_id)s, %(reporter_id)s, %(labels)s, %(story_points)s, %(sprint_id)s, %(pr_url)s, %(branch)s,
                %(source)s, coalesce(%(created_at)s, now()), coalesce(%(created_at)s, now()), %(resolved_at)s)
        returning key
        """,
        {
            "key": key,
            "project_key": fields.get("project_key", "ATLAS"),
            "type": fields["type"],
            "title": fields["title"],
            "description": fields.get("description") or "",
            "status": fields.get("status") or "Backlog",
            "priority": fields.get("priority") or "Medium",
            "assignee_id": fields.get("assignee_id"),
            "reporter_id": fields["reporter_id"],
            "labels": list(fields.get("labels") or []),
            "story_points": fields.get("story_points"),
            "sprint_id": fields.get("sprint_id"),
            "pr_url": fields.get("pr_url"),
            "branch": fields.get("branch"),
            "source": Jsonb(fields["source"]) if fields.get("source") is not None else None,
            "created_at": created_at,
            "resolved_at": fields.get("resolved_at"),
        },
    ).fetchone()
    return get_issue(c, r["key"])


_UPDATABLE = {"title", "description", "priority", "labels", "story_points", "sprint_id", "pr_url", "branch", "assignee_id"}


def update_issue_fields(c: Connection, issue_id: int, changes: dict, at: datetime | None = None) -> None:
    sets = []
    params: dict[str, Any] = {"id": issue_id, "at": at}
    for k, v in changes.items():
        if k not in _UPDATABLE:
            raise ValueError(f"not updatable: {k}")
        sets.append(f"{k} = %({k})s")
        params[k] = list(v) if k == "labels" and v is not None else v
    if not sets:
        return
    c.execute(f"update issues set {', '.join(sets)}, updated_at = coalesce(%(at)s, now()) where id = %(id)s", params)


def set_status(c: Connection, issue_id: int, status: str, at: datetime | None = None) -> None:
    c.execute(
        """
        update issues set status = %(status)s, updated_at = coalesce(%(at)s, now()),
          resolved_at = case when %(status)s = 'Done' then coalesce(%(at)s, now()) else null end
        where id = %(id)s
        """,
        {"status": status, "at": at, "id": issue_id},
    )


# ---------------------------------------------------------------- comments / activity


def add_comment(c: Connection, issue_id: int, author_id: int, body: str, at: datetime | None = None) -> dict:
    r = c.execute(
        "insert into comments (issue_id, author_id, body, created_at) values (%s, %s, %s, coalesce(%s, now())) "
        "returning id, created_at",
        (issue_id, author_id, body, at),
    ).fetchone()
    add_activity(c, issue_id, author_id, "commented", body=body, at=r["created_at"])
    return r


def add_activity(
    c: Connection,
    issue_id: int,
    actor_id: int,
    kind: str,
    *,
    from_value: str | None = None,
    to_value: str | None = None,
    body: str | None = None,
    at: datetime | None = None,
) -> dict:
    return c.execute(
        """
        insert into activity (issue_id, actor_id, kind, from_value, to_value, body, created_at)
        values (%s, %s, %s, %s, %s, %s, coalesce(%s, now())) returning id, created_at
        """,
        (issue_id, actor_id, kind, from_value, to_value, body, at),
    ).fetchone()


def issue_activity(c: Connection, issue_id: int) -> list[dict]:
    rows = c.execute(
        """
        select act.id, act.kind, act.from_value, act.to_value, act.body, act.created_at,
               u.handle as actor_handle, u.display_name as actor_display_name, u.kind as actor_kind,
               u.avatar as actor_avatar, u.color as actor_color, u.mode as actor_mode
        from activity act join users u on u.id = act.actor_id
        where act.issue_id = %s order by act.created_at, act.id
        """,
        (issue_id,),
    ).fetchall()
    return [
        {
            "id": r["id"],
            "kind": r["kind"],
            "actor": user_summary(r, "actor_"),
            "from_value": r["from_value"],
            "to_value": r["to_value"],
            "body": r["body"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]


def issue_comments(c: Connection, issue_id: int) -> list[dict]:
    rows = c.execute(
        """
        select cm.id, cm.body, cm.created_at,
               u.handle as author_handle, u.display_name as author_display_name, u.kind as author_kind,
               u.avatar as author_avatar, u.color as author_color, u.mode as author_mode
        from comments cm join users u on u.id = cm.author_id
        where cm.issue_id = %s order by cm.created_at, cm.id
        """,
        (issue_id,),
    ).fetchall()
    return [{"id": r["id"], "author": user_summary(r, "author_"), "body": r["body"], "created_at": r["created_at"]} for r in rows]


# ---------------------------------------------------------------- stats


def stats(c: Connection) -> dict:
    by_status = {
        r["status"]: r["n"] for r in c.execute("select status, count(*) as n from issues group by status").fetchall()
    }
    by_assignee = {
        (r["handle"] or "unassigned"): r["n"]
        for r in c.execute(
            "select u.handle, count(*) as n from issues i left join users u on u.id = i.assignee_id "
            "group by u.handle order by n desc"
        ).fetchall()
    }
    total = c.execute("select count(*) as n from issues").fetchone()["n"]
    return {"total": total, "by_status": by_status, "by_assignee": by_assignee}
