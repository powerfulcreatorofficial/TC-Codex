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

from .agent_loop import AgentLoop, AgentLoopConfig, ModelToolCall, ModelTurn, ToolBrain
from .apply_patch import apply_any_patch, apply_v4a_patch, is_v4a_patch
from .budget import BudgetExceeded, TaskBudget
from .engine import Cybertron, CybertronEngine, EngineConfig
from .exec_policy import ApprovalPolicy, SandboxMode, assess_command, decide_exec
from .models import (
    EngineeringTask,
    FinalStatus,
    Stage,
    TaskReport,
)
from .planning import EngineeringPlan, PlanAction, PlanValidationError, validate_plan
from .sandbox import LocalProcessSandbox, SandboxLimits, SandboxResult
from .sessions import SessionRecorder
from .workspace import SafeWorkspace, WorkspaceSecurityError

__all__ = [
    "AgentLoop",
    "AgentLoopConfig",
    "ApprovalPolicy",
    "BudgetExceeded",
    "Cybertron",
    "CybertronEngine",
    "EngineConfig",
    "EngineeringPlan",
    "EngineeringTask",
    "FinalStatus",
    "LocalProcessSandbox",
    "ModelToolCall",
    "ModelTurn",
    "PlanAction",
    "PlanValidationError",
    "SafeWorkspace",
    "SandboxLimits",
    "SandboxMode",
    "SandboxResult",
    "SessionRecorder",
    "Stage",
    "TaskBudget",
    "TaskReport",
    "ToolBrain",
    "WorkspaceSecurityError",
    "apply_any_patch",
    "apply_v4a_patch",
    "assess_command",
    "decide_exec",
    "is_v4a_patch",
    "validate_plan",
]
