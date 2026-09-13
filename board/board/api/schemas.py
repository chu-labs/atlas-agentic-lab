"""Request bodies. Responses are plain dicts shaped in the repository layer."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Status = Literal["Backlog", "Triage", "In Progress", "In Review", "Done"]
Priority = Literal["Highest", "High", "Medium", "Low", "Lowest"]
IssueType = Literal["Bug", "Story", "Task", "Incident"]


class ActorBody(BaseModel):
    actor: str | None = Field(None, description="Handle of the acting user. Alternative to the X-Actor header.")


class UserIn(ActorBody):
    handle: str = Field(min_length=1, max_length=40, pattern=r"^[a-z0-9_-]+$")
    display_name: str
    kind: Literal["human", "agent"]
    avatar: str = "🙂"
    color: str = "#6b7280"
    remit: str = ""
    authority: dict | None = None
    mode: Literal["autonomous", "supervised"] | None = None


class IssueIn(ActorBody):
    type: IssueType
    title: str = Field(min_length=1, max_length=240)
    description: str = ""
    status: Status = "Backlog"
    priority: Priority = "Medium"
    assignee: str | None = None
    labels: list[str] = []
    story_points: int | None = Field(None, ge=0, le=100)
    sprint_id: int | None = Field(None, description="Defaults to the active sprint when omitted; -1 for none")
    pr_url: str | None = None
    branch: str | None = None
    source: dict | None = None


class IssuePatch(ActorBody):
    title: str | None = Field(None, min_length=1, max_length=240)
    description: str | None = None
    priority: Priority | None = None
    labels: list[str] | None = None
    story_points: int | None = Field(None, ge=0, le=100)
    sprint_id: int | None = None
    pr_url: str | None = None
    branch: str | None = None
    assignee: str | None = None


class TransitionIn(ActorBody):
    status: Status
    body: str | None = None


class BodyIn(ActorBody):
    body: str = Field(min_length=1)


class EscalateIn(ActorBody):
    body: str = Field(min_length=1)
    to: str
