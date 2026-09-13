"""Small local state file: the clean baseline and what is currently injected."""
from __future__ import annotations

import json

from .config import LOCAL_CFG

STATE = LOCAL_CFG / "state.json"


def load() -> dict:
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def save(**kv) -> dict:
    d = load()
    d.update(kv)
    LOCAL_CFG.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(d, indent=2, default=str))
    return d
