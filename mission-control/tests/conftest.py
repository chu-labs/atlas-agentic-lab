"""Test fixtures.

Tests need Postgres: they create a throwaway database on the server named by
DB_HOST/DB_PORT/DB_USER/DB_PASSWORD (default: the docker-compose instance on 55433), migrate it,
and drop it afterwards. No AWS, no GitHub: EVENT_BUS and GITHUB_HUMAN_TOKEN are empty.
"""
from __future__ import annotations

import os
import uuid

import pytest

os.environ.setdefault("DB_PORT", "55433")
os.environ.setdefault("DB_USER", "atlas")
os.environ.setdefault("DB_PASSWORD", "atlas")
os.environ["DB_NAME"] = f"mission_test_{uuid.uuid4().hex[:8]}"
os.environ["BASIC_AUTH_USER"] = ""
os.environ["EVENT_BUS"] = ""
os.environ["GITHUB_HUMAN_TOKEN"] = ""
os.environ["QUEUE_URL_MISSION_EVENTS"] = ""
for k in list(os.environ):
    if k.startswith("QUEUE_URL_"):
        os.environ.pop(k)


@pytest.fixture(scope="session")
def db():
    import psycopg

    from mission.db.migrate import migrate
    from mission.db.pool import pool
    from mission.settings import settings

    s = settings()
    migrate()
    yield s
    pool().close()
    with psycopg.connect(s.admin_dsn, autocommit=True) as c:
        c.execute(f'drop database "{s.db_name}" with (force)')


@pytest.fixture
def clean(db):
    from mission.hub import hub

    hub().reset()
    return hub()


@pytest.fixture
def client(clean):
    from fastapi.testclient import TestClient

    from mission.main import app

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
