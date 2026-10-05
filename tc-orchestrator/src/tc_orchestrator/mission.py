"""High-level engineering mission controller.

This is intentionally thin: the existing Orchestrator remains the execution
authority. MissionController adds deterministic delegation and evidence rules
around it so specialist agents can help without becoming the system owner.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .delegation import DelegationManager
from .engineering.scientific import status as scientific_status
from .evidence import EvidenceRecord


@dataclass
class MissionReport:
    objective: str
    delegated_task_id: str | None = None
    worker: str | None = None
    evidence: list[EvidenceRecord] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


class MissionController:
    def __init__(self, delegator: DelegationManager | None = None) -> None:
        self.delegator = delegator or DelegationManager()

    def prepare(self, objective: str, workspace: str, context: dict[str, Any] | None = None) -> MissionReport:
        result = self.delegator.delegate(
            objective,
            workspace=workspace,
            context=context or {},
            constraints=[
                "Do not bypass TC approval policy.",
                "Return changed files and verification evidence.",
                "Do not claim completion without observable evidence.",
            ],
            acceptance_criteria=[
                "Requested behavior is implemented.",
                "Existing interfaces remain compatible unless change is explicitly required.",
                "Verification evidence is recorded.",
            ],
        )
        return MissionReport(
            objective=objective,
            delegated_task_id=result.task_id,
            worker=result.worker,
            evidence=[
                EvidenceRecord("delegation", result.summary, "delegation manager", verified=True),
                EvidenceRecord(
                    "scientific_capabilities",
                    f"available={scientific_status().available}",
                    "local capability discovery",
                    verified=True,
                ),
            ],
            notes=["Worker output must be reviewed by the TC lead before integration."],
        )
