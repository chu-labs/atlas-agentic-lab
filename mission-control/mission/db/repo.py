"""Repository: SQL in, dicts out. Keep queries here and only here."""
from __future__ import annotations

from datetime import datetime

from psycopg import Connection
from psycopg.types.json import Jsonb

EVENT_COLS = "id, received_at, ts, source, detail_type, ticket, actor, summary, detail, replay"


def insert_event(c: Connection, e: dict) -> dict:
    return c.execute(
        f"""
        insert into events (ts, source, detail_type, ticket, actor, summary, detail, replay)
        values (%(ts)s, %(source)s, %(detail_type)s, %(ticket)s, %(actor)s, %(summary)s, %(detail)s, %(replay)s)
        returning {EVENT_COLS}
        """,
        {
            "ts": e["ts"],
            "source": e["source"],
            "detail_type": e["detail_type"],
            "ticket": e.get("ticket"),
            "actor": Jsonb(e.get("actor")) if e.get("actor") is not None else None,
            "summary": e.get("summary") or "",
            "detail": Jsonb(e.get("detail") or {}),
            "replay": bool(e.get("replay")),
        },
    ).fetchone()


def events_after(c: Connection, after: int, limit: int) -> list[dict]:
    return c.execute(
        f"select {EVENT_COLS} from events where id > %s order by id limit %s", (after, limit)
    ).fetchall()


def recent_events(c: Connection, limit: int) -> list[dict]:
    """The last `limit` events in ascending order, for rebuilding state at startup."""
    rows = c.execute(f"select {EVENT_COLS} from events order by id desc limit %s", (limit,)).fetchall()
    rows.reverse()
    return rows


def last_event_id(c: Connection) -> int:
    r = c.execute("select coalesce(max(id), 0) as id from events").fetchone()
    return int(r["id"])


def clear_events(c: Connection) -> None:
    c.execute("truncate events restart identity")


def save_recording(c: Connection, name: str, events: list[dict]) -> dict:
    return c.execute(
        """
        insert into recordings (name, events) values (%s, %s)
        on conflict (name) do update set events = excluded.events, created_at = now()
        returning id, name, created_at, jsonb_array_length(events) as count
        """,
        (name, Jsonb(events)),
    ).fetchone()


def list_recordings(c: Connection) -> list[dict]:
    return c.execute(
        "select id, name, created_at, jsonb_array_length(events) as count from recordings order by created_at desc"
    ).fetchall()


def get_recording(c: Connection, name: str) -> dict | None:
    return c.execute("select id, name, created_at, events from recordings where name = %s", (name,)).fetchone()


def delete_recording(c: Connection, name: str) -> bool:
    return c.execute("delete from recordings where name = %s", (name,)).rowcount > 0


def serialise_event(r: dict) -> dict:
    """A DB row as the JSON the SPA and the recordings use."""
    out = dict(r)
    for k in ("received_at", "ts"):
        if isinstance(out.get(k), datetime):
            out[k] = out[k].isoformat().replace("+00:00", "Z")
    return out
