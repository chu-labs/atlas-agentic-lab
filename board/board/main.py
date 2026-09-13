"""ASGI entry point: `uvicorn board.main:app`. Serves the JSON API and the built SPA."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .api.auth import BasicAuthMiddleware
from .api.routes import router
from .logging_setup import configure
from .settings import settings

log = logging.getLogger(__name__)
WEB_DIST = Path(__file__).resolve().parents[1] / "web" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure()
    from .db.migrate import migrate

    try:
        applied = migrate()
        log.info("startup", extra={"version": __version__, "migrations_applied": applied})
    except Exception:
        log.exception("migration failed at startup")
    yield


app = FastAPI(title="atlas-board", version=__version__, lifespan=lifespan)
app.add_middleware(BasicAuthMiddleware)
app.include_router(router)


@app.get("/health")
def health():
    from .db.pool import conn

    db_ok = True
    try:
        with conn() as c:
            c.execute("select 1")
    except Exception:  # noqa: BLE001
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "service": settings().service_name, "version": __version__, "db": db_ok}


if (WEB_DIST / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        """SPA fallback: any non-API path serves index.html; the client router takes over."""
        if path.startswith("api/") or path == "api":
            raise HTTPException(404)
        candidate = WEB_DIST / path
        if path and candidate.is_file() and candidate.resolve().is_relative_to(WEB_DIST):
            return FileResponse(candidate)
        return FileResponse(WEB_DIST / "index.html")
