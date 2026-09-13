"""Test fixtures.

API tests need Postgres: they create a throwaway database on the server named by
DB_HOST/DB_PORT/DB_USER/DB_PASSWORD (default: the docker-compose instance on 55433), migrate it,
seed it, and drop it afterwards.
"""
from __future__ import annotations

import os
import uuid

import pytest

os.environ.setdefault("DB_PORT", "55433")
os.environ.setdefault("DB_USER", "atlas")
os.environ.setdefault("DB_PASSWORD", "atlas")
os.environ["DB_NAME"] = f"board_test_{uuid.uuid4().hex[:8]}"
os.environ["BASIC_AUTH_USER"] = ""
os.environ["EVENT_BUS"] = ""


@pytest.fixture(scope="session")
def db():
    import psycopg

    from board.db.migrate import migrate
    from board.db.pool import pool
    from board.db.seed import seed
    from board.settings import settings

    s = settings()
    migrate()
    counts = seed()
    yield counts
    pool().close()
    with psycopg.connect(s.admin_dsn, autocommit=True) as c:
        c.execute(f'drop database "{s.db_name}" with (force)')


@pytest.fixture
def client(db):
    from fastapi.testclient import TestClient

    from board.main import app

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def events(monkeypatch):
    """Collect emitted board events instead of logging/shipping them."""
    from board.api import routes

    captured: list[tuple[str, dict]] = []
    monkeypatch.setattr(routes, "emit", lambda dt, detail: captured.append((dt, detail)))
    return captured
