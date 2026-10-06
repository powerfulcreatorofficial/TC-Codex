"""FastAPI HTTP API for the TC Orchestrator (Step 4).

Endpoints:
  GET  /health                          -> liveness + daemon + db reachability
  POST /v1/tasks                        -> create + run a task
  GET  /v1/tasks/{id}                   -> fetch task state
  GET  /v1/tasks/{id}/events            -> task event history
  POST /v1/tasks/{id}/approve           -> approve a pending mutating action
  POST /v1/tasks/{id}/reject            -> reject a pending mutating action
  GET  /v1/tasks/{id}/pending_approval  -> view the pending action (owner only)

Approval security:
- Only the task owner (holder of the owner token returned at creation) may
  approve/reject. The Brain never receives the owner token.
- Approvals reference the exact pending action via a single-use nonce.
- Stale/replayed/mismatched approvals are rejected.
- DB failures surface as FAILED rather than fake success.

Note: the owner token is returned in the ``x-tc-owner-token`` response header
on task creation (once). In production this would be a cookie/signed token.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi.responses import StreamingResponse

from fastapi import FastAPI, Header, HTTPException, Response

from .brain import OpenAICompatibleBrain, OpenAIResponsesBrain
from .brain_router import BrainBudget, BrainPricing, BrainRouter, BrainRouterConfig
from .config import Settings, load_settings
from .context_engine import assemble_project_context, classify_project_health
from .db import Database
from .evaluation import evaluate_task
from .adaptive import classify_failure
from .grpc_client import WorkspaceClient
from .learning import derive_learnings
from .planner import build_plan
from .retrieval import retrieve_project_evidence
from .repository_intelligence import build_repository_snapshot
from .models import (
    ApprovalDecisionRequest,
    ApprovalView,
    HealthResponse,
    BrainRoutingStatusOut,
    TaskEventOut,
    TaskEvaluationOut,
    TaskBrainUsageOut,
    BrainUsageOut,
    TaskRecoveryOut,
    LearningOut,
    ProjectCreateRequest,
    ProjectSummary,
    ProjectUpdateRequest,
    ProjectContextOut,
    ProjectContextTaskOut,
    ProjectContextLearningOut,
    ProjectContextPacketOut,
    ProjectContextRetrievalOut,
    RetrievedEvidenceOut,
    ProjectHealthOut,
    RepositoryFileOut,
    RepositorySnapshotOut,
    RepositoryFileOut,
    RepositorySnapshotOut,
    PlanApprovalRequest,
    PlanContextOut,
    PlanCreateRequest,
    PlanCreateResponse,
    PlanSummary,
    TaskRequest,
    TaskStatus,
    TaskSummary,
)
from .orchestrator import Orchestrator, OrchestratorConfig
from .pg_task_store import PgTaskStore
from .policy import ApprovalPolicy
from .redaction import Redactor
from .task_store import TaskStore
from .tool_registry import default_registry
from .master_api import router as master_router
from .transitions import InvalidTransition

OWNER_HEADER = "x-tc-owner-token"


def _build_orchestrator(
    settings: Settings,
    client: WorkspaceClient,
    brain_override: Any | None = None,
    learning_context: str = "",
    project_context: str = "",
    plan_context: str = "",
    repository_context: str = "",
) -> Orchestrator:
    if brain_override is not None:
        brain = brain_override
    else:
        primary = OpenAICompatibleBrain(
            base_url=settings.brain_base_url or "",
            api_key=settings.brain_api_key or "",
            model=settings.brain_model,
        )
        higher = None
        if settings.higher_brain_enabled and settings.higher_brain_api_key:
            if settings.higher_brain_protocol.lower() == "responses":
                higher = OpenAIResponsesBrain(
                    base_url=settings.higher_brain_base_url or "",
                    api_key=settings.higher_brain_api_key,
                    model=settings.higher_brain_model,
                )
            else:
                higher = OpenAICompatibleBrain(
                    base_url=settings.higher_brain_base_url or "",
                    api_key=settings.higher_brain_api_key,
                    model=settings.higher_brain_model,
                )
        brain = BrainRouter(
            primary=primary,
            higher=higher,
            config=BrainRouterConfig(
                primary_model=settings.brain_model,
                higher_model=settings.higher_brain_model,
                higher_enabled=settings.higher_brain_enabled,
                budget=BrainBudget(
                    max_usd=settings.higher_brain_max_usd,
                    max_higher_calls=settings.higher_brain_max_calls,
                ),
                primary_pricing=BrainPricing(settings.primary_input_usd_per_mtok, settings.primary_output_usd_per_mtok),
                higher_pricing=BrainPricing(settings.higher_input_usd_per_mtok, settings.higher_output_usd_per_mtok),
            ),
        )
    policy = ApprovalPolicy() if settings.require_approval else ApprovalPolicy.disabled()
    return Orchestrator(
        brain=brain,
        client=client,
        registry=default_registry(),
        redactor=Redactor.from_env(),
        config=OrchestratorConfig(
            max_steps=settings.max_agent_steps,
            approval_policy=policy,
            approval_expiry_seconds=settings.approval_expiry_seconds,
            learning_context=learning_context,
            project_context=project_context,
            plan_context=plan_context,
            repository_context=repository_context,
            max_repair_attempts=settings.max_repair_attempts,
        ),
    )


def build_default_store(settings: Settings):
    """PgTaskStore if DATABASE_URL is set (migrations auto-applied), else in-memory."""
    if settings.database_url:
        from .migrations import apply_migrations

        apply_migrations(settings.database_url)
        return PgTaskStore(Database(settings.database_url))
    return TaskStore()


def create_app(
    *,
    settings: Settings | None = None,
    store: Any | None = None,
    client: WorkspaceClient | None = None,
    brain_override: Any | None = None,
) -> FastAPI:
    settings = settings or load_settings()
    owns_client = client is None
    client = client or WorkspaceClient(settings.daemon_addr)
    store = store or build_default_store(settings)
    redactor = Redactor.from_env()

    # In-process pending-action store for approval resume (single-process).
    # Holds the transcript + raw args needed to resume after approval.
    pending_resume: dict[str, dict] = {}

    app = FastAPI(title="Engineering TC Orchestrator", version="0.3.0")
    app.include_router(master_router)

    # Cybertron — the engineering capability inside TC (TC -> Cybertron.execute).
    from .cybertron_api import build_cybertron_router

    app.include_router(build_cybertron_router(settings))

    def _fail(task_id: str, error: str) -> TaskSummary:
        """Never report success on persistence failure; mark FAILED safely."""
        try:
            store.update(task_id, status=TaskStatus.FAILED, error=error, steps=0)
        except Exception:  # noqa: BLE001
            pass
        try:
            store.add_event(task_id, "task_failed", status=TaskStatus.FAILED.value)
        except Exception:  # noqa: BLE001
            pass
        summary = store.get(task_id)
        if summary is not None and getattr(summary, "plan_id", None) and hasattr(store, "update_plan"):
            try:
                plan = store.get_plan(summary.plan_id)
                if plan and plan.get("status") in {"READY", "EXECUTING"}:
                    store.update_plan(summary.plan_id, status="FAILED")
            except Exception:
                pass
            return summary
        return TaskSummary(task_id=task_id, status=TaskStatus.FAILED, prompt="", error=error)

    def _persist_learnings(task_id: str, summary: TaskSummary | None) -> None:
        if summary is None or not hasattr(store, "add_learning"):
            return
        try:
            learnings = derive_learnings(summary, store.list_events(task_id))
            for learning in learnings:
                store.add_learning(task_id, learning)
        except Exception:
            # Learning is advisory; it must never turn a successful task into a failure.
            return

    def _build_project_context(project_id: str | None) -> tuple[str, dict[str, Any] | None]:
        if not project_id or not hasattr(store, "get_project"):
            return "", None
        try:
            project = store.get_project(project_id)
        except Exception:
            return "", None
        if not project:
            return "", None
        tasks = []
        learnings = []
        if hasattr(store, "list_project_tasks"):
            try:
                tasks = list(store.list_project_tasks(project_id, 8))
            except Exception:
                tasks = []
        if hasattr(store, "list_project_learnings"):
            try:
                learnings = list(store.list_project_learnings(project_id, 8))
            except Exception:
                learnings = []
        packet = assemble_project_context(project, tasks, learnings)
        return packet.context_text, project


    def _retrieved_project_context(project_id: str | None, query: str) -> str:
        if not project_id:
            return ""
        try:
            project = store.get_project(project_id) if hasattr(store, "get_project") else None
            if not project:
                return ""
            tasks = list(store.list_project_tasks(project_id, 20)) if hasattr(store, "list_project_tasks") else []
            learnings = list(store.list_project_learnings(project_id, 20)) if hasattr(store, "list_project_learnings") else []
            return retrieve_project_evidence(query, tasks, learnings, max_items=6).context_text
        except Exception:
            return ""

    def _project_context(project_id: str | None) -> str:
        context, _ = _build_project_context(project_id)
        return context


    def _plan_context(plan_id: str | None) -> str:
        if not plan_id or not hasattr(store, "get_plan"):
            return ""
        plan = store.get_plan(plan_id)
        if not plan:
            return ""
        packet = assemble_project_context(None, plan=plan)
        return packet.context_text

    def _repository_context(project_id: str | None) -> str:
        if not project_id or not hasattr(store, "get_project"):
            return ""
        try:
            project = store.get_project(project_id)
            if not project:
                return ""
            return build_repository_snapshot(client, project.get("workspace_path"), max_changed=12).context_text
        except Exception:
            return ""

    def _learning_context() -> str:
        if not hasattr(store, "list_learnings"):
            return ""
        try:
            items = store.list_learnings(8)
        except Exception:
            return ""
        return "\n".join(f"- [{item['category']}] {item['lesson']}" for item in items)

    def _apply_result(task_id, result, owner_token, prompt) -> TaskSummary:
        for call in getattr(result, "brain_calls", []) or []:
            try:
                metadata = call.metadata() if hasattr(call, "metadata") else dict(call)
                store.add_event(task_id, "brain_call", result_metadata=metadata)
            except Exception:
                # Telemetry is advisory; never turn an execution result into a failure.
                pass
        if result.awaiting_approval is not None:
            pending = result.awaiting_approval
            try:
                stored = store.create_approval(
                    task_id=task_id,
                    tool_name=pending.tool_name,
                    arguments_metadata=pending.arguments_metadata,
                    risk_level=pending.risk_level,
                    expiry_seconds=settings.approval_expiry_seconds,
                )
                store.update(task_id, status=TaskStatus.AWAITING_APPROVAL)
                store.add_event(
                    task_id,
                    "approval_requested",
                    tool_name=pending.tool_name,
                    arguments_metadata=pending.arguments_metadata,
                    status="pending",
                    approval_nonce=stored.nonce,
                )
            except Exception as exc:  # noqa: BLE001
                return _fail(task_id, redactor.redact(str(exc)))
            pending_resume[task_id] = {
                "messages": result.messages,
                "tool_name": pending.tool_name,
                "arguments": result.pending_arguments or {},
                "owner_token": owner_token,
                "prompt": prompt,
            }
            updated = store.get(task_id)
            return updated if updated else _fail(task_id, "lost task")

        try:
            if result.finished:
                store.update(
                    task_id,
                    status=TaskStatus.COMPLETED,
                    answer=result.answer,
                    steps=result.steps,
                )
                store.add_event(
                    task_id,
                    "task_completed",
                    status=TaskStatus.COMPLETED.value,
                    result_metadata={"answer": redactor.redact(result.answer or "")},
                )
            else:
                store.update(
                    task_id,
                    status=TaskStatus.FAILED,
                    error=redactor.redact(result.error or "unknown"),
                    steps=result.steps,
                )
                store.add_event(
                    task_id,
                    "task_failed",
                    status=TaskStatus.FAILED.value,
                    result_metadata={"error": redactor.redact(result.error or "")},
                )
            summary_now = store.get(task_id)
            if summary_now is not None and getattr(summary_now, "plan_id", None) and hasattr(store, "update_plan"):
                target_plan_status = "COMPLETED" if result.finished else "FAILED"
                try:
                    store.update_plan(summary_now.plan_id, status=target_plan_status)
                except Exception as exc:
                    return _fail(task_id, redactor.redact(str(exc)))
        except Exception as exc:  # noqa: BLE001
            return _fail(task_id, redactor.redact(str(exc)))
        updated = store.get(task_id)
        if updated and updated.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
            _persist_learnings(task_id, updated)
        return updated if updated else _fail(task_id, "lost task")

    @app.get("/v1/brain", response_model=BrainRoutingStatusOut)
    def get_brain_status() -> BrainRoutingStatusOut:
        return BrainRoutingStatusOut(
            primary_model=settings.brain_model,
            higher_model=settings.higher_brain_model,
            higher_enabled=settings.higher_brain_enabled,
            higher_configured=bool(settings.higher_brain_enabled and settings.higher_brain_api_key),
            higher_max_usd=settings.higher_brain_max_usd,
            higher_max_calls=settings.higher_brain_max_calls,
            primary_input_usd_per_mtok=settings.primary_input_usd_per_mtok,
            primary_output_usd_per_mtok=settings.primary_output_usd_per_mtok,
            higher_input_usd_per_mtok=settings.higher_input_usd_per_mtok,
            higher_output_usd_per_mtok=settings.higher_output_usd_per_mtok,
        )

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        daemon_status = "unconfigured"
        try:
            import grpc

            ch = grpc.insecure_channel(settings.daemon_addr)
            grpc.channel_ready_future(ch).result(timeout=1.0)
            ch.close()
            daemon_status = "reachable"
        except Exception:  # noqa: BLE001
            daemon_status = "unreachable"
        db_status = "unconfigured"
        if settings.database_url:
            db_status = "reachable" if Database(settings.database_url).ping() else "unreachable"
        return HealthResponse(status="ok", daemon=daemon_status, database=db_status)

    @app.get("/v1/projects", response_model=list[ProjectSummary])
    def list_projects(limit: int = 100) -> list[ProjectSummary]:
        if not hasattr(store, "list_projects"):
            return []
        return [ProjectSummary(**p) for p in store.list_projects(limit)]

    @app.post("/v1/projects", response_model=ProjectSummary)
    def create_project(req: ProjectCreateRequest) -> ProjectSummary:
        if not hasattr(store, "create_project"):
            raise HTTPException(status_code=501, detail="projects unavailable")
        try:
            return ProjectSummary(**store.create_project(req.name, req.description, req.workspace_path))
        except Exception as exc:
            detail = str(exc)
            if "unique" in detail.lower() or "exists" in detail.lower():
                raise HTTPException(status_code=409, detail="project name already exists") from exc
            raise HTTPException(status_code=400, detail="project could not be created") from exc

    @app.get("/v1/projects/{project_id}", response_model=ProjectSummary)
    def get_project(project_id: str) -> ProjectSummary:
        project = store.get_project(project_id) if hasattr(store, "get_project") else None
        if project is None:
            raise HTTPException(status_code=404, detail="project not found")
        return ProjectSummary(**project)

    @app.get("/v1/projects/{project_id}/context", response_model=ProjectContextOut)
    def get_project_context(project_id: str) -> ProjectContextOut:
        context_text, project = _build_project_context(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="project not found")
        tasks = list(store.list_project_tasks(project_id, 12)) if hasattr(store, "list_project_tasks") else []
        learnings = list(store.list_project_learnings(project_id, 12)) if hasattr(store, "list_project_learnings") else []
        completed = sum(task.status == TaskStatus.COMPLETED for task in tasks)
        failed = sum(task.status == TaskStatus.FAILED for task in tasks)
        active = sum(task.status in (TaskStatus.PENDING, TaskStatus.RUNNING, TaskStatus.AWAITING_APPROVAL) for task in tasks)
        return ProjectContextOut(
            project=ProjectSummary(**project),
            total_tasks=len(tasks),
            completed_tasks=completed,
            failed_tasks=failed,
            active_tasks=active,
            recent_tasks=[ProjectContextTaskOut(
                task_id=task.task_id, status=task.status, prompt=task.prompt, answer=task.answer,
                error=task.error, steps=task.steps, created_at=task.created_at, updated_at=task.updated_at
            ) for task in tasks],
            recent_learnings=[ProjectContextLearningOut(
                id=item["id"], category=item["category"], lesson=item["lesson"], score=item["score"], created_at=item.get("created_at")
            ) for item in learnings],
            context_text=context_text,
        )

    @app.patch("/v1/projects/{project_id}", response_model=ProjectSummary)
    def update_project(project_id: str, req: ProjectUpdateRequest) -> ProjectSummary:
        project = store.update_project(project_id, name=req.name, description=req.description) if hasattr(store, "update_project") else None
        if project is None:
            raise HTTPException(status_code=404, detail="project not found")
        return ProjectSummary(**project)

    @app.delete("/v1/projects/{project_id}")
    def delete_project(project_id: str):
        ok = store.delete_project(project_id) if hasattr(store, "delete_project") else False
        if not ok:
            raise HTTPException(status_code=404, detail="project not found")
        return {"deleted": True, "project_id": project_id}


    def _plan_summary(data: dict[str, Any]) -> PlanSummary:
        return PlanSummary(plan_id=data["plan_id"], status=data["status"], objective=data["objective"], project_id=data.get("project_id"), steps=data.get("steps",[]), acceptance_criteria=data.get("acceptance_criteria",[]), risks=data.get("risks",[]), created_at=data.get("created_at"), updated_at=data.get("updated_at"))

    @app.get("/v1/projects/{project_id}/context/packet", response_model=ProjectContextPacketOut)
    def get_project_context_packet(project_id: str) -> ProjectContextPacketOut:
        if not hasattr(store, "get_project"):
            raise HTTPException(status_code=501, detail="projects unavailable")
        try:
            project = store.get_project(project_id)
        except Exception as exc:
            raise HTTPException(status_code=503, detail="project store unavailable") from exc
        if not project:
            raise HTTPException(status_code=404, detail="project not found")
        tasks = list(store.list_project_tasks(project_id, 12)) if hasattr(store, "list_project_tasks") else []
        learnings = list(store.list_project_learnings(project_id, 12)) if hasattr(store, "list_project_learnings") else []
        plan = None
        plan_id = None
        for task in tasks:
            if getattr(task, "plan_id", None):
                plan_id = task.plan_id
                break
        if plan_id and hasattr(store, "get_plan"):
            plan = store.get_plan(plan_id)
        packet = assemble_project_context(project, tasks, learnings, plan, max_tasks=12, max_learnings=12)
        health = classify_project_health(tasks)
        return ProjectContextPacketOut(
            project_id=project_id,
            health=ProjectHealthOut(**health),
            section_names=[name for name, _ in packet.sections],
            context_text=packet.context_text,
        )

    @app.get("/v1/projects/{project_id}/context/retrieve", response_model=ProjectContextRetrievalOut)
    def retrieve_project_context(project_id: str, q: str = "", limit: int = 6) -> ProjectContextRetrievalOut:
        project = store.get_project(project_id) if hasattr(store, "get_project") else None
        if project is None:
            raise HTTPException(status_code=404, detail="project not found")
        tasks = list(store.list_project_tasks(project_id, 20)) if hasattr(store, "list_project_tasks") else []
        learnings = list(store.list_project_learnings(project_id, 20)) if hasattr(store, "list_project_learnings") else []
        packet = retrieve_project_evidence(q, tasks, learnings, max_items=limit)
        return ProjectContextRetrievalOut(
            project_id=project_id,
            query=packet.query,
            items=[RetrievedEvidenceOut(kind=x.kind, record_id=x.record_id, score=x.score, reason=x.reason, text=x.text) for x in packet.items],
            context_text=packet.context_text,
        )

    @app.get("/v1/projects/{project_id}/repository", response_model=RepositorySnapshotOut)
    def get_project_repository(project_id: str) -> RepositorySnapshotOut:
        project = store.get_project(project_id) if hasattr(store, "get_project") else None
        if project is None:
            raise HTTPException(status_code=404, detail="project not found")
        try:
            snapshot = build_repository_snapshot(client, project.get("workspace_path"), max_changed=20)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return RepositorySnapshotOut(
            project_id=project_id, project_path=snapshot.project_path, branch=snapshot.branch, clean=snapshot.clean,
            changed_files=[RepositoryFileOut(path=x.path,status=x.status,size=x.size,sha256=x.sha256,preview=x.preview) for x in snapshot.changed_files],
            manifests=[RepositoryFileOut(path=x.path,status=x.status,size=x.size,sha256=x.sha256,preview=x.preview) for x in snapshot.manifests],
            context_text=snapshot.context_text,
        )

    @app.post("/v1/plans", response_model=PlanCreateResponse)
    def create_plan(req: PlanCreateRequest) -> PlanCreateResponse:
        project = None
        if req.project_id:
            project = store.get_project(req.project_id) if hasattr(store,"get_project") else None
            if project is None: raise HTTPException(status_code=404, detail="project not found")
        if not hasattr(store,"create_plan"): raise HTTPException(status_code=501, detail="planning unavailable")
        generated=build_plan(req.prompt,project)
        try: plan,owner_token=store.create_plan(generated["objective"],req.project_id,generated["steps"],generated["acceptance_criteria"],generated["risks"])
        except Exception as exc: raise HTTPException(status_code=503, detail="plan store unavailable") from exc
        return PlanCreateResponse(plan=_plan_summary(plan), owner_token=owner_token)

    @app.get("/v1/plans", response_model=list[PlanSummary])
    def list_plans(project_id: str | None = None, limit: int = 100) -> list[PlanSummary]:
        if not hasattr(store,"list_plans"): return []
        return [_plan_summary(x) for x in store.list_plans(project_id,limit)]

    @app.get("/v1/plans/{plan_id}", response_model=PlanSummary)
    def get_plan(plan_id: str) -> PlanSummary:
        plan=store.get_plan(plan_id) if hasattr(store,"get_plan") else None
        if plan is None: raise HTTPException(status_code=404, detail="plan not found")
        return _plan_summary(plan)

    @app.get("/v1/plans/{plan_id}/context", response_model=PlanContextOut)
    def get_plan_context(plan_id: str) -> PlanContextOut:
        plan=store.get_plan(plan_id) if hasattr(store,"get_plan") else None
        if plan is None: raise HTTPException(status_code=404, detail="plan not found")
        return PlanContextOut(plan=_plan_summary(plan), context_text=_plan_context(plan_id))

    @app.post("/v1/plans/{plan_id}/approve", response_model=PlanSummary)
    def approve_plan(plan_id: str, req: PlanApprovalRequest, owner_token: str | None = Header(None, alias="x-tc-plan-owner-token")) -> PlanSummary:
        plan=store.get_plan(plan_id) if hasattr(store,"get_plan") else None
        if plan is None: raise HTTPException(status_code=404, detail="plan not found")
        if not owner_token or not store.verify_plan_owner(plan_id,owner_token): raise HTTPException(status_code=403, detail="invalid plan owner token")
        if plan["status"] != "DRAFT": raise HTTPException(status_code=409, detail="plan is no longer editable")
        try: updated=store.update_plan(plan_id,status="READY" if req.approved else "FAILED")
        except InvalidTransition as exc: raise HTTPException(status_code=409,detail=str(exc)) from exc
        return _plan_summary(updated)

    @app.post("/v1/tasks", response_model=TaskSummary)
    def create_task(req: TaskRequest, response: Response) -> TaskSummary:
        if req.project_id:
            project = store.get_project(req.project_id) if hasattr(store, "get_project") else None
            if project is None:
                raise HTTPException(status_code=404, detail="project not found")
        if req.plan_id:
            plan = store.get_plan(req.plan_id) if hasattr(store, "get_plan") else None
            if plan is None:
                raise HTTPException(status_code=404, detail="plan not found")
            if plan["status"] != "READY":
                raise HTTPException(status_code=409, detail="plan must be READY before execution")
            if req.project_id and plan.get("project_id") != req.project_id:
                raise HTTPException(status_code=409, detail="plan and task project mismatch")
        try:
            summary, owner_token = store.create(req.prompt, max_steps=settings.max_agent_steps, project_id=req.project_id, plan_id=req.plan_id)
            if req.plan_id:
                store.update_plan(req.plan_id, status="EXECUTING")
        except InvalidTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=503, detail="task store unavailable") from exc

        # Return the owner token once, in a header (never logged, never to Brain).
        response.headers[OWNER_HEADER] = owner_token

        task_id = summary.task_id
        try:
            store.update(task_id, status=TaskStatus.RUNNING)
            store.add_event(task_id, "task_started", status=TaskStatus.RUNNING.value)
        except Exception as exc:  # noqa: BLE001
            return _fail(task_id, redactor.redact(str(exc)))

        orch = _build_orchestrator(
            settings,
            client,
            brain_override,
            learning_context=_learning_context() + ("\n\n" + _retrieved_project_context(req.project_id, req.prompt) if req.project_id else ""),
            project_context=_project_context(req.project_id),
            plan_context=_plan_context(req.plan_id),
            repository_context=_repository_context(req.project_id),
        )
        try:
            result = orch.run(req.prompt)
        except Exception as exc:  # noqa: BLE001
            return _fail(task_id, redactor.redact(str(exc)))
        return _apply_result(task_id, result, owner_token, req.prompt)

    def _require_owner(task_id: str, owner_token: str | None) -> None:
        if not owner_token:
            raise HTTPException(status_code=401, detail="owner token required")
        if not store.verify_owner(task_id, owner_token):
            raise HTTPException(status_code=403, detail="not authorized for this task")

    def _decide(
        task_id: str, req: ApprovalDecisionRequest, owner_token: str | None, approved: bool
    ):
        from .approval import ApprovalDecision, ApprovalError

        _require_owner(task_id, owner_token)
        summary = store.get(task_id)
        if summary is None:
            raise HTTPException(status_code=404, detail="task not found")
        if summary.status != TaskStatus.AWAITING_APPROVAL:
            raise HTTPException(
                status_code=409,
                detail=f"task not awaiting approval (status={summary.status.value})",
            )

        pending_view = store.get_pending_approval(task_id)
        if pending_view is None:
            raise HTTPException(status_code=409, detail="no pending approval")

        decision = ApprovalDecision(
            task_id=task_id, nonce=req.nonce, approved=approved, decided_by=req.decided_by
        )
        try:
            decided = store.decide_approval(decision, expected_tool=pending_view.tool_name)
        except ApprovalError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except InvalidTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        store.add_event(
            task_id,
            "approval_decided",
            tool_name=decided.tool_name,
            status="approved" if approved else "rejected",
            approval_nonce=decided.nonce,
            arguments_metadata=decided.arguments_metadata,
        )

        if not approved:
            store.update(task_id, status=TaskStatus.FAILED, error="action rejected by approver")
            store.add_event(task_id, "task_failed", status=TaskStatus.FAILED.value)
            if summary.plan_id and hasattr(store, "update_plan"):
                try:
                    store.update_plan(summary.plan_id, status="FAILED")
                except Exception:
                    pass
            pending_resume.pop(task_id, None)
            updated = store.get(task_id)
            return updated if updated else _fail(task_id, "lost task")

        # Approved: resume the loop executing the EXACT approved action.
        pend = pending_resume.pop(task_id, None)
        if pend is None:
            return _fail(task_id, "cannot resume: process restarted while awaiting approval")
        try:
            store.update(task_id, status=TaskStatus.RUNNING)
            orch = _build_orchestrator(
                settings,
                client,
                brain_override,
                learning_context=_learning_context() + ("\n\n" + _retrieved_project_context(summary.project_id, pend.get("prompt", "")) if summary.project_id else ""),
                project_context=_project_context(summary.project_id),
                plan_context=_plan_context(summary.plan_id),
                repository_context=_repository_context(summary.project_id),
            )
            result = orch.resume(pend["messages"], (decided.tool_name, pend["arguments"]))
        except Exception as exc:  # noqa: BLE001
            return _fail(task_id, redactor.redact(str(exc)))
        return _apply_result(task_id, result, pend["owner_token"], pend["prompt"])

    @app.post("/v1/tasks/{task_id}/approve", response_model=TaskSummary)
    def approve_task(
        task_id: str,
        req: ApprovalDecisionRequest,
        owner_token: str | None = Header(None, alias=OWNER_HEADER),
    ) -> TaskSummary:
        return _decide(task_id, req, owner_token, approved=True)

    @app.post("/v1/tasks/{task_id}/reject", response_model=TaskSummary)
    def reject_task(
        task_id: str,
        req: ApprovalDecisionRequest,
        owner_token: str | None = Header(None, alias=OWNER_HEADER),
    ) -> TaskSummary:
        return _decide(task_id, req, owner_token, approved=False)

    @app.get("/v1/tasks", response_model=list[TaskSummary])
    def list_tasks(
        status: TaskStatus | None = None,
        limit: int = 50,
    ) -> list[TaskSummary]:
        """List persisted task summaries without exposing owner tokens.

        This endpoint is intentionally read-only and returns only the metadata
        needed by the command center. Approval credentials remain owner-gated
        on the individual task endpoints.
        """
        limit = max(1, min(limit, 200))
        tasks = list(store.all())
        if status is not None:
            tasks = [task for task in tasks if task.status == status]
        tasks.sort(key=lambda task: task.updated_at or task.created_at or "", reverse=True)
        return tasks[:limit]

    @app.get("/v1/tasks/{task_id}", response_model=TaskSummary)
    def get_task(task_id: str) -> TaskSummary:
        summary = store.get(task_id)
        if summary is None:
            raise HTTPException(status_code=404, detail="task not found")
        return summary

    @app.get("/v1/tasks/{task_id}/brain", response_model=TaskBrainUsageOut)
    def get_task_brain_usage(task_id: str) -> TaskBrainUsageOut:
        summary = store.get(task_id)
        if summary is None:
            raise HTTPException(status_code=404, detail="task not found")
        calls = []
        for event in store.list_events(task_id):
            if event.get("event_type") != "brain_call":
                continue
            meta = event.get("result_metadata") or {}
            calls.append(BrainUsageOut(
                route=str(meta.get("route", "primary")),
                model=str(meta.get("model", settings.brain_model)),
                reason=str(meta.get("reason", "")),
                input_tokens=int(meta.get("input_tokens", 0) or 0),
                output_tokens=int(meta.get("output_tokens", 0) or 0),
                total_tokens=int(meta.get("total_tokens", 0) or 0),
                estimated_cost_usd=float(meta.get("estimated_cost_usd", 0.0) or 0.0),
                fallback=bool(meta.get("fallback", False)),
            ))
        return TaskBrainUsageOut(
            task_id=task_id,
            calls=calls,
            total_input_tokens=sum(c.input_tokens for c in calls),
            total_output_tokens=sum(c.output_tokens for c in calls),
            total_tokens=sum(c.total_tokens for c in calls),
            estimated_cost_usd=round(sum(c.estimated_cost_usd for c in calls), 8),
            higher_calls=sum(c.route == "higher" for c in calls),
            current_route=(calls[-1].route if calls else "primary"),
        )

    @app.get("/v1/tasks/{task_id}/evaluation", response_model=TaskEvaluationOut)
    def get_task_evaluation(task_id: str) -> TaskEvaluationOut:
        """Return deterministic execution-quality evidence for one task.

        This is deliberately not an LLM quality judgment: it scores only
        observable execution signals from task state and persisted events.
        """
        summary = store.get(task_id)
        if summary is None:
            raise HTTPException(status_code=404, detail="task not found")
        evaluation = evaluate_task(summary, store.list_events(task_id))
        return TaskEvaluationOut(
            task_id=evaluation.task_id,
            overall_score=evaluation.overall_score,
            verdict=evaluation.verdict,
            dimensions=[
                {
                    "key": dimension.key,
                    "label": dimension.label,
                    "score": dimension.score,
                    "evidence": dimension.evidence,
                }
                for dimension in evaluation.dimensions
            ],
            total_events=evaluation.total_events,
            approvals_requested=evaluation.approvals_requested,
            approvals_decided=evaluation.approvals_decided,
            repair_signals=evaluation.repair_signals,
            verification_signals=evaluation.verification_signals,
        )

    @app.get("/v1/tasks/{task_id}/recovery", response_model=TaskRecoveryOut)
    def get_task_recovery(task_id: str) -> TaskRecoveryOut:
        summary = store.get(task_id)
        if summary is None:
            raise HTTPException(status_code=404, detail="task not found")
        decision = classify_failure(summary, store.list_events(task_id), max_repair_attempts=settings.max_repair_attempts)
        return TaskRecoveryOut(
            task_id=task_id,
            recovery_class=decision.recovery_class,
            severity=decision.severity,
            repair_attempts=decision.repair_attempts,
            max_repair_attempts=decision.max_repair_attempts,
            retry_allowed=decision.retry_allowed,
            recommended_action=decision.recommended_action,
            evidence=list(decision.evidence),
        )

    @app.get("/v1/tasks/{task_id}/events", response_model=list[TaskEventOut])
    def get_events(task_id: str) -> list[TaskEventOut]:
        summary = store.get(task_id)
        if summary is None:
            raise HTTPException(status_code=404, detail="task not found")
        events = store.list_events(task_id)
        return [
            TaskEventOut(
                id=e["id"],
                task_id=e["task_id"],
                ts=e["ts"],
                event_type=e["event_type"],
                tool_name=e.get("tool_name"),
                arguments_metadata=e.get("arguments_metadata"),
                result_metadata=e.get("result_metadata"),
                status=e.get("status"),
            )
            for e in events
        ]

    @app.get("/v1/tasks/{task_id}/events/stream")
    async def stream_events(task_id: str):
        """Stream task events as Server-Sent Events until the task is terminal."""
        summary = store.get(task_id)
        if summary is None:
            raise HTTPException(status_code=404, detail="task not found")

        async def generate():
            sent_ids: set[int] = set()
            deadline = asyncio.get_running_loop().time() + 900
            while asyncio.get_running_loop().time() < deadline:
                events = store.list_events(task_id)
                for event in events:
                    event_id = int(event["id"])
                    if event_id in sent_ids:
                        continue
                    sent_ids.add(event_id)
                    payload = {
                        "id": event_id,
                        "task_id": event["task_id"],
                        "ts": event["ts"],
                        "event_type": event["event_type"],
                        "tool_name": event.get("tool_name"),
                        "arguments_metadata": event.get("arguments_metadata"),
                        "result_metadata": event.get("result_metadata"),
                        "status": event.get("status"),
                    }
                    data = json.dumps(payload, separators=(",", ":"))
                    yield f"id: {event_id}\ndata: {data}\n\n"
                current = store.get(task_id)
                if current is None or current.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                    return
                yield ": heartbeat\n\n"
                await asyncio.sleep(1)

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/v1/tasks/{task_id}/pending_approval", response_model=ApprovalView)
    def get_pending_approval(
        task_id: str,
        owner_token: str | None = Header(None, alias=OWNER_HEADER),
    ) -> ApprovalView:
        _require_owner(task_id, owner_token)
        summary = store.get(task_id)
        if summary is None:
            raise HTTPException(status_code=404, detail="task not found")
        pending = store.get_pending_approval(task_id)
        if pending is None:
            raise HTTPException(status_code=409, detail="no pending approval")
        return ApprovalView(
            task_id=pending.task_id,
            tool_name=pending.tool_name,
            arguments_metadata=pending.arguments_metadata,
            risk_level=pending.risk_level,
            created_at=pending.created_at.isoformat(),
            expires_at=pending.expires_at.isoformat(),
            nonce=pending.nonce,
        )

    @app.get("/v1/learnings", response_model=list[LearningOut])
    def list_learnings(limit: int = 20) -> list[LearningOut]:
        """Return recent deterministic engineering lessons, without secrets."""
        if not hasattr(store, "list_learnings"):
            return []
        try:
            items = store.list_learnings(limit)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=503, detail="learning store unavailable") from exc
        return [LearningOut(**item) for item in items]


    if owns_client:

        @app.on_event("shutdown")
        def _shutdown() -> None:  # type: ignore[unused-variable]
            client.close()

    return app


def app() -> FastAPI:
    return create_app()
