"""Derived state: fleet, pipeline, gate and telemetry, all folded from the event stream.

Pure and synchronous. `apply()` takes one normalised event and returns the follow-up events the
dashboard itself should emit (today: `human.gate_waiting`). The hub owns persistence, the
WebSocket fan-out and the bus; this module owns only the rules in docs/EVENTS.md.
"""
from __future__ import annotations

import re
import threading
from datetime import UTC, datetime, timedelta
from typing import Any

from .fleet import FLEET, TEAMMATE_AVATARS

STAGES = ["error", "triage", "ticket", "code", "test", "pr", "human_gate", "merge", "deploy", "verify", "closed"]
ORDER = {s: i for i, s in enumerate(STAGES)}
TELEMETRY_FIELDS = ("tokens_in", "tokens_out", "model_calls", "seconds", "usd")
TICKET_KEY = re.compile(r"^[A-Z][A-Z0-9]*-\d+$")
SIGNAL_WINDOW = timedelta(minutes=10)
SIGNAL_BUCKET = 30  # seconds per sparkline bucket
# Duration segments shown under each ticket row: (name, start stage, end stage). Triage starts at the first error.
SEGMENTS = [
    ("triage", "error", "ticket"),
    ("code", "code", "pr"),
    ("review", "pr", "human_gate"),
    ("gate", "human_gate", "merge"),
    ("deploy", "merge", "deploy"),
    ("verify", "deploy", "closed"),
]
HUMAN_SEGMENTS = {"gate"}


def is_ticket_key(value: Any) -> bool:
    """Real board keys only. Agents also use pseudo-tickets such as Scout's "triage" for telemetry."""
    return isinstance(value, str) and bool(TICKET_KEY.match(value))


def error_signature(d: dict) -> str | None:
    """The platform's signature, or the same fallback Scout uses when it is missing."""
    sig = d.get("signature")
    if sig:
        return str(sig)
    if d.get("endpoint") or d.get("error_type"):
        return f"{d.get('endpoint')}:{d.get('error_type')}"
    return None


def incident_signature(d: dict) -> str | None:
    issue = d.get("issue") or {}
    source = issue.get("source") or {}
    return (d.get("incident") or {}).get("signature") or source.get("signature") or issue.get("signature") or d.get("signature")


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
            self.rows: dict[str, dict] = {}  # ticket -> pipeline row. Tickets only; errors live in the signal.
            self.errors: list[dict] = []  # every error.raised in the last SIGNAL_WINDOW (for the rate sparkline)
            self.untracked: dict[str, dict] = {}  # signature -> bucket of errors no open ticket has claimed
            self.triage_since: datetime | None = None  # Scout started working before a ticket existed
            self.gate: dict = {"waiting": False, "pr": None, "ticket": None, "since": None}
            self.gate_notified: set[int] = set()
            self.telemetry: dict[str, dict] = {}  # ticket -> {"agents": {handle: {...}}}
            self.pseudo_telemetry: dict[str, dict] = {}  # handle -> telemetry reported on a pseudo-ticket
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
                "signature": signature,
            }
            self.rows[ticket] = row
            self._attach_untracked(row, signature)
        elif signature and not row.get("signature"):
            row["signature"] = signature
            self._attach_untracked(row, signature)
        if title and not row["title"]:
            row["title"] = title
        return row

    def _open_ticket_rows(self) -> list[dict]:
        return [r for r in self.rows.values() if r["stage"] != "closed"]

    @staticmethod
    def _row_signature(row: dict) -> str | None:
        return row.get("signature") or (row.get("error") or {}).get("signature")

    def _attach_untracked(self, row: dict, signature: str | None) -> None:
        """Fold the untracked errors with this signature into the ticket row: count, first seen, triage start.

        With no signature to match on, or when nothing matched and this is the only open ticket,
        every untracked bucket is taken: the errors that started all this belong to this ticket.
        """
        keys = [k for k, b in self.untracked.items() if signature is None or b["signature"] == signature]
        if not keys and len(self._open_ticket_rows()) == 1:
            keys = list(self.untracked)
        if not keys:
            return
        taken = [self.untracked.pop(k) for k in keys]
        first = min(taken, key=lambda b: b["first_ts"])
        count = sum(b["count"] for b in taken) + (row.get("error") or {}).get("count", 0)
        row["error"] = {
            "signature": self._row_signature(row) or first["signature"],
            "endpoint": first.get("endpoint"),
            "error_type": first.get("error_type"),
            "message": first.get("message"),
            "count": count,
            "first_seen": first["first_ts"],
        }
        row.setdefault("signature", row["error"]["signature"])
        if "error" not in row["stages"] or first["first_ts"] < row["stages"]["error"]:
            row["stages"]["error"] = first["first_ts"]
        row["first_ts"] = min(row["first_ts"], first["first_ts"])
        if self.triage_since and self.triage_since >= row["first_ts"]:
            row["stages"]["triage"] = min(self.triage_since, row["stages"].get("triage") or self.triage_since)
        self.triage_since = None

    def _absorb_orphans(self) -> None:
        """Any untracked bucket whose signature now belongs to an open ticket is folded into that ticket."""
        for key in list(self.untracked):
            bucket = self.untracked.get(key)
            if not bucket:
                continue
            owner = next((r for r in self._open_ticket_rows() if self._row_signature(r) == bucket["signature"]), None)
            if owner is not None:
                self._attach_untracked(owner, bucket["signature"])

    def _count_error(self, row: dict, d: dict, ts: datetime, sig: str | None) -> None:
        """One more error.raised on a ticket that already owns this signature."""
        if not row.get("error"):
            row["error"] = {"signature": sig, "endpoint": d.get("endpoint"), "error_type": d.get("error_type"),
                            "message": d.get("message"), "count": 0, "first_seen": ts}
        row["error"]["count"] += 1
        row["error"]["last_seen"] = max(row["error"].get("last_seen") or ts, ts)
        if ts < row["error"]["first_seen"]:
            row["error"]["first_seen"] = ts
        if "error" not in row["stages"] or ts < row["stages"]["error"]:
            row["stages"]["error"] = ts
        row["first_ts"] = min(row["first_ts"], ts)
        row["updated_ts"] = max(row["updated_ts"], ts)

    def _record_error(self, d: dict, ts: datetime, sig: str | None) -> None:
        self.errors.append({"ts": ts, "signature": sig, "message": d.get("message"), "endpoint": d.get("endpoint"),
                            "error_type": d.get("error_type"), "status_code": d.get("status_code"), "method": d.get("method")})
        cutoff = ts - SIGNAL_WINDOW
        if len(self.errors) > 5000 or (self.errors and self.errors[0]["ts"] < cutoff - SIGNAL_WINDOW):
            self.errors = [x for x in self.errors if x["ts"] >= cutoff]

    def _prune_signal(self, now: datetime) -> None:
        cutoff = now - SIGNAL_WINDOW
        self.errors = [x for x in self.errors if x["ts"] >= cutoff]
        for k in [k for k, b in self.untracked.items() if b["last_ts"] < cutoff - SIGNAL_WINDOW]:
            self.untracked.pop(k, None)

    @staticmethod
    def _enter(row: dict, stage: str, ts: datetime, *, back: bool = False) -> None:
        if back or ORDER[stage] > ORDER[row["stage"]]:
            row["stage"] = stage
            row["stages"][stage] = ts
        row["stages"].setdefault(stage, ts)

    def _resolve_ticket(self, e: dict) -> str | None:
        """Ticket from the event, else by PR number, else the most recent row that is past the PR stage."""
        if is_ticket_key(e.get("ticket")):
            return e["ticket"]
        pr = (e["detail"].get("pr") or {}).get("number")
        if pr is not None:
            for row in self.rows.values():
                if row.get("pr") and row["pr"].get("number") == pr:
                    return row["ticket"]
        if e["detail_type"] in {"deploy.completed", "pr.merged", "verify.passed", "verify.failed", "ticket.closed"}:
            candidates = [r for r in self._open_ticket_rows() if ORDER[r["stage"]] >= ORDER["pr"]]
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
                sig = error_signature(d)
                self._record_error(d, ts, sig)
                row = next((r for r in self._open_ticket_rows() if self._row_signature(r) == sig), None)
                if row is not None:
                    self._count_error(row, d, ts, sig)
                else:
                    bucket = self.untracked.get(sig or "")
                    if bucket is None:
                        self.untracked[sig or ""] = bucket = {
                            "signature": sig, "count": 0, "first_ts": ts, "last_ts": ts,
                            "message": d.get("message"), "endpoint": d.get("endpoint"), "error_type": d.get("error_type"),
                            "status_code": d.get("status_code"), "method": d.get("method"),
                        }
                    bucket["count"] += 1
                    bucket["first_ts"] = min(bucket["first_ts"], ts)
                    if ts >= bucket["last_ts"]:
                        bucket.update(last_ts=ts, message=d.get("message") or bucket["message"])
                self._absorb_orphans()
            elif src == "atlas.scout" and kind == "agent.status" and d.get("status") == "working" and not ticket:
                if self.untracked and self.triage_since is None:
                    self.triage_since = ts
                self._absorb_orphans()
            elif kind in {"incident.opened", "issue.created"} and ticket:
                issue = d.get("issue") or {}
                row = self._row(ticket, ts, issue.get("title"), incident_signature(d))
                if src == "atlas.scout":
                    row["stages"].setdefault("triage", ts)
                self._enter(row, "ticket", ts)
                row["updated_ts"] = max(row["updated_ts"], ts)
                self._absorb_orphans()
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
            card["ticket"] = ticket  # pseudo-tickets such as "triage" never reach here
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
        if not handle:
            return
        if ticket:
            per = self.telemetry.setdefault(ticket, {"agents": {}})["agents"].setdefault(handle, dict.fromkeys(TELEMETRY_FIELDS, 0))
            parked = self.pseudo_telemetry.pop(handle, None)  # e.g. Scout's "triage" spend belongs to this ticket
            if parked:
                for k in TELEMETRY_FIELDS:
                    per[k] = max(per[k], parked[k])
        elif e.get("ticket") and isinstance(tel, dict):  # a pseudo-ticket: park it
            per = self.pseudo_telemetry.setdefault(handle, dict.fromkeys(TELEMETRY_FIELDS, 0))
        else:
            return
        if not isinstance(tel, dict):
            return
        for k in TELEMETRY_FIELDS:
            try:
                per[k] = max(per[k], float(tel.get(k) or 0))
            except (TypeError, ValueError):
                pass

    # ------------------------------------------------------------ reads

    def active_ticket(self) -> str | None:
        with self.lock:
            open_rows = self._open_ticket_rows()
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

    @staticmethod
    def durations(row: dict, now: datetime) -> dict:
        """Per-segment seconds under the chain. The running segment is measured to `now`.

        Human time is the gate; everything else is machine time. Escalated tickets freeze at
        their last event; closed ones at close.
        """
        st = row["stages"]
        frozen = row["closed_ts"] or (row["updated_ts"] if row["escalated"] else None)
        end_of_world = frozen or now
        first_error = st.get("error") or row["first_ts"]
        out: dict = {"segments": {}, "open_segment": None}
        for name, start_key, end_key in SEGMENTS:
            start = first_error if start_key == "error" else st.get(start_key)
            if start is None:
                continue
            end = st.get(end_key)
            if end is None:
                if out["open_segment"] is None and frozen is None and row["stage"] != "closed":
                    out["open_segment"] = name
                end = end_of_world
            out["segments"][name] = max(0.0, (end - start).total_seconds())
        total = max(0.0, (end_of_world - first_error).total_seconds())
        human = sum(v for k, v in out["segments"].items() if k in HUMAN_SEGMENTS)
        out.update(total=total, human=human, machine=max(0.0, total - human), frozen=frozen is not None)
        return out

    def signal(self, now: datetime) -> dict:
        """The production signal strip: error rate over the last 10 minutes, untracked errors, latest one."""
        with self.lock:
            self._prune_signal(now)
            n = int(SIGNAL_WINDOW.total_seconds() // SIGNAL_BUCKET)
            buckets = [0] * n
            for x in self.errors:
                i = int((now - x["ts"]).total_seconds() // SIGNAL_BUCKET)
                if 0 <= i < n:
                    buckets[n - 1 - i] += 1
            latest = max(self.untracked.values(), key=lambda b: b["last_ts"], default=None)
            last_minute = sum(1 for x in self.errors if (now - x["ts"]).total_seconds() < 60)
            return {
                "rate": buckets,
                "bucket_seconds": SIGNAL_BUCKET,
                "total_10m": len(self.errors),
                "per_minute": last_minute,
                "untracked_count": sum(b["count"] for b in self.untracked.values()),
                "untracked_signatures": len(self.untracked),
                "latest": {**latest, "first_ts": iso(latest["first_ts"]), "last_ts": iso(latest["last_ts"])} if latest else None,
                "triage_since": iso(self.triage_since),
            }

    def snapshot(self, baselines: dict | None = None, now: datetime | None = None) -> dict:
        now = now or datetime.now(UTC)
        with self.lock:
            rows = sorted(self.rows.values(), key=lambda r: r["updated_ts"], reverse=True)[:12]
            pipeline = []
            for r in rows:
                err = r.get("error")
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
                        "error": {**err, "first_seen": iso(err.get("first_seen")), "last_seen": iso(err.get("last_seen"))} if err else None,
                        "signature": self._row_signature(r),
                        "first_ts": iso(r["first_ts"]),
                        "updated_ts": iso(r["updated_ts"]),
                        "closed_ts": iso(r["closed_ts"]),
                        "closed": r["stage"] == "closed",
                        "durations": self.durations(r, now),
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
                "signal": self.signal(now),
                "baselines": baselines or {},
                "replaying": replaying,
                "last_event_id": self.last_event_id,
            }
