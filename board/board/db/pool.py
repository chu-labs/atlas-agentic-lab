from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from ..settings import settings


@lru_cache
def pool() -> ConnectionPool:
    return ConnectionPool(settings().dsn, min_size=1, max_size=8, kwargs={"row_factory": dict_row}, open=True)


@contextmanager
def conn():
    with pool().connection() as c:
        yield c


def ensure_database() -> None:
    """Create the app database if it does not exist. Idempotent; safe at every start."""
    s = settings()
    with psycopg.connect(s.admin_dsn, autocommit=True) as c:
        exists = c.execute("select 1 from pg_database where datname = %s", (s.db_name,)).fetchone()
        if not exists:
            c.execute(psycopg.sql.SQL("create database {}").format(psycopg.sql.Identifier(s.db_name)))
