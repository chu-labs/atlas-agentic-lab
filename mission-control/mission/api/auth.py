"""Shared basic-auth credential for the whole lab. /health stays open for the ALB; /ws uses tokens."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from ..settings import settings

OPEN_PATHS = {"/health", "/ws"}
WS_TOKEN_TTL = 300


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


def _sign(exp: int) -> str:
    return hmac.new(settings().signing_secret.encode(), str(exp).encode(), hashlib.sha256).hexdigest()


def make_ws_token(ttl: int = WS_TOKEN_TTL, now: float | None = None) -> str:
    """`<expiry>.<hmac>`: handed out behind basic auth, checked on the WebSocket handshake."""
    exp = int((now or time.time()) + ttl)
    return f"{exp}.{_sign(exp)}"


def verify_ws_token(token: str | None, now: float | None = None) -> bool:
    if not token or "." not in token:
        return False
    exp_s, _, sig = token.partition(".")
    if not exp_s.isdigit():
        return False
    exp = int(exp_s)
    if exp < (now or time.time()):
        return False
    return hmac.compare_digest(sig, _sign(exp))
