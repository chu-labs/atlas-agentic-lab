"""Shared basic-auth credential for the whole lab. /health stays open for the ALB."""
from __future__ import annotations

import base64
import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from ..settings import settings

OPEN_PATHS = {"/health"}


class BasicAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        s = settings()
        if not s.basic_auth_user or request.url.path in OPEN_PATHS:
            return await call_next(request)
        header = request.headers.get("authorization", "")
        ok = False
        if header.startswith("Basic "):
            try:
                user, _, pw = base64.b64decode(header[6:]).decode().partition(":")
                ok = secrets.compare_digest(user, s.basic_auth_user) and secrets.compare_digest(pw, s.basic_auth_pass)
            except Exception:  # noqa: BLE001
                ok = False
        if not ok:
            return Response("unauthorised", status_code=401, headers={"WWW-Authenticate": 'Basic realm="atlas"'})
        return await call_next(request)
