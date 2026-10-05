"""Deterministic, provider-independent engineering planning."""
from __future__ import annotations
from typing import Any
from .models import PlanStep


def _clean(prompt: str) -> str:
    return " ".join(prompt.strip().split())


def build_plan(prompt: str, project: dict[str, Any] | None = None) -> dict[str, Any]:
    text = _clean(prompt)
    lower = text.lower()
    suffix = f" for project '{project['name']}'" if project else ""
    steps = [
        PlanStep(id="inspect", title="Inspect the workspace", objective=f"Understand the existing repository and constraints{suffix}.", verification="Confirm relevant files, stack and current state before editing.", risk="low"),
        PlanStep(id="implement", title="Implement the requested change", objective="Make the smallest coherent change that satisfies the request.", verification="Confirm changed files match the requested behavior and preserve existing interfaces.", risk="medium"),
    ]
    if any(k in lower for k in ("fix", "repair", "error", "bug", "broken", "failing")):
        steps.append(PlanStep(id="repair", title="Repair failures", objective="If verification fails, inspect the concrete failure and make a targeted repair.", verification="Rerun the failing verification after each targeted repair.", risk="medium"))
    steps.append(PlanStep(id="verify", title="Verify the result", objective="Run the requested tests/build checks or another appropriate validation.", verification="Require observable successful evidence before claiming completion.", risk="low"))
    return {
        "objective": text,
        "steps": [x.model_dump() for x in steps],
        "acceptance_criteria": [
            "The requested behavior is implemented in the workspace.",
            "No task/tool approval boundary is bypassed.",
            "Verification produces observable evidence.",
            "TC reports failure honestly if verification cannot succeed.",
        ],
        "risks": [
            "Existing project behavior may constrain the safest implementation.",
            "Provider availability can block Brain-driven execution even when planning succeeds.",
        ],
    }
