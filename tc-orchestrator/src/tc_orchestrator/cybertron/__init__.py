"""Cybertron — the engineering capability inside TC ENGINEERING AI.

Cybertron is NOT a replacement for TC. It is a modular engineering subsystem
that TC invokes when engineering work is appropriate:

    TC -> Cybertron.execute(task) -> TaskReport

It provides:
- repository intelligence (structure, languages, build systems, tests)
- model-assisted but validated planning
- a capability-levelled tool surface (L0..L5)
- sandboxed execution with truthful exit codes and hard resource bounds
- a bounded ORIENT -> PLAN -> APPROVE -> ACT -> OBSERVE -> VERIFY -> REVIEW
  -> REPAIR -> REPORT state machine
- deterministic, evidence-based verification (a hard gate)
- an independent read-only review stage
- scoped memory with provenance/trust metadata

Security priorities come first: repository content is treated as untrusted
data, secrets stay in the control plane, and no stage may convert a failing
command into a success.
"""

from .budget import BudgetExceeded, TaskBudget
from .engine import Cybertron, CybertronEngine, EngineConfig
from .models import (
    EngineeringTask,
    FinalStatus,
    Stage,
    TaskReport,
)
from .planning import EngineeringPlan, PlanAction, PlanValidationError, validate_plan
from .sandbox import LocalProcessSandbox, SandboxLimits, SandboxResult
from .workspace import SafeWorkspace, WorkspaceSecurityError

__all__ = [
    "BudgetExceeded",
    "Cybertron",
    "CybertronEngine",
    "EngineConfig",
    "EngineeringPlan",
    "EngineeringTask",
    "FinalStatus",
    "LocalProcessSandbox",
    "PlanAction",
    "PlanValidationError",
    "SafeWorkspace",
    "SandboxLimits",
    "SandboxResult",
    "Stage",
    "TaskBudget",
    "TaskReport",
    "WorkspaceSecurityError",
    "validate_plan",
]
