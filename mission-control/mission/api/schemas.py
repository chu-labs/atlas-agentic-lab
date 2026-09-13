from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class GateApproveIn(BaseModel):
    pr: int


class GateRejectIn(BaseModel):
    pr: int
    reason: str = Field(min_length=1, max_length=2000)


class ReplayIn(BaseModel):
    name: str
    speed: float = 1.0


class RecordingIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    since_event_id: int = 0
    events: list[dict] | None = None  # upload a recording captured elsewhere (labctl record files)


class InjectIn(BaseModel):
    """One EventBridge-shaped event, or several. Used by scripts/demo_feed.py."""

    events: list[dict[str, Any]] | None = None
    source: str | None = None
    detail_type: str | None = Field(default=None, alias="detail-type")
    time: str | None = None
    detail: dict[str, Any] | None = None

    model_config = {"populate_by_name": True}

    def as_events(self) -> list[dict]:
        if self.events is not None:
            return self.events
        return [{"source": self.source, "detail-type": self.detail_type, "time": self.time, "detail": self.detail or {}}]


class AssignIn(BaseModel):
    handle: str | None = Field(default=None, max_length=40)


class TransitionIn(BaseModel):
    status: str
    body: str | None = None


class BoardIssueIn(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    description: str = ""
    type: str = "Bug"
    priority: str = "Medium"
    assignee: str | None = None
    status: str | None = None
    labels: list[str] | None = None
