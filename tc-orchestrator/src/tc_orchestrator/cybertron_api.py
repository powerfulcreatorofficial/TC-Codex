"""HTTP surface for Cybertron inside the TC orchestrator.

TC (or an operator UI) drives engineering work through these endpoints. The
response contract mirrors ``Cybertron.execute``: truthful status, changed
files, verification evidence, review results, errors and usage.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .config import Settings
from .cybertron_service import CybertronService, CybertronTaskState


class CybertronTaskRequest(BaseModel):
    objective: str = Field(min_length=1, max_length=20_000)
    # Relative to the configured CYBERTRON_WORKSPACE_ROOT.
    workspace_path: str = Field(default=".", max_length=1000)
    project_id: str | None = None
    verification_commands: list[list[str]] = Field(default_factory=list, max_length=8)
    require_approval: bool | None = None
    # "auto": agentic when a Cybertron brain is configured, else plan mode.
    mode: str = Field(default="auto", pattern="^(auto|agentic|plan)$")


class CybertronTaskOut(BaseModel):
    task_id: str
    state: str
    mode: str = "plan"
    objective: str
    status: str | None = None
    summary: str | None = None
    changed_files: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    verification: dict[str, Any] | None = None
    review: dict[str, Any] | None = None
    usage: dict[str, Any] = Field(default_factory=dict)
    stages_completed: list[str] = Field(default_factory=list)


class CybertronApprovalOut(BaseModel):
    approval_id: str
    task_id: str
    description: str
    detail: dict[str, Any]
    expires_at: float


class CybertronDecisionRequest(BaseModel):
    approved: bool
    decided_by: str = "external"


def _task_out(state: CybertronTaskState) -> CybertronTaskOut:
    report = state.report
    return CybertronTaskOut(
        task_id=state.task_id,
        state=state.state,
        mode=state.mode,
        objective=state.objective,
        status=report.status.value if report else None,
        summary=report.summary if report else state.error,
        changed_files=report.changed_files if report else [],
        errors=report.errors if report else ([state.error] if state.error else []),
        evidence=report.evidence if report else [],
        verification=report.verification.model_dump() if report and report.verification else None,
        review=report.review.model_dump() if report and report.review else None,
        usage=report.usage if report else {},
        stages_completed=[s.value for s in report.stages_completed] if report else [],
    )


def build_cybertron_router(settings: Settings) -> APIRouter:
    service = CybertronService(settings)
    router = APIRouter(prefix="/v1/cybertron", tags=["cybertron"])

    @router.get("/status")
    def status() -> dict[str, Any]:
        from .cybertron_service import loop_config_from_env, tool_brain_from_settings

        loop_cfg = loop_config_from_env()
        return {
            "subsystem": "cybertron",
            "workspace_root": str(service.workspace_root),
            "require_approval_default": settings.require_approval,
            "agentic_available": tool_brain_from_settings(settings) is not None,
            "approval_policy": loop_cfg.approval_policy.value,
            "sandbox_mode": loop_cfg.sandbox_mode.value,
            "sessions_dir": str(service.sessions.directory) if service.sessions else None,
            "stages": [
                "ORIENT", "PLAN", "APPROVE", "ACT", "OBSERVE",
                "VERIFY", "REVIEW", "REPAIR", "REPORT",
            ],
        }

    @router.post("/tasks", response_model=CybertronTaskOut)
    def create_task(req: CybertronTaskRequest) -> CybertronTaskOut:
        try:
            state = service.start_task(
                req.objective,
                req.workspace_path,
                project_id=req.project_id,
                verification_commands=req.verification_commands or None,
                require_approval=req.require_approval,
                mode=req.mode,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _task_out(state)

    @router.get("/tasks", response_model=list[CybertronTaskOut])
    def list_tasks(limit: int = 50) -> list[CybertronTaskOut]:
        return [_task_out(s) for s in service.list(limit=limit)]

    @router.get("/tasks/{task_id}", response_model=CybertronTaskOut)
    def get_task(task_id: str) -> CybertronTaskOut:
        state = service.get(task_id)
        if state is None:
            raise HTTPException(status_code=404, detail="unknown cybertron task")
        return _task_out(state)

    @router.get("/tasks/{task_id}/events")
    def get_events(task_id: str) -> list[dict[str, Any]]:
        state = service.get(task_id)
        if state is None:
            raise HTTPException(status_code=404, detail="unknown cybertron task")
        return [e.model_dump() for e in list(state.events)]

    @router.get("/approvals", response_model=list[CybertronApprovalOut])
    def list_approvals() -> list[CybertronApprovalOut]:
        return [
            CybertronApprovalOut(
                approval_id=a.approval_id,
                task_id=a.task_id,
                description=a.description,
                detail=a.detail,
                expires_at=a.expires_at,
            )
            for a in service.approvals.list_pending()
        ]

    @router.get("/sessions")
    def list_sessions(limit: int = 50) -> list[dict[str, Any]]:
        if service.sessions is None:
            return []
        return [
            {
                "task_id": s.task_id,
                "created_at": s.created_at,
                "objective": s.objective,
                "final_status": s.final_status,
                "event_count": s.event_count,
            }
            for s in service.sessions.list_sessions(limit=limit)
        ]

    @router.get("/sessions/{task_id}")
    def get_session(task_id: str) -> list[dict[str, Any]]:
        if service.sessions is None:
            raise HTTPException(status_code=404, detail="session recording disabled")
        lines = service.sessions.load(task_id)
        if not lines:
            raise HTTPException(status_code=404, detail="unknown session")
        return lines

    @router.post("/approvals/{approval_id}")
    def decide(approval_id: str, req: CybertronDecisionRequest) -> dict[str, Any]:
        found = service.approvals.decide(approval_id, req.approved, req.decided_by)
        if not found:
            raise HTTPException(status_code=404, detail="unknown or already-decided approval")
        return {"approval_id": approval_id, "approved": req.approved}

    return router
