"""Authority as data. Each agent's defs/<name>.yaml declares what it may do; the code checks it."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .config import DEFS


class AuthorityViolation(Exception):
    def __init__(self, agent: str, action: str, reason: str):
        super().__init__(f"{agent} may not {action}: {reason}")
        self.agent, self.action, self.reason = agent, action, reason


@dataclass(frozen=True)
class AgentDef:
    name: str
    display_name: str
    avatar: str
    color: str
    remit: str
    mode: str  # autonomous | supervised
    authority: dict = field(default_factory=dict)
    model: str | None = None

    def can(self, permission: str) -> bool:
        return bool(self.authority.get(permission, False))

    def require(self, permission: str, action: str) -> None:
        """Raise AuthorityViolation if the permission is not granted. Callers emit the event."""
        if not self.can(permission):
            raise AuthorityViolation(self.name, action, f"authority.{permission} is false")

    def must_escalate(self, condition: str) -> bool:
        return condition in set(self.authority.get("must_escalate_when", []))


def load(name: str, defs: Path = DEFS) -> AgentDef:
    raw = yaml.safe_load((defs / f"{name}.yaml").read_text())
    return AgentDef(**raw)
