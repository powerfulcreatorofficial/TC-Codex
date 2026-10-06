"""Bounded project context assembly for Engineering TC.

The context engine is deterministic and evidence-first. It does not infer facts
that are not present in persisted project/task/learning/plan records. It
produces a compact context packet suitable for Brain prompts and UI inspection.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import TaskStatus


@dataclass(frozen=True)
class ContextPacket:
    project_id: str | None
    sections: tuple[tuple[str, str], ...]
    context_text: str


def _task_line(task: Any) -> str:
    status = task.status.value if hasattr(task.status, "value") else str(task.status)
    prompt = " ".join(str(task.prompt).split())[:180]
    return f"- {task.task_id} | {status} | steps={task.steps} | {prompt}"


def assemble_project_context(
    project: dict[str, Any] | None,
    tasks: list[Any] | None = None,
    learnings: list[dict[str, Any]] | None = None,
    plan: dict[str, Any] | None = None,
    *,
    max_tasks: int = 8,
    max_learnings: int = 8,
) -> ContextPacket:
    """Build a bounded packet from observable persisted records."""
    tasks = list(tasks or [])[:max_tasks]
    learnings = list(learnings or [])[:max_learnings]
    sections: list[tuple[str, str]] = []
    project_id = project.get("id") if project else None

    if project:
        sections.append(
            (
                "project",
                "\n".join(
                    [
                        f"name={project.get('name', '')}",
                        f"description={project.get('description') or ''}",
                        f"workspace_path={project.get('workspace_path', '')}",
                        f"task_count={project.get('task_count', 0)}",
                    ]
                ),
            )
        )

    if tasks:
        sections.append(("recent_tasks", "\n".join(_task_line(task) for task in tasks)))

    if learnings:
        lines = [
            f"- [{item.get('category', 'general')}] {item.get('lesson', '')}"
            for item in learnings
        ]
        sections.append(("verified_lessons", "\n".join(lines)))

    if plan:
        lines = [
            f"plan_id={plan.get('plan_id')}",
            f"status={plan.get('status')}",
            f"objective={plan.get('objective', '')}",
        ]
        for step in plan.get("steps", []):
            lines.append(
                f"- step={step.get('id')} title={step.get('title')} "
                f"verify={step.get('verification')} risk={step.get('risk', 'low')}"
            )
        criteria = plan.get("acceptance_criteria") or []
        if criteria:
            lines.append("acceptance_criteria:")
            lines.extend(f"- {item}" for item in criteria)
        risks = plan.get("risks") or []
        if risks:
            lines.append("risks:")
            lines.extend(f"- {item}" for item in risks)
        sections.append(("approved_plan", "\n".join(lines)))

    if not sections:
        text = "No persisted project context is available. Inspect the workspace before making changes."
    else:
        chunks = [f"[{name}]\n{content}" for name, content in sections]
        text = "\n\n".join(chunks)

    return ContextPacket(project_id=project_id, sections=tuple(sections), context_text=text)


def classify_project_health(tasks: list[Any]) -> dict[str, Any]:
    total = len(tasks)
    completed = sum(_status(t) == TaskStatus.COMPLETED for t in tasks)
    failed = sum(_status(t) == TaskStatus.FAILED for t in tasks)
    active = sum(_status(t) in {TaskStatus.PENDING, TaskStatus.RUNNING, TaskStatus.AWAITING_APPROVAL} for t in tasks)
    rate = round(completed / total * 100) if total else None
    return {"total": total, "completed": completed, "failed": failed, "active": active, "completion_rate": rate}


def _status(task: Any) -> TaskStatus | str:
    status = getattr(task, "status", "")
    return status if isinstance(status, TaskStatus) else str(status)
