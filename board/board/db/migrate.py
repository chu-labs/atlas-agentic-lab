from __future__ import annotations

import logging
from pathlib import Path

import psycopg

from ..settings import settings
from .pool import ensure_database

log = logging.getLogger(__name__)
MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"


def migrate() -> list[str]:
    ensure_database()
    applied: list[str] = []
    with psycopg.connect(settings().dsn, autocommit=False) as c:
        c.execute(
            "create table if not exists schema_migrations "
            "(version text primary key, applied_at timestamptz not null default now())"
        )
        done = {r[0] for r in c.execute("select version from schema_migrations")}
        for f in sorted(MIGRATIONS.glob("*.sql")):
            if f.name in done:
                continue
            c.execute(f.read_text())
            c.execute("insert into schema_migrations(version) values (%s)", (f.name,))
            applied.append(f.name)
            log.info("applied migration", extra={"migration": f.name})
        c.commit()
    return applied
