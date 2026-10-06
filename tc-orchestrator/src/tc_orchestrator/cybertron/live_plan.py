"""Codex-style ``update_plan``: a live step list the model maintains.

The model records its plan as steps with statuses (pending / in_progress /
completed). This is OBSERVABILITY, not authority: live-plan state never
bypasses validation, approval, verification, or review.
"""

from __future__ import annotations

from dataclasses import dataclass, field

VALID_STATUSES = ("pending", "in_progress", "completed")


@dataclass
class LivePlanStep:
    step: str
    status: str = "pending"


@dataclass
class LivePlan:
    steps: list[LivePlanStep] = field(default_factory=list)
    explanation: str = ""
    updates: int = 0

    def update(self, steps: list[dict], explanation: str = "") -> str:
        """Validate and apply an update_plan call. Returns an error message
        (empty string on success)."""
        if not isinstance(steps, list) or not steps:
            return "plan must be a non-empty list of steps"
        if len(steps) > 20:
            return "plan too long (max 20 steps)"
        parsed: list[LivePlanStep] = []
        in_progress = 0
        for raw in steps:
            if not isinstance(raw, dict):
                return "each plan item must be an object with 'step' and 'status'"
            text = str(raw.get("step", "")).strip()
            status = str(raw.get("status", "pending")).strip()
            if not text:
                return "plan step text must not be empty"
            if status not in VALID_STATUSES:
                return f"invalid status {status!r}; use one of {VALID_STATUSES}"
            if status == "in_progress":
                in_progress += 1
            parsed.append(LivePlanStep(step=text[:300], status=status))
        if in_progress > 1:
            return "at most one step may be in_progress"
        self.steps = parsed
        self.explanation = str(explanation or "")[:1000]
        self.updates += 1
        return ""

    def as_dict(self) -> dict:
        return {
            "explanation": self.explanation,
            "steps": [{"step": s.step, "status": s.status} for s in self.steps],
            "updates": self.updates,
        }

    def render(self) -> str:
        marks = {"pending": "[ ]", "in_progress": "[~]", "completed": "[x]"}
        return "\n".join(f"{marks[s.status]} {s.step}" for s in self.steps)
