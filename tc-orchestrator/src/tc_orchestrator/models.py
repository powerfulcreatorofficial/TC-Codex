"""Pydantic models for tool calls, tool results, tasks, and chat messages."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Chat messages (OpenAI-compatible)
# ---------------------------------------------------------------------------


class ChatMessage(BaseModel):
    """A single chat message in the OpenAI Chat Completions format."""

    role: str  # "system" | "user" | "assistant" | "tool"
    content: str | None = None
    # For assistant tool calls.
    tool_calls: list[dict[str, Any]] | None = None
    # For role == "tool": the name of the tool that produced this result.
    name: str | None = None
    # Responses API correlation id for function_call_output.
    tool_call_id: str | None = None


# ---------------------------------------------------------------------------
# Tool calls and results
# ---------------------------------------------------------------------------


class ToolCallRequest(BaseModel):
    """A structured tool call requested by the Brain."""

    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    """The structured result returned to the Brain after a tool executes.

    ``ok`` must reflect the real outcome: a command that completed with a
    non-zero exit code is NOT ok. ``exit_code`` is carried explicitly so the
    orchestration layers never have to re-parse output text to learn it.
    """

    name: str
    ok: bool
    output: str
    error: str | None = None
    exit_code: int | None = None
    truncated: bool = False

    def as_tool_message(self) -> ChatMessage:
        return ChatMessage(role="tool", content=self.to_compact(), name=self.name)

    def to_compact(self) -> str:
        parts = [f"ok={self.ok}"]
        if self.exit_code is not None:
            parts.append(f"exit_code={self.exit_code}")
        parts.append(self.output)
        if self.error:
            parts.append(f"error={self.error}")
        return " | ".join(parts)


# ---------------------------------------------------------------------------
# Task API
# ---------------------------------------------------------------------------


class TaskStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"


class TaskRequest(BaseModel):
    prompt: str
    project_id: str | None = None
    plan_id: str | None = None



class PlanStatus(StrEnum):
    DRAFT = "DRAFT"
    READY = "READY"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class PlanStep(BaseModel):
    id: str
    title: str
    objective: str
    verification: str
    risk: str = "low"


class PlanSummary(BaseModel):
    plan_id: str
    status: PlanStatus
    objective: str
    project_id: str | None = None
    steps: list[PlanStep]
    acceptance_criteria: list[str]
    risks: list[str]
    created_at: str | None = None
    updated_at: str | None = None


class PlanCreateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=12000)
    project_id: str | None = None


class PlanCreateResponse(BaseModel):
    plan: PlanSummary
    owner_token: str


class PlanApprovalRequest(BaseModel):
    approved: bool


class PlanContextOut(BaseModel):
    plan: PlanSummary
    context_text: str


class TaskSummary(BaseModel):
    task_id: str
    status: TaskStatus
    prompt: str
    answer: str | None = None
    steps: int = 0
    error: str | None = None
    current_step: int = 0
    max_steps: int = 20
    created_at: str | None = None
    updated_at: str | None = None
    project_id: str | None = None
    plan_id: str | None = None


class TaskCreateResponse(BaseModel):
    """Returned on task creation. Includes the owner token (once, never again)."""

    task_id: str
    status: TaskStatus
    owner_token: str


class ApprovalView(BaseModel):
    """Secret-free view of a pending approval shown to the approver."""

    task_id: str
    tool_name: str
    arguments_metadata: dict[str, Any]
    risk_level: str
    created_at: str
    expires_at: str
    nonce: str


class ApprovalDecisionRequest(BaseModel):
    approved: bool
    # The nonce of the exact pending action being decided.
    nonce: str
    # Identifier of the external approver (audited; never the Brain).
    decided_by: str = "external"


class TaskEventOut(BaseModel):
    id: int
    task_id: str
    ts: str
    event_type: str
    tool_name: str | None = None
    arguments_metadata: dict[str, Any] | None = None
    result_metadata: dict[str, Any] | None = None
    status: str | None = None




class EvaluationDimensionOut(BaseModel):
    key: str
    label: str
    score: int
    evidence: str


class TaskEvaluationOut(BaseModel):
    task_id: str
    overall_score: int
    verdict: str
    dimensions: list[EvaluationDimensionOut]
    total_events: int
    approvals_requested: int
    approvals_decided: int
    repair_signals: int
    verification_signals: int


class LearningOut(BaseModel):
    id: int
    task_id: str | None = None
    category: str
    lesson: str
    evidence: str
    score: int
    created_at: str | None = None


class RecoveryClass(StrEnum):
    VERIFICATION_FAILURE = "verification_failure"
    TOOL_FAILURE = "tool_failure"
    PROVIDER_FAILURE = "provider_failure"
    APPROVAL_BLOCKED = "approval_blocked"
    REPEATED_ACTION = "repeated_action"
    UNKNOWN_FAILURE = "unknown_failure"


class BrainUsageOut(BaseModel):
    route: str
    model: str
    reason: str
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    fallback: bool = False


class TaskBrainUsageOut(BaseModel):
    task_id: str
    calls: list[BrainUsageOut]
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    estimated_cost_usd: float
    higher_calls: int
    current_route: str


class TaskRecoveryOut(BaseModel):
    task_id: str
    recovery_class: RecoveryClass
    severity: str
    repair_attempts: int
    max_repair_attempts: int
    retry_allowed: bool
    recommended_action: str
    evidence: list[str]


class ProjectHealthOut(BaseModel):
    total: int
    completed: int
    failed: int
    active: int
    completion_rate: int | None = None


class RetrievedEvidenceOut(BaseModel):
    kind: str
    record_id: str
    score: int
    reason: str
    text: str


class ProjectContextRetrievalOut(BaseModel):
    project_id: str
    query: str
    items: list[RetrievedEvidenceOut]
    context_text: str


class ProjectContextPacketOut(BaseModel):
    project_id: str
    generated_at: str | None = None
    health: ProjectHealthOut
    section_names: list[str]
    context_text: str


class RepositoryFileOut(BaseModel):
    path: str
    status: str
    size: int | None = None
    sha256: str | None = None
    preview: str | None = None


class RepositorySnapshotOut(BaseModel):
    project_id: str
    project_path: str
    branch: str | None = None
    clean: bool | None = None
    changed_files: list[RepositoryFileOut]
    manifests: list[RepositoryFileOut]
    context_text: str


class BrainRoutingStatusOut(BaseModel):
    primary_model: str
    higher_model: str
    higher_enabled: bool
    higher_configured: bool
    higher_max_usd: float
    higher_max_calls: int
    primary_input_usd_per_mtok: float
    primary_output_usd_per_mtok: float
    higher_input_usd_per_mtok: float
    higher_output_usd_per_mtok: float


class HealthResponse(BaseModel):
    status: str
    daemon: str | None = None
    database: str | None = None


class ProjectSummary(BaseModel):
    id: str
    name: str
    description: str
    workspace_path: str
    task_count: int = 0
    created_at: str | None = None
    updated_at: str | None = None


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)
    workspace_path: str = Field(min_length=1, max_length=400)


class ProjectUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)


class ProjectContextTaskOut(BaseModel):
    task_id: str
    status: TaskStatus
    prompt: str
    answer: str | None = None
    error: str | None = None
    steps: int = 0
    created_at: str | None = None
    updated_at: str | None = None


class ProjectContextLearningOut(BaseModel):
    id: int
    category: str
    lesson: str
    score: int
    created_at: str | None = None


class ProjectContextOut(BaseModel):
    project: ProjectSummary
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    active_tasks: int
    recent_tasks: list[ProjectContextTaskOut]
    recent_learnings: list[ProjectContextLearningOut]
    context_text: str
