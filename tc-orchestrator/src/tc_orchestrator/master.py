"""TC ENGINEERING AI master facade."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any

from .delegation import DelegationManager
from .engineering.catalog import discover
from .mission import MissionController, MissionReport


@dataclass
class TCMaster:
    delegator: DelegationManager

    @classmethod
    def create(cls, root: str | None = None) -> "TCMaster":
        return cls(DelegationManager(root=root))

    def capabilities(self) -> list[dict[str, Any]]:
        return [c.__dict__ for c in discover()]

    def delegate(self, objective: str, workspace: str, **kwargs: Any) -> MissionReport:
        return MissionController(self.delegator).prepare(objective, workspace, kwargs or None)
