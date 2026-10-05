"""Evidence-based task execution evaluation.

This module intentionally evaluates execution quality from persisted task state
and event metadata. It does not claim to judge answer quality semantically.
It is a deterministic foundation for the future TC self-improvement loop.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .models import TaskStatus, TaskSummary


@dataclass(frozen=True)
class EvaluationDimension:
    key: str
    label: str
    score: int
    evidence: str


@dataclass(frozen=True)
class TaskEvaluation:
    task_id: str
    overall_score: int
    verdict: str
    dimensions: tuple[EvaluationDimension, ...]
    total_events: int
    approvals_requested: int
    approvals_decided: int
    repair_signals: int
    verification_signals: int


def _has_verification_signal(event: dict[str, Any]) -> bool:
    if event.get("event_type") in {"task_completed", "verification_passed", "task_verified"}:
        return True
    tool = str(event.get("tool_name") or "").lower()
    if any(token in tool for token in ("test", "build", "verify", "pytest", "check")):
        return True
    text = repr(event.get("result_metadata") or {}).lower()
    return any(token in text for token in ("pytest", "tests passed", "build passed", "verified"))


def _has_repair_signal(event: dict[str, Any]) -> bool:
    tool = str(event.get("tool_name") or "").lower()
    if any(token in tool for token in ("edit", "repair", "fix", "patch", "write")):
        return True
    event_type = str(event.get("event_type") or "").lower()
    return any(token in event_type for token in ("repair", "fixed"))


def evaluate_task(summary: TaskSummary, events: Iterable[dict[str, Any]]) -> TaskEvaluation:
    event_list = list(events)
    approvals_requested = sum(1 for e in event_list if e.get("event_type") == "approval_requested")
    approvals_decided = sum(1 for e in event_list if e.get("event_type") == "approval_decided")
    verification_signals = sum(1 for e in event_list if _has_verification_signal(e))
    repair_signals = sum(1 for e in event_list if _has_repair_signal(e))

    completion_score = 100 if summary.status == TaskStatus.COMPLETED else 25 if summary.status != TaskStatus.FAILED else 0
    verification_score = 100 if verification_signals >= 2 else 70 if verification_signals == 1 else 0
    control_score = 100 if approvals_requested == approvals_decided else 50 if approvals_requested == 0 else 0
    steps = max(1, summary.steps or summary.current_step or 1)
    efficiency_score = max(40, 100 - max(0, steps - 1) * 4)

    overall = round(
        completion_score * 0.40
        + verification_score * 0.30
        + control_score * 0.15
        + efficiency_score * 0.15
    )
    overall = max(0, min(100, overall))

    if summary.status == TaskStatus.COMPLETED and overall >= 85:
        verdict = "strong"
    elif summary.status == TaskStatus.COMPLETED:
        verdict = "complete"
    elif summary.status == TaskStatus.AWAITING_APPROVAL:
        verdict = "in_progress"
    else:
        verdict = "failed"

    dimensions = (
        EvaluationDimension("completion", "Completion", completion_score, "Task terminal status is COMPLETED." if completion_score == 100 else "Task did not reach COMPLETED."),
        EvaluationDimension("verification", "Verification", verification_score, f"{verification_signals} verification signal(s) found in task events."),
        EvaluationDimension("control", "Control compliance", control_score, f"{approvals_decided}/{approvals_requested} approval decision(s) resolved."),
        EvaluationDimension("efficiency", "Step efficiency", efficiency_score, f"Execution used {steps} agent step(s)."),
    )

    return TaskEvaluation(
        task_id=summary.task_id,
        overall_score=overall,
        verdict=verdict,
        dimensions=dimensions,
        total_events=len(event_list),
        approvals_requested=approvals_requested,
        approvals_decided=approvals_decided,
        repair_signals=repair_signals,
        verification_signals=verification_signals,
    )
