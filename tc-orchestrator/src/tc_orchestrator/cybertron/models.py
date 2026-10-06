"""Shared Cybertron data models: task, stages, events, report."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class Stage(StrEnum):
    ORIENT = "ORIENT"
    PLAN = "PLAN"
    APPROVE = "APPROVE"
    ACT = "ACT"
    OBSERVE = "OBSERVE"
    VERIFY = "VERIFY"
    REVIEW = "REVIEW"
    REPAIR = "REPAIR"
    REPORT = "REPORT"


class FinalStatus(StrEnum):
    SUCCESS = "SUCCESS"    # verification + review passed with evidence
    PARTIAL = "PARTIAL"    # some objectives met; evidence shows gaps
    FAILED = "FAILED"      # verification failed or execution failed
    BLOCKED = "BLOCKED"    # approval denied/expired or budget exhausted


class CapabilityLevel(StrEnum):
    L0 = "L0"  # safe read-only inspection
    L1 = "L1"  # search / context
    L2 = "L2"  # patch / edit
    L3 = "L3"  # tests / build / static checks
    L4 = "L4"  # controlled shell execution
    L5 = "L5"  # git write operations (strongest approval)


class EngineeringTask(BaseModel):
    """The task contract TC uses to invoke Cybertron."""

    task_id: str
    objective: str = Field(min_length=1, max_length=20_000)
    workspace_path: str
    project_id: str | None = None
    constraints: list[str] = Field(default_factory=list)
    verification_commands: list[list[str]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskEvent(BaseModel):
    seq: int
    ts: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    stage: Stage
    event_type: str
    detail: dict[str, Any] = Field(default_factory=dict)


class ActionOutcome(BaseModel):
    """Structured, truthful result of one executed action."""

    action_kind: str
    tool: str
    ok: bool
    exit_code: int | None = None
    summary: str = ""
    stdout_tail: str = ""
    stderr_tail: str = ""
    truncated: bool = False
    duration_ms: int = 0
    error: str | None = None


class VerificationCheck(BaseModel):
    argv: list[str]
    ok: bool
    exit_code: int | None = None
    status: str = "completed"
    stdout_tail: str = ""
    stderr_tail: str = ""
    duration_ms: int = 0


class VerificationReport(BaseModel):
    passed: bool
    checks: list[VerificationCheck] = Field(default_factory=list)
    reason: str = ""

    @property
    def evidence_lines(self) -> list[str]:
        return [
            f"{'PASS' if c.ok else 'FAIL'} exit={c.exit_code} {' '.join(c.argv)}"
            for c in self.checks
        ]


class ReviewFinding(BaseModel):
    severity: str  # "info" | "warning" | "blocking"
    category: str
    message: str


class ReviewReport(BaseModel):
    approved: bool
    reviewer: str
    findings: list[ReviewFinding] = Field(default_factory=list)
    summary: str = ""


class TaskReport(BaseModel):
    """The structured result returned to TC for Cybertron.execute(task)."""

    task_id: str
    status: FinalStatus
    summary: str
    changed_files: list[str] = Field(default_factory=list)
    verification: VerificationReport | None = None
    review: ReviewReport | None = None
    errors: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    usage: dict[str, Any] = Field(default_factory=dict)
    stages_completed: list[Stage] = Field(default_factory=list)
    events: list[TaskEvent] = Field(default_factory=list)
