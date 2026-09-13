"""WebSocket: token-authenticated, pushes events as they arrive and a state snapshot every 2 s."""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..hub import hub
from .auth import verify_ws_token

log = logging.getLogger(__name__)
router = APIRouter()
STATE_EVERY = 2.0


@router.websocket("/ws")
async def ws(websocket: WebSocket):
    if not verify_ws_token(websocket.query_params.get("token")):
        await websocket.close(code=4401)
        return
    await websocket.accept()
    h = hub()
    q = h.broadcaster.subscribe()
    await websocket.send_text(json.dumps(h.state_message(), default=str))

    async def reader():
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        except Exception:  # noqa: BLE001
            pass

    reader_task = asyncio.create_task(reader())
    try:
        while not reader_task.done():
            try:
                payload = await asyncio.wait_for(q.get(), timeout=STATE_EVERY)
            except TimeoutError:
                payload = json.dumps(h.state_message(), default=str)
            await websocket.send_text(payload)
    except (WebSocketDisconnect, RuntimeError):
        pass
    except Exception:  # noqa: BLE001
        log.exception("websocket send failed")
    finally:
        h.broadcaster.unsubscribe(q)
        reader_task.cancel()
