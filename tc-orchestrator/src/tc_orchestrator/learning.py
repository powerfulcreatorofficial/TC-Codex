"""Deterministic engineering lessons derived from observable task evidence.

This is intentionally a small, auditable self-improvement foundation. Lessons
are generated only from persisted task state/events; no hidden model judgment
is involved. Future TC iterations can consume these lessons as context.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .evaluation import evaluate_task
from .models import TaskSummary, TaskStatus


@dataclass(frozen=True)
class Learning:
    category: str
    lesson: str
    evidence: str
    score: int


def derive_learnings(summary: TaskSummary, events: Iterable[dict[str, Any]]) -> list[Learning]:
    event_list = list(events)
    evaluation = evaluate_task(summary, event_list)
    learnings: list[Learning] = []

    if summary.status == TaskStatus.COMPLETED and evaluation.verification_signals > 0:
        learnings.append(
            Learning(
                category="verification",
                lesson="Treat completion as verified only after observable test/build/verification evidence is present.",
                evidence=f"task={summary.task_id} verification_signals={evaluation.verification_signals}",
                score=evaluation.overall_score,
            )
        )

    if summary.status == TaskStatus.COMPLETED and evaluation.repair_signals > 0:
        learnings.append(
            Learning(
                category="repair",
                lesson="When execution reveals a failure, inspect the concrete failure output, make a targeted repair, and rerun verification.",
                evidence=f"task={summary.task_id} repair_signals={evaluation.repair_signals}",
                score=evaluation.overall_score,
            )
        )

    if summary.status == TaskStatus.FAILED:
        learnings.append(
            Learning(
                category="failure",
                lesson="Do not claim success after a failed task; preserve the failure reason and use it to guide the next attempt.",
                evidence=f"task={summary.task_id} error={summary.error or 'unknown failure'}",
                score=evaluation.overall_score,
            )
        )

    if summary.status == TaskStatus.COMPLETED and summary.steps >= 8:
        learnings.append(
            Learning(
                category="efficiency",
                lesson="Prefer small, verified engineering steps and avoid repeating identical tool actions without new evidence.",
                evidence=f"task={summary.task_id} steps={summary.steps}",
                score=evaluation.overall_score,
            )
        )

    return learnings
