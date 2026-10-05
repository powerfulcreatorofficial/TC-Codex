"""Protocol objects for delegated engineering-agent work.

The delegated-agent layer deliberately separates task ownership from execution.
A worker receives a bounded task packet and must return evidence; it never
changes TC's architectural policy or approval rules.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any
from uuid import uuid4


class AgentKind(StrEnum):
    PRIMARY_CODER = "primary_coder"
    REPOSITORY_CODER = "repository_coder"
    RESEARCHER = "researcher"
    TESTER = "tester"
    UI_ENGINEER = "ui_engineer"
    SCIENTIFIC_SPECIALIST = "scientific_specialist"
    REVIEWER = "reviewer"


@dataclass(frozen=True)
class AgentCapability:
    kind: AgentKind
    label: str
    description: str
    endpoint: str | None = None
    command: list[str] | None = None
    enabled: bool = True


@dataclass
class DelegationTask:
    objective: str
    agent_kind: AgentKind
    workspace: str
    constraints: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)
    task_id: str = field(default_factory=lambda: uuid4().hex)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DelegationResult:
    task_id: str
    status: str
    summary: str
    changed_files: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    tests: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    worker: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
