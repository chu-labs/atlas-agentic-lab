"""HTTP routes. Thin: resolve the actor, call the repository inside one transaction, emit the event."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from .. import domain
from ..db import repo
from ..db.pool import conn
from ..events import emit, envelope
from .schemas import BodyIn, EscalateIn, IssueIn, IssuePatch, TransitionIn, UserIn

router = APIRouter(prefix="/api")


def _actor(c, request: Request, body_actor: str | None) -> dict:
    handle = body_actor or request.headers.get("x-actor")
    if not handle:
        raise HTTPException(400, "actor required: send X-Actor header or `actor` in the body")
    u = repo.get_user(c, handle)
    if not u:
        raise HTTPException(404, f"unknown actor: {handle}")
    return u


def _issue_or_404(c, key: str) -> dict:
    issue = repo.get_issue(c, key)
    if not issue:
        raise HTTPException(404, f"issue not found: {key}")
    return issue


def _user_or_404(c, handle: str) -> dict:
    u = repo.get_user(c, handle)
    if not u:
        raise HTTPException(404, f"unknown user: {handle}")
    return u


def _full_issue(c, issue: dict) -> dict:
    activity = repo.issue_activity(c, issue["id"])
    counts = {k: sum(1 for a in activity if a["kind"] == k) for k in domain.ACTIVITY_KINDS}
    return {
        **issue,
        "activity": activity,
        "comments": repo.issue_comments(c, issue["id"]),
        "counts": counts,
        "allowed_transitions": [s for s in domain.STATUSES if s in domain.allowed_transitions(issue["status"])],
    }


# ---------------------------------------------------------------- users


@router.get("/users")
def list_users():
    with conn() as c:
        return repo.list_users(c)


@router.post("/users", status_code=201)
def upsert_user(body: UserIn):
    with conn() as c:
        return repo.upsert_user(c, body.model_dump(exclude={"actor"}))


@router.get("/users/{handle}")
def get_user(handle: str):
    with conn() as c:
        return _user_or_404(c, handle)


# ---------------------------------------------------------------- issues


@router.get("/issues")
def list_issues(
    status: str | None = None,
    assignee: str | None = None,
    sprint: str | None = None,
    type: str | None = None,  # noqa: A002 - matches the query parameter name
    label: str | None = None,
    q: str | None = None,
    limit: int = Query(200, ge=1, le=1000),
):
    with conn() as c:
        return repo.list_issues(
            c, status=status, assignee=assignee, sprint=sprint, type_=type, label=label, q=q, limit=limit
        )


@router.post("/issues", status_code=201)
def create_issue(body: IssueIn, request: Request):
    with conn() as c:
        actor = _actor(c, request, body.actor)
        assignee = _user_or_404(c, body.assignee) if body.assignee else None
        sprint_id: int | None
        if body.sprint_id is None:
            active = repo.active_sprint(c)
            sprint_id = active["id"] if active else None
        elif body.sprint_id < 0:
            sprint_id = None
        else:
            if not repo.get_sprint(c, body.sprint_id):
                raise HTTPException(404, f"unknown sprint: {body.sprint_id}")
            sprint_id = body.sprint_id
        fields = body.model_dump(exclude={"actor", "assignee", "sprint_id"})
        issue = repo.insert_issue(
            c, {**fields, "assignee_id": assignee["id"] if assignee else None, "reporter_id": actor["id"], "sprint_id": sprint_id}
        )
        repo.add_activity(c, issue["id"], actor["id"], "created", to_value=issue["status"])
        if assignee:
            repo.add_activity(c, issue["id"], actor["id"], "assigned", to_value=assignee["handle"])
    summary = repo.issue_summary(issue)
    emit("issue.created", envelope(actor, summary, f"Opened {issue['key']}: {issue['title']}"))
    if assignee:
        emit(
            "issue.assigned",
            envelope(actor, summary, f"Assigned {issue['key']} to {assignee['display_name']}", to=assignee["handle"]),
        )
    return issue


@router.get("/issues/{key}")
def get_issue(key: str):
    with conn() as c:
        return _full_issue(c, _issue_or_404(c, key))


@router.patch("/issues/{key}")
def patch_issue(key: str, body: IssuePatch, request: Request):
    given = body.model_dump(exclude_unset=True, exclude={"actor"})
    if not given:
        raise HTTPException(400, "nothing to update")
    events: list[tuple[str, dict[str, Any]]] = []
    with conn() as c:
        actor = _actor(c, request, body.actor)
        issue = _issue_or_404(c, key)
        changes: dict[str, Any] = {}
        changed_fields: list[str] = []
        new_assignee = None
        if "assignee" in given:
            handle = given.pop("assignee")
            new_assignee = _user_or_404(c, handle) if handle else None
            old = issue["assignee"]["handle"] if issue["assignee"] else None
            new = new_assignee["handle"] if new_assignee else None
            if old != new:
                changes["assignee_id"] = new_assignee["id"] if new_assignee else None
                repo.add_activity(c, issue["id"], actor["id"], "assigned", from_value=old, to_value=new)
        if "sprint_id" in given and given["sprint_id"] is not None and not repo.get_sprint(c, given["sprint_id"]):
            raise HTTPException(404, f"unknown sprint: {given['sprint_id']}")
        for field, value in given.items():
            if issue.get(field) != value:
                changes[field] = value
                changed_fields.append(field)
                repo.add_activity(
                    c, issue["id"], actor["id"], "field_changed", from_value=_text(issue.get(field)), to_value=_text(value), body=field
                )
        repo.update_issue_fields(c, issue["id"], changes)
        issue = repo.get_issue(c, key)
        summary = repo.issue_summary(issue)
        if "assignee_id" in changes:
            who = new_assignee["display_name"] if new_assignee else "nobody"
            events.append(("issue.assigned", envelope(actor, summary, f"Assigned {key} to {who}", to=summary["assignee"])))
        if changed_fields:
            events.append(
                (
                    "issue.updated",
                    envelope(actor, summary, f"Updated {key}: {', '.join(changed_fields)}", fields=changed_fields),
                )
            )
        result = _full_issue(c, issue)
    for detail_type, detail in events:
        emit(detail_type, detail)
    return result


def _text(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, list):
        return ", ".join(str(x) for x in v)
    return str(v)


@router.post("/issues/{key}/transition")
def transition(key: str, body: TransitionIn, request: Request):
    with conn() as c:
        actor = _actor(c, request, body.actor)
        issue = _issue_or_404(c, key)
        frm, to = issue["status"], body.status
        if frm == to:
            raise HTTPException(409, f"{key} is already {to}")
        if not domain.can_transition(frm, to):
            allowed = sorted(domain.allowed_transitions(frm))
            raise HTTPException(422, f"cannot move {key} from {frm} to {to}; allowed: {allowed}")
        repo.set_status(c, issue["id"], to)
        repo.add_activity(c, issue["id"], actor["id"], "transitioned", from_value=frm, to_value=to, body=body.body)
        issue = repo.get_issue(c, key)
        result = _full_issue(c, issue)
    emit(
        "issue.transitioned",
        envelope(actor, repo.issue_summary(issue), f"Moved {key} from {frm} to {to}", **{"from": frm, "to": to, "body": body.body}),
    )
    return result


@router.post("/issues/{key}/comments", status_code=201)
def comment(key: str, body: BodyIn, request: Request):
    with conn() as c:
        actor = _actor(c, request, body.actor)
        issue = _issue_or_404(c, key)
        r = repo.add_comment(c, issue["id"], actor["id"], body.body)
        result = _full_issue(c, issue)
    first_line = body.body.strip().splitlines()[0][:140]
    emit(
        "issue.commented",
        envelope(actor, repo.issue_summary(issue), f"Commented on {key}: {first_line}", body=body.body, comment_id=r["id"]),
    )
    return result


@router.post("/issues/{key}/reasoning", status_code=201)
def reasoning(key: str, body: BodyIn, request: Request):
    with conn() as c:
        actor = _actor(c, request, body.actor)
        issue = _issue_or_404(c, key)
        repo.add_activity(c, issue["id"], actor["id"], "reasoning", body=body.body)
        return _full_issue(c, issue)


@router.post("/issues/{key}/escalate")
def escalate(key: str, body: EscalateIn, request: Request):
    with conn() as c:
        actor = _actor(c, request, body.actor)
        issue = _issue_or_404(c, key)
        to_user = _user_or_404(c, body.to)
        old_assignee = issue["assignee"]["handle"] if issue["assignee"] else None
        frm = issue["status"]
        repo.add_activity(c, issue["id"], actor["id"], "escalated", from_value=old_assignee, to_value=to_user["handle"], body=body.body)
        repo.update_issue_fields(c, issue["id"], {"assignee_id": to_user["id"]})
        if frm != "Triage":
            repo.set_status(c, issue["id"], "Triage")
            repo.add_activity(c, issue["id"], actor["id"], "transitioned", from_value=frm, to_value="Triage", body="escalated")
        issue = repo.get_issue(c, key)
        result = _full_issue(c, issue)
    summary = repo.issue_summary(issue)
    first_line = body.body.strip().splitlines()[0][:140]
    emit(
        "issue.assigned",
        envelope(actor, summary, f"Escalated {key} to {to_user['display_name']}: {first_line}", to=to_user["handle"], body=body.body, escalation=True),
    )
    emit("issue.updated", envelope(actor, summary, f"{key} moved to Triage pending {to_user['display_name']}", fields=["status", "assignee"], **{"from": frm, "to": "Triage"}))
    return result


# ---------------------------------------------------------------- board / sprints / stats


@router.get("/board")
def board(sprint: str = "active"):
    with conn() as c:
        if sprint == "active":
            sp = repo.active_sprint(c)
        elif sprint == "none":
            sp = None
        else:
            sp = repo.get_sprint(c, int(sprint))
            if not sp:
                raise HTTPException(404, f"unknown sprint: {sprint}")
        issues = repo.board_issues(c, sp["id"] if sp else None)
    columns = [{"status": s, "issues": [i for i in issues if i["status"] == s]} for s in domain.STATUSES]
    return {
        "project": {"key": "ATLAS", "name": "ATLAS"},
        "sprint": sp,
        "columns": columns,
        "counts": {col["status"]: len(col["issues"]) for col in columns},
    }


@router.get("/sprints")
def sprints():
    with conn() as c:
        return repo.list_sprints(c)


@router.get("/stats")
def stats():
    with conn() as c:
        return repo.stats(c)


@router.post("/admin/reset")
def admin_reset():
    from ..db.seed import reset, seed

    reset()
    return seed()
