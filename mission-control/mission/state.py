"""Derived state: fleet, pipeline, gate and telemetry, all folded from the event stream.

Pure and synchronous. `apply()` takes one normalised event and returns the follow-up events the
dashboard itself should emit (today: `human.gate_waiting`). The hub owns persistence, the
WebSocket fan-out and the bus; this module owns only the rules in docs/EVENTS.md.
"""
from __future__ import annotations

import threading
from datetime import UTC, datetime
from typing import Any

from .fleet import FLEET, TEAMMATE_AVATARS

STAGES = ["error", "triage", "ticket", "code", "test", "pr", "human_gate", "merge", "deploy", "verify", "closed"]
ORDER = {s: i for i, s in enumerate(STAGES)}
TELEMETRY_FIELDS = ("tokens_in", "tokens_out", "model_calls", "seconds", "usd")
PENDING = "__pending__"  # prefix of pipeline rows for errors no ticket has claimed yet (one per signature)


def is_pending(key: str) -> bool:
    return key.startswith(PENDING)


def parse_ts(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(UTC)


def iso(dt: datetime | None) -> str | None:
    return dt.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z") if dt else None


def normalise(raw: dict, *, replay: bool = False, event_id: int | None = None, received_at=None) -> dict:
    """An EventBridge-shaped message ({source, detail-type, time, detail}) -> the flat record we store."""
    detail = raw.get("detail") or {}
    if isinstance(detail, str):
        import json

        detail = json.loads(detail)
    return {
        "id": event_id,
        "received_at": received_at,
        "ts": parse_ts(detail.get("ts") or raw.get("time")),
        "source": raw.get("source") or "unknown",
        "detail_type": raw.get("detail-type") or raw.get("detail_type") or "unknown",
        "ticket": detail.get("ticket"),
        "actor": detail.get("actor"),
        "summary": detail.get("summary") or "",
        "detail": detail,
        "replay": replay,
    }


def _fleet_card(d: dict) -> dict:
    return {
        **d,
        "kind": "fleet",
        "status": "idle",
        "thinking": "",
        "ticket": None,
        "last_seen": None,
    }


class State:
    def __init__(self):
        self.lock = threading.RLock()
        self.reset()

    # ------------------------------------------------------------ lifecycle

    def reset(self) -> None:
        with self.lock:
            self.fleet: dict[str, dict] = {d["handle"]: _fleet_card(d) for d in FLEET}
            self.rows: dict[str, dict] = {}  # ticket -> pipeline row (plus PENDING)
            self.gate: dict = {"waiting": False, "pr": None, "ticket": None, "since": None}
            self.gate_notified: set[int] = set()
            self.telemetry: dict[str, dict] = {}  # ticket -> {"agents": {handle: {...}}}
            self.queues: dict[str, int] = {}
            self.last_event_id: int = 0
            self.last_replay_at: datetime | None = None

    # ------------------------------------------------------------ helpers

    def _row(self, ticket: str, ts: datetime, title: str | None = None, signature: str | None = None) -> dict:
        row = self.rows.get(ticket)
        if row is None:
            row = {
                "ticket": ticket,
                "title": title or "",
                "stage": "ticket",
                "stages": {},
                "escalated": False,
                "escalation": None,
                "verify_failed": False,
                "pr": None,
                "first_ts": ts,
                "updated_ts": ts,
                "pr_ts": None,
                "closed_ts": None,
            }
            self._attach_pending(row, signature)
            self.rows[ticket] = row
        if title and not row["title"]:
            row["title"] = title
        return row

    def _pending_rows(self) -> list[dict]:
        return [r for k, r in self.rows.items() if is_pending(k)]

    def _attach_pending(self, row: dict, signature: str | None) -> None:
        """Fold every unattached error row with this signature into the new ticket row.

        With no signature on the incident, every pending row is taken: the errors that started
        all this belong to this ticket.
        """
        keys = [k for k, r in self.rows.items() if is_pending(k) and (signature is None or r["error"]["signature"] == signature)]
        if not keys:
            return
        taken = [self.rows.pop(k) for k in keys]
        for p in taken:
            for stage, ts in p["stages"].items():
                if stage not in row["stages"] or ts < row["stages"][stage]:
                    row["stages"][stage] = ts
            row["first_ts"] = min(row["first_ts"], p["first_ts"])
        first = min(taken, key=lambda p: p["first_ts"])
        row["error"] = {**first["error"], "count": sum(p["error"]["count"] for p in taken)}

    @staticmethod
    def _enter(row: dict, stage: str, ts: datetime, *, back: bool = False) -> None:
        if back or ORDER[stage] > ORDER[row["stage"]]:
            row["stage"] = stage
            row["stages"][stage] = ts
        row["stages"].setdefault(stage, ts)

    def _resolve_ticket(self, e: dict) -> str | None:
        """Ticket from the event, else by PR number, else the most recent row that is past the PR stage."""
        if e.get("ticket"):
            return e["ticket"]
        pr = (e["detail"].get("pr") or {}).get("number")
        if pr is not None:
            for row in self.rows.values():
                if row.get("pr") and row["pr"].get("number") == pr:
                    return row["ticket"]
        if e["detail_type"] in {"deploy.completed", "pr.merged", "verify.passed", "verify.failed", "ticket.closed"}:
            candidates = [
                r for k, r in self.rows.items() if not is_pending(k) and r["stage"] != "closed" and ORDER[r["stage"]] >= ORDER["pr"]
            ]
            if candidates:
                return max(candidates, key=lambda r: r["updated_ts"])["ticket"]
        return None

    # ------------------------------------------------------------ apply

    def apply(self, e: dict, *, emit: bool = True) -> list[tuple[str, dict]]:
        """Fold one normalised event in. Returns follow-up (detail_type, detail) pairs to publish."""
        followups: list[tuple[str, dict]] = []
        with self.lock:
            if e.get("id"):
                self.last_event_id = max(self.last_event_id, e["id"])
            if e.get("replay"):
                self.last_replay_at = datetime.now(UTC)
            ts: datetime = e["ts"]
            d: dict = e["detail"] or {}
            src: str = e["source"]
            kind: str = e["detail_type"]
            ticket = self._resolve_ticket(e)

            self._apply_fleet(e, ticket)
            self._apply_telemetry(e, ticket)

            # --- pipeline ------------------------------------------------
            if kind == "error.raised":
                sig = d.get("signature")
                row = next(
                    (
                        r for k, r in self.rows.items()
                        if not is_pending(k) and r["stage"] != "closed" and (r.get("error") or {}).get("signature") == sig
                    ),
                    None,
                ) or self.rows.get(f"{PENDING}{sig or ''}")
                if row is None:
                    self.rows[f"{PENDING}{sig or ''}"] = row = {
                        "ticket": None,
                        "title": d.get("message") or d.get("error_type") or "Production error",
                        "stage": "error",
                        "stages": {"error": ts},
                        "escalated": False,
                        "verify_failed": False,
                        "pr": None,
                        "first_ts": ts,
                        "updated_ts": ts,
                        "error": {"signature": sig, "endpoint": d.get("endpoint"), "count": 0},
                    }
                row["error"]["count"] += 1
                row["updated_ts"] = max(row["updated_ts"], ts)
            elif src == "atlas.scout" and kind == "agent.status" and d.get("status") == "working" and not ticket:
                for row in self._pending_rows():
                    self._enter(row, "triage", ts)
                    row["updated_ts"] = ts
            elif kind in {"incident.opened", "issue.created"} and ticket:
                issue = d.get("issue") or {}
                signature = (d.get("incident") or {}).get("signature") or (d.get("issue") or {}).get("signature")
                row = self._row(ticket, ts, issue.get("title"), signature)
                if src == "atlas.scout":
                    row["stages"].setdefault("triage", ts)
                self._enter(row, "ticket", ts)
                row["updated_ts"] = ts
            elif ticket:
                row = self._row(ticket, ts)
                thinking = (d.get("thinking") or "").lower()
                if src == "atlas.forge" and (kind == "branch.created" or (kind == "agent.status" and d.get("status") == "working")):
                    self._enter(row, "code", ts)
                    if "pytest" in thinking:
                        self._enter(row, "test", ts)
                elif src == "atlas.forge" and kind == "agent.thinking" and "pytest" in thinking:
                    self._enter(row, "test", ts)
                elif kind in {"pr.opened", "pr.updated"}:
                    row["pr"] = d.get("pr") or row["pr"]
                    self._enter(row, "pr", ts)
                    if row["pr_ts"] is None:
                        row["pr_ts"] = ts
                elif kind == "review.changes_requested":
                    row["pr"] = d.get("pr") or row["pr"]
                    self._enter(row, "code", ts, back=True)
                    self._clear_gate(row)
                elif kind == "review.posted":
                    row["pr"] = d.get("pr") or row["pr"]
                    self._enter(row, "human_gate", ts)
                    self.gate = {"waiting": True, "pr": row["pr"], "ticket": ticket, "since": ts}
                    number = (row["pr"] or {}).get("number")
                    if emit and number is not None and number not in self.gate_notified:
                        self.gate_notified.add(number)
                        followups.append(
                            (
                                "human.gate_waiting",
                                {
                                    "ticket": ticket,
                                    "pr": row["pr"],
                                    "waited_seconds": 0,
                                    "summary": f"PR #{number} is waiting on a human. Agents cannot merge.",
                                },
                            )
                        )
                elif kind in {"human.approved", "pr.merged"}:
                    self._enter(row, "merge", ts)
                    self._clear_gate(row)
                elif kind == "human.rejected":
                    self._enter(row, "code", ts, back=True)
                    self._clear_gate(row)
                elif kind == "deploy.completed":
                    self._enter(row, "deploy", ts)
                elif kind == "verify.passed":
                    row["verify_failed"] = False
                    self._enter(row, "verify", ts)
                elif kind == "verify.failed":
                    row["verify_failed"] = True
                    self._enter(row, "verify", ts)
                elif kind == "ticket.closed":
                    self._enter(row, "closed", ts)
                    row["closed_ts"] = row["closed_ts"] or ts
                elif kind == "escalation.raised":
                    row["escalated"] = True
                    row["escalation"] = {"summary": e.get("summary"), "category": d.get("category"), "to": d.get("assigned_to")}
                    self._clear_gate(row)
                row["updated_ts"] = max(row["updated_ts"], ts)
        return followups

    def _clear_gate(self, row: dict) -> None:
        if self.gate.get("waiting") and self.gate.get("ticket") == row["ticket"]:
            self.gate = {"waiting": False, "pr": self.gate.get("pr"), "ticket": row["ticket"], "since": None}

    def _apply_fleet(self, e: dict, ticket: str | None) -> None:
        d = e["detail"] or {}
        actor = e.get("actor") or {}
        handle = actor.get("handle")
        ts = e["ts"]
        if e["source"] == "atlas.workbench":
            role = d.get("role") or handle
            if e["detail_type"] == "teammate.spawned" and role:
                self.fleet[f"teammate:{role}"] = {
                    "handle": f"teammate:{role}",
                    "kind": "teammate",
                    "display_name": (d.get("display_name") or role).replace("_", " ").title(),
                    "avatar": TEAMMATE_AVATARS.get(str(role).lower(), "🧑‍💻"),
                    "color": "#e879f9",
                    "remit": f"Workbench teammate ({role}) working in {d.get('worktree') or d.get('branch') or 'a worktree'}.",
                    "mode": "supervised",
                    "authority": {"can_write_code": True, "can_review": False, "can_merge": False, "can_deploy": False,
                                  "can_change_business_rules": False},
                    "status": "working",
                    "thinking": e.get("summary") or "",
                    "ticket": ticket,
                    "last_seen": ts,
                }
            elif e["detail_type"] == "teammate.finished" and role:
                self.fleet.pop(f"teammate:{role}", None)
            return
        if not handle or actor.get("kind") != "agent":
            return
        card = self.fleet.get(handle)
        if card is None:
            return  # unknown agent handles are shown on the timeline but do not get a card
        card["last_seen"] = ts
        if ticket:
            card["ticket"] = ticket
        if d.get("authority"):
            card["authority"] = {**card.get("authority", {}), **d["authority"]}
        if actor.get("mode"):
            card["mode"] = actor["mode"]
        if e["detail_type"] == "agent.status":
            if d.get("status"):
                card["status"] = d["status"]
            card["thinking"] = d.get("thinking") or e.get("summary") or card["thinking"]
        elif e["detail_type"] == "agent.thinking":
            card["thinking"] = d.get("thinking") or e.get("summary") or card["thinking"]
        elif e.get("summary"):
            card["thinking"] = e["summary"]
        if e["detail_type"] == "escalation.raised":
            card["status"] = "escalated"

    def _apply_telemetry(self, e: dict, ticket: str | None) -> None:
        d = e["detail"] or {}
        tel = d.get("telemetry")
        handle = (e.get("actor") or {}).get("handle")
        if not ticket or not isinstance(tel, dict) or not handle:
            return
        per = self.telemetry.setdefault(ticket, {"agents": {}})["agents"].setdefault(handle, dict.fromkeys(TELEMETRY_FIELDS, 0))
        for k in TELEMETRY_FIELDS:
            try:
                per[k] = max(per[k], float(tel.get(k) or 0))
            except (TypeError, ValueError):
                pass

    # ------------------------------------------------------------ reads

    def active_ticket(self) -> str | None:
        with self.lock:
            open_rows = [r for k, r in self.rows.items() if not is_pending(k) and r["stage"] != "closed"]
            if not open_rows:
                return None
            return max(open_rows, key=lambda r: r["updated_ts"])["ticket"]

    def ticket_telemetry(self, ticket: str | None, now: datetime | None = None) -> dict:
        now = now or datetime.now(UTC)
        with self.lock:
            row = self.rows.get(ticket) if ticket else None
            totals = dict.fromkeys(TELEMETRY_FIELDS, 0.0)
            for per in (self.telemetry.get(ticket, {}).get("agents", {}) if ticket else {}).values():
                for k in TELEMETRY_FIELDS:
                    totals[k] += per[k]
            out: dict = {"ticket": ticket, **totals}
            out["tokens_in"], out["tokens_out"], out["model_calls"] = (
                int(totals["tokens_in"]), int(totals["tokens_out"]), int(totals["model_calls"]))
            if row:
                first = row["first_ts"]
                out["first_ts"] = iso(first)
                out["pr_ts"] = iso(row["pr_ts"])
                out["closed_ts"] = iso(row["closed_ts"])
                out["error_to_pr_seconds"] = (row["pr_ts"] - first).total_seconds() if row["pr_ts"] else None
                end = row["closed_ts"] or (row["updated_ts"] if row["escalated"] else now)
                out["error_to_closed_seconds"] = (end - first).total_seconds() if end else None
                out["closed"] = row["closed_ts"] is not None
            return out

    def snapshot(self, baselines: dict | None = None, now: datetime | None = None) -> dict:
        now = now or datetime.now(UTC)
        with self.lock:
            rows = sorted(self.rows.values(), key=lambda r: r["updated_ts"], reverse=True)
            pipeline = []
            for r in rows:
                pipeline.append(
                    {
                        "ticket": r["ticket"],
                        "title": r["title"],
                        "stage": r["stage"],
                        "stages": {k: iso(v) for k, v in r["stages"].items()},
                        "escalated": r["escalated"],
                        "escalation": r.get("escalation"),
                        "verify_failed": r["verify_failed"],
                        "pr": r["pr"],
                        "error": r.get("error"),
                        "first_ts": iso(r["first_ts"]),
                        "updated_ts": iso(r["updated_ts"]),
                        "closed": r["stage"] == "closed",
                    }
                )
            gate = dict(self.gate)
            gate["since"] = iso(gate.get("since"))
            gate["waited_seconds"] = (
                max(0, (now - self.gate["since"]).total_seconds()) if gate["waiting"] and self.gate.get("since") else 0
            )
            active = self.active_ticket()
            fleet = [
                {**c, "last_seen": iso(c["last_seen"])}
                for c in self.fleet.values()
            ]
            replaying = bool(self.last_replay_at and (now - self.last_replay_at).total_seconds() < 15)
            return {
                "now": iso(now),
                "active_ticket": active,
                "fleet": fleet,
                "pipeline": pipeline,
                "gate": gate,
                "telemetry": self.ticket_telemetry(active, now),
                "queues": dict(self.queues),
                "baselines": baselines or {},
                "replaying": replaying,
                "last_event_id": self.last_event_id,
            }
