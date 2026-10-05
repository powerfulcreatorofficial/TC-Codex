"""Explicit task state transitions.

Invalid transitions are rejected. The API cannot set arbitrary states; it must
go through these allowed edges.
"""

from __future__ import annotations

from .models import TaskStatus

# Allowed transitions: from -> {to, ...}.
_ALLOWED: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.PENDING: {TaskStatus.RUNNING, TaskStatus.FAILED},
    TaskStatus.RUNNING: {
        TaskStatus.AWAITING_APPROVAL,
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
    },
    TaskStatus.AWAITING_APPROVAL: {TaskStatus.RUNNING, TaskStatus.FAILED},
    TaskStatus.COMPLETED: set(),
    TaskStatus.FAILED: set(),
}


class InvalidTransition(Exception):
    """Raised when a status change is not allowed."""


def allowed_transitions(from_status: TaskStatus) -> set[TaskStatus]:
    return set(_ALLOWED.get(from_status, set()))


def validate_transition(from_status: TaskStatus, to_status: TaskStatus) -> None:
    if from_status == to_status:
        # No-op transitions are allowed (idempotent re-reporting).
        return
    if to_status not in _ALLOWED.get(from_status, set()):
        raise InvalidTransition(
            f"invalid task transition: {from_status.value} -> {to_status.value}"
        )


def is_terminal(status: TaskStatus) -> bool:
    return status in {TaskStatus.COMPLETED, TaskStatus.FAILED}
