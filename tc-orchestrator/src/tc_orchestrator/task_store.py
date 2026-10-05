"""In-memory task store (test double / fallback).

Implements the same surface as ``PgTaskStore`` so it can be swapped in for
tests that do not need PostgreSQL. When a ``DATABASE_URL`` is configured the
PostgreSQL-backed store is used instead.
"""

from __future__ import annotations

import secrets
import uuid
from collections.abc import Iterable
from threading import Lock

from .approval import (
    ApprovalActionMismatchError,
    ApprovalAlreadyDecidedError,
    ApprovalDecision,
    ApprovalExpiredError,
    ApprovalNotFoundError,
    ApprovalRequest,
    expiry_from_now,
    hash_token,
    new_nonce,
    utcnow,
)
from .models import PlanStatus, TaskStatus, TaskSummary
from .learning import Learning
from .transitions import InvalidTransition, is_terminal, validate_transition


class TaskStore:
    """In-memory store with the Step 4 surface (tasks + events + approvals)."""

    def __init__(self) -> None:
        self._tasks: dict[str, TaskSummary] = {}
        self._owner_hashes: dict[str, str] = {}
        self._events: list[dict] = []
        self._approvals: dict[str, dict] = {}  # nonce -> record
        self._learnings: list[dict] = []
        self._projects: dict[str, dict] = {}
        self._plans: dict[str, dict] = {}
        self._plan_owner_hashes: dict[str, str] = {}
        self._lock = Lock()

    def create(self, prompt: str, max_steps: int = 20, project_id: str | None = None, plan_id: str | None = None) -> tuple[TaskSummary, str]:
        task_id = uuid.uuid4().hex
        owner_token = secrets.token_urlsafe(32)
        summary = TaskSummary(
            task_id=task_id,
            status=TaskStatus.PENDING,
            prompt=prompt,
            max_steps=max_steps,
            project_id=project_id,
            plan_id=plan_id,
        )
        with self._lock:
            self._tasks[task_id] = summary
            self._owner_hashes[task_id] = hash_token(owner_token)
        return summary, owner_token

    def update(self, task_id: str, **fields: object) -> TaskSummary | None:
        with self._lock:
            summary = self._tasks.get(task_id)
            if summary is None:
                return None
            status_val = fields.get("status")
            if status_val is not None:
                target = (
                    TaskStatus(status_val) if not isinstance(status_val, TaskStatus) else status_val
                )
                validate_transition(summary.status, target)
                fields["status"] = target
            if "steps" in fields:
                # Keep the legacy `steps` and `current_step` fields in sync.
                fields["current_step"] = fields["steps"]
            new = summary.model_copy(update=fields)
            self._tasks[task_id] = new
            return new

    def get(self, task_id: str) -> TaskSummary | None:
        with self._lock:
            return self._tasks.get(task_id)

    def all(self) -> Iterable[TaskSummary]:
        with self._lock:
            return list(self._tasks.values())


    def create_plan(self, objective: str, project_id: str | None, steps: list[dict], acceptance_criteria: list[str], risks: list[str]):
        plan_id = uuid.uuid4().hex
        owner_token = secrets.token_urlsafe(32)
        now = utcnow().isoformat()
        with self._lock:
            self._plans[plan_id] = {"plan_id": plan_id, "status": PlanStatus.DRAFT.value, "objective": objective, "project_id": project_id, "steps": steps, "acceptance_criteria": acceptance_criteria, "risks": risks, "created_at": now, "updated_at": now}
            self._plan_owner_hashes[plan_id] = hash_token(owner_token)
        return dict(self._plans[plan_id]), owner_token

    def get_plan(self, plan_id: str):
        with self._lock:
            item = self._plans.get(plan_id)
            return dict(item) if item else None

    def verify_plan_owner(self, plan_id: str, raw_owner_token: str) -> bool:
        with self._lock:
            expected = self._plan_owner_hashes.get(plan_id)
        return expected is not None and expected == hash_token(raw_owner_token)

    def update_plan(self, plan_id: str, **fields):
        with self._lock:
            plan = self._plans.get(plan_id)
            if plan is None: return None
            current = PlanStatus(plan["status"])
            if "status" in fields:
                target = PlanStatus(fields["status"])
                allowed = {PlanStatus.DRAFT:{PlanStatus.READY,PlanStatus.FAILED}, PlanStatus.READY:{PlanStatus.EXECUTING,PlanStatus.FAILED}, PlanStatus.EXECUTING:{PlanStatus.COMPLETED,PlanStatus.FAILED}, PlanStatus.COMPLETED:set(), PlanStatus.FAILED:set()}
                if target != current and target not in allowed[current]:
                    raise InvalidTransition(f"invalid plan transition {current.value} -> {target.value}")
                plan["status"] = target.value
            for key in ("objective","steps","acceptance_criteria","risks"):
                if key in fields: plan[key] = fields[key]
            plan["updated_at"] = utcnow().isoformat()
            return dict(plan)

    def list_plans(self, project_id: str | None = None, limit: int = 100):
        with self._lock:
            items = list(self._plans.values())
            if project_id: items = [p for p in items if p.get("project_id") == project_id]
            items.sort(key=lambda p:p["updated_at"], reverse=True)
            return [dict(p) for p in items[:max(1,min(limit,200))]]

    def create_project(self, name: str, description: str, workspace_path: str):
        project_id = uuid.uuid4().hex
        now = utcnow().isoformat()
        with self._lock:
            if any(p["name"] == name for p in self._projects.values()):
                raise ValueError("project name already exists")
            self._projects[project_id] = {"id":project_id,"name":name,"description":description,"workspace_path":workspace_path,"created_at":now,"updated_at":now}
            return dict(self._projects[project_id], task_count=0)

    def get_project(self, project_id: str):
        with self._lock:
            p=self._projects.get(project_id)
            if p is None: return None
            count=sum(1 for t in self._tasks.values() if t.project_id == project_id)
            return dict(p, task_count=count)

    def list_projects(self, limit: int = 100):
        with self._lock:
            projects=[dict(p, task_count=sum(1 for t in self._tasks.values() if t.project_id == pid)) for pid,p in self._projects.items()]
            projects.sort(key=lambda p:p["updated_at"], reverse=True)
            return projects[:max(1,min(limit,200))]

    def update_project(self, project_id: str, **fields):
        with self._lock:
            p=self._projects.get(project_id)
            if p is None: return None
            for k in ("name","description"):
                if fields.get(k) is not None: p[k]=fields[k]
            p["updated_at"]=utcnow().isoformat()
            count=sum(1 for t in self._tasks.values() if t.project_id == project_id)
            return dict(p, task_count=count)

    def delete_project(self, project_id: str) -> bool:
        with self._lock:
            if project_id not in self._projects: return False
            self._projects.pop(project_id)
            for tid, task in list(self._tasks.items()):
                if task.project_id == project_id:
                    self._tasks[tid]=task.model_copy(update={"project_id":None})
            return True

    def verify_owner(self, task_id: str, raw_owner_token: str) -> bool:
        with self._lock:
            expected = self._owner_hashes.get(task_id)
        return expected is not None and expected == hash_token(raw_owner_token)

    def add_event(
        self,
        task_id,
        event_type,
        *,
        tool_name=None,
        arguments_metadata=None,
        result_metadata=None,
        status=None,
        approval_nonce=None,
    ) -> int:
        with self._lock:
            self._events.append(
                {
                    "id": len(self._events) + 1,
                    "task_id": task_id,
                    "event_type": event_type,
                    "tool_name": tool_name,
                    "arguments_metadata": arguments_metadata,
                    "result_metadata": result_metadata,
                    "status": status,
                    "approval_nonce": approval_nonce,
                    "ts": utcnow().isoformat(),
                }
            )
            return self._events[-1]["id"]

    def list_events(self, task_id: str) -> list[dict]:
        with self._lock:
            return [dict(e) for e in self._events if e["task_id"] == task_id]

    def create_approval(
        self, task_id, tool_name, arguments_metadata, risk_level, expiry_seconds
    ) -> ApprovalRequest:
        nonce = new_nonce()
        created = utcnow()
        expires = expiry_from_now(expiry_seconds)
        with self._lock:
            self._approvals[nonce] = {
                "task_id": task_id,
                "tool_name": tool_name,
                "arguments_metadata": arguments_metadata,
                "risk_level": risk_level,
                "nonce": nonce,
                "created_at": created,
                "expires_at": expires,
                "status": "pending",
                "decided_by": None,
            }
        return ApprovalRequest(
            task_id=task_id,
            tool_name=tool_name,
            arguments_metadata=arguments_metadata,
            risk_level=risk_level,
            nonce=nonce,
            created_at=created,
            expires_at=expires,
        )

    def get_pending_approval(self, task_id: str) -> ApprovalRequest | None:
        with self._lock:
            for rec in reversed(list(self._approvals.values())):
                if rec["task_id"] == task_id and rec["status"] == "pending":
                    return ApprovalRequest(
                        task_id=rec["task_id"],
                        tool_name=rec["tool_name"],
                        arguments_metadata=rec["arguments_metadata"],
                        risk_level=rec["risk_level"],
                        nonce=rec["nonce"],
                        created_at=rec["created_at"],
                        expires_at=rec["expires_at"],
                    )
        return None

    def decide_approval(self, decision: ApprovalDecision, expected_tool: str) -> ApprovalRequest:
        with self._lock:
            rec = self._approvals.get(decision.nonce)
            if rec is None:
                raise ApprovalNotFoundError("no approval for nonce")
            if rec["status"] != "pending":
                raise ApprovalAlreadyDecidedError(
                    f"approval already {rec['status']} (nonce not reusable)"
                )
            if utcnow() >= rec["expires_at"]:
                rec["status"] = "expired"
                raise ApprovalExpiredError("approval expired")
            if rec["tool_name"] != expected_tool or rec["task_id"] != decision.task_id:
                raise ApprovalActionMismatchError("action mismatch")
            task = self._tasks.get(rec["task_id"])
            if task is None:
                raise ApprovalNotFoundError("task not found")
            if is_terminal(task.status):
                raise InvalidTransition("cannot approve an action for a terminal task")
            rec["status"] = "approved" if decision.approved else "rejected"
            rec["decided_by"] = decision.decided_by
            return ApprovalRequest(
                task_id=rec["task_id"],
                tool_name=rec["tool_name"],
                arguments_metadata=rec["arguments_metadata"],
                risk_level=rec["risk_level"],
                nonce=rec["nonce"],
                created_at=rec["created_at"],
                expires_at=rec["expires_at"],
            )

    def add_learning(self, task_id: str | None, learning: Learning) -> int:
        with self._lock:
            self._learnings.append({
                "id": len(self._learnings) + 1,
                "task_id": task_id,
                "category": learning.category,
                "lesson": learning.lesson,
                "evidence": learning.evidence,
                "score": learning.score,
                "created_at": utcnow().isoformat(),
            })
            return self._learnings[-1]["id"]

    def list_learnings(self, limit: int = 20) -> list[dict]:
        with self._lock:
            return [dict(x) for x in self._learnings[-max(1, min(limit, 100)):]][::-1]

    def list_project_tasks(self, project_id: str, limit: int = 20) -> list[TaskSummary]:
        with self._lock:
            tasks = [t for t in self._tasks.values() if t.project_id == project_id]
            tasks.sort(key=lambda t: t.updated_at or t.created_at or "", reverse=True)
            return list(tasks[: max(1, min(limit, 100))])

    def list_project_learnings(self, project_id: str, limit: int = 20) -> list[dict]:
        with self._lock:
            task_ids = {t.task_id for t in self._tasks.values() if t.project_id == project_id}
            items = [x for x in self._learnings if x.get("task_id") in task_ids]
            return [dict(x) for x in items[-max(1, min(limit, 100)):]][::-1]


# Module-level default store (replaceable for tests). When a DATABASE_URL is
# present, callers should use build_default_store() which returns a PgTaskStore.
_default_store: TaskStore | None = None


def get_default_store() -> TaskStore:
    global _default_store
    if _default_store is None:
        _default_store = TaskStore()
    return _default_store


def set_default_store(store: TaskStore) -> None:
    global _default_store
    _default_store = store
