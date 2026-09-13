"""Anthropic calls with per-ticket usage accounting."""
from __future__ import annotations

import json
import logging
import time
from functools import lru_cache

from .config import config

log = logging.getLogger(__name__)

# USD per million tokens, used for the dashboard's cost-per-ticket figure.
PRICES = {"claude-sonnet-5": (3.0, 15.0), "claude-opus-5": (15.0, 75.0), "claude-haiku-4-5-20251001": (1.0, 5.0)}


@lru_cache
def client():
    import anthropic

    return anthropic.Anthropic(api_key=config().anthropic_api_key)


def ask(system: str, user: str, *, emitter=None, ticket: str | None = None, max_tokens: int = 2000, json_mode: bool = False) -> str:
    model = config().model
    t0 = time.perf_counter()
    msg = client().messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user + ("\n\nRespond with a single JSON object and nothing else." if json_mode else "")}],
    )
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    secs = time.perf_counter() - t0
    pin, pout = PRICES.get(model, (3.0, 15.0))
    usd = (msg.usage.input_tokens * pin + msg.usage.output_tokens * pout) / 1_000_000
    log.info("llm", extra={"model": msg.model, "in": msg.usage.input_tokens, "out": msg.usage.output_tokens, "secs": round(secs, 2), "usd": round(usd, 4)})
    if emitter is not None and ticket:
        emitter.add_telemetry(ticket, tokens_in=msg.usage.input_tokens, tokens_out=msg.usage.output_tokens, model_calls=1, seconds=secs, usd=usd)
    return text


def _extract_json(text: str) -> dict | None:
    """The last complete JSON object in `text`, tolerating code fences and surrounding prose."""
    text = text.replace("```json", "```").replace("```", "")
    end = text.rfind("}")
    if end == -1:
        return None
    depth = 0
    for i in range(end, -1, -1):
        if text[i] == "}":
            depth += 1
        elif text[i] == "{":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[i : end + 1])
                except json.JSONDecodeError:
                    return None
    return None


def ask_json(system: str, user: str, **kw) -> dict:
    """Ask for a JSON object; retry once with a blunt reminder if the model answered in prose."""
    text = ask(system, user, json_mode=True, **kw)
    out = _extract_json(text)
    if out is None:
        log.warning("model did not return JSON; retrying once", extra={"head": text[:200]})
        text = ask(system, user + "\n\nYour previous reply was not a JSON object. Reply with ONLY the JSON object, no prose, no code fences.", json_mode=True, **kw)
        out = _extract_json(text)
    if out is None:
        raise ValueError("model returned no JSON object: " + text[:300])
    return out
