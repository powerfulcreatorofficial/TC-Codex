"""PostgreSQL-backed task store (Step 4).

Implements the same surface as the in-memory ``TaskStore`` plus event history
and approval persistence. All stored metadata is redacted by the orchestrator
before being written; this store never holds raw secrets.

State transitions are validated against ``transitions.py``; the API cannot set
arbitrary states. Approval nonces are single-use.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterable
from typing import Any, Protocol

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
    new_owner_token,
    utcnow,
)
from .db import Database
from .models import PlanStatus, TaskStatus, TaskSummary
from .learning import Learning
from .transitions import InvalidTransition, is_terminal, validate_transition


class TaskStoreProtocol(Protocol):
    def create(self, prompt: str, max_steps: int = 20, project_id: str | None = None, plan_id: str | None = None) -> tuple[TaskSummary, str]: ...

    def update(self, task_id: str, **fields: object) -> TaskSummary | None: ...

    def get(self, task_id: str) -> TaskSummary | None: ...

    def all(self) -> Iterable[TaskSummary]: ...

    def create_project(self, name: str, description: str, workspace_path: str): ...
    def get_project(self, project_id: str): ...
    def list_projects(self, limit: int = 100): ...
    def update_project(self, project_id: str, **fields: object): ...
    def delete_project(self, project_id: str) -> bool: ...
    def create_plan(self, objective: str, project_id: str | None, steps: list[dict], acceptance_criteria: list[str], risks: list[str]): ...
    def get_plan(self, plan_id: str): ...
    def verify_plan_owner(self, plan_id: str, raw_owner_token: str) -> bool: ...
    def update_plan(self, plan_id: str, **fields): ...
    def list_plans(self, project_id: str | None = None, limit: int = 100): ...


def _row_to_summary(row: tuple) -> TaskSummary:
    (
        task_id,
        prompt,
        status,
        answer,
        error,
        current_step,
        max_steps,
        owner_token_hash,
        created_at,
        updated_at,
        project_id,
        plan_id,
    ) = row
    return TaskSummary(
        task_id=task_id,
        status=TaskStatus(status),
        prompt=prompt,
        answer=answer,
        error=error,
        steps=current_step,
        current_step=current_step,
        max_steps=max_steps,
        created_at=created_at.isoformat() if created_at else None,
        updated_at=updated_at.isoformat() if updated_at else None,
        project_id=project_id,
        plan_id=plan_id,
    )


class PgTaskStore:
    """PostgreSQL-backed implementation of the task store."""

    def __init__(self, database: Database) -> None:
        self._db = database

    # ---- tasks ----

    def create(self, prompt: str, max_steps: int = 20, project_id: str | None = None, plan_id: str | None = None) -> tuple[TaskSummary, str]:
        """Create a task. Returns (summary, raw_owner_token). The raw token is
        returned exactly once and is never stored or logged."""
        task_id = uuid.uuid4().hex
        owner_token = new_owner_token()
        owner_hash = hash_token(owner_token)
        with self._db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO tasks (id, prompt, status, max_steps, owner_token_hash, project_id, plan_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, prompt, status, answer, error, current_step,
                              max_steps, owner_token_hash, created_at, updated_at, project_id, plan_id
                    """,
                    (task_id, prompt, TaskStatus.PENDING.value, max_steps, owner_hash, project_id, plan_id),
                )
                row = cur.fetchone()
        return _row_to_summary(row), owner_token

    def update(self, task_id: str, **fields: object) -> TaskSummary | None:
        """Update a task. If ``status`` is supplied, the transition is validated
        against the current persisted status (atomic, transition-safe)."""
        if not fields:
            return self.get(task_id)

        status_val = fields.get("status")
        with self._db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT status FROM tasks WHERE id = %s FOR UPDATE",
                    (task_id,),
                )
                row = cur.fetchone()
                if row is None:
                    return None
                current_status = TaskStatus(row[0])

                if status_val is not None:
                    target = (
                        TaskStatus(status_val)
                        if not isinstance(status_val, TaskStatus)
                        else status_val
                    )
                    validate_transition(current_status, target)
                    fields["status"] = target.value

                # Map TaskSummary field names -> column names.
                col_map = {
                    "status": "status",
                    "answer": "answer",
                    "error": "error",
                    "steps": "current_step",
                    "current_step": "current_step",
                    "max_steps": "max_steps",
                }
                sets: list[str] = []
                vals: list[Any] = []
                for k, v in fields.items():
                    col = col_map.get(k, k)
                    sets.append(f'"{col}" = %s')
                    vals.append(v)
                sets.append("updated_at = now()")
                vals.append(task_id)
                cur.execute(
                    f"UPDATE tasks SET {', '.join(sets)} WHERE id = %s "  # noqa: S608
                    f"RETURNING id, prompt, status, answer, error, current_step, "
                    f"max_steps, owner_token_hash, created_at, updated_at, project_id, plan_id",
                    vals,
                )
                row = cur.fetchone()
        return _row_to_summary(row) if row else None

    def get(self, task_id: str) -> TaskSummary | None:
        with self._db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, prompt, status, answer, error, current_step, "
                    "max_steps, owner_token_hash, created_at, updated_at, project_id, plan_id "
                    "FROM tasks WHERE id = %s",
                    (task_id,),
                )
                row = cur.fetchone()
        return _row_to_summary(row) if row else None

    def all(self) -> Iterable[TaskSummary]:
        with self._db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, prompt, status, answer, error, current_step, "
                    "max_steps, owner_token_hash, created_at, updated_at, project_id, plan_id "
                    "FROM tasks ORDER BY created_at DESC"
                )
                rows = cur.fetchall()
        return [_row_to_summary(r) for r in rows]

    def create_project(self, name: str, description: str, workspace_path: str):
        project_id = uuid.uuid4().hex
        with self._db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO tc_projects (id, name, description, workspace_path) VALUES (%s, %s, %s, %s) "
                    "RETURNING id, name, description, workspace_path, created_at, updated_at",
                    (project_id, name, description, workspace_path),
                )
                row = cur.fetchone()
        return {
            "id": row[0], "name": row[1], "description": row[2], "workspace_path": row[3],
            "task_count": 0, "created_at": row[4].isoformat(), "updated_at": row[5].isoformat(),
        }

    def get_project(self, project_id: str):
        with self._db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT p.id, p.name, p.description, p.workspace_path, p.created_at, p.updated_at, "
                    "COUNT(t.id) FROM tc_projects p LEFT JOIN tasks t ON t.project_id=p.id "
                    "WHERE p.id=%s GROUP BY p.id",
                    (project_id,),
                )
                row=cur.fetchone()
        if not row: return None
        return {"id":row[0],"name":row[1],"description":row[2],"workspace_path":row[3],"created_at":row[4].isoformat(),"updated_at":row[5].isoformat(),"task_count":int(row[6])}

    def list_projects(self, limit: int = 100):
        limit=max(1,min(limit,200))
        with self._db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT p.id, p.name, p.description, p.workspace_path, p.created_at, p.updated_at, COUNT(t.id) "
                    "FROM tc_projects p LEFT JOIN tasks t ON t.project_id=p.id "
                    "GROUP BY p.id ORDER BY p.updated_at DESC LIMIT %s", (limit,)
                )
                rows=cur.fetchall()
        return [{"id":r[0],"name":r[1],"description":r[2],"workspace_path":r[3],"created_at":r[4].isoformat(),"updated_at":r[5].isoformat(),"task_count":int(r[6])} for r in rows]

    def update_project(self, project_id: str, **fields):
        allowed={k:v for k,v in fields.items() if k in {"name","description"} and v is not None}
        if not allowed: return self.get_project(project_id)
        sets=[f'"{k}"=%s' for k in allowed]
        vals=list(allowed.values())+[project_id]
        with self._db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(f"UPDATE tc_projects SET {', '.join(sets)}, updated_at=now() WHERE id=%s", vals)
        return self.get_project(project_id)

    def delete_project(self, project_id: str) -> bool:
        with self._db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM tc_projects WHERE id=%s", (project_id,))
                return cur.rowcount > 0


    def create_plan(self, objective: str, project_id: str | None, steps: list[dict], acceptance_criteria: list[str], risks: list[str]):
        plan_id = uuid.uuid4().hex
        owner_token = new_owner_token()
        with self._db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""INSERT INTO tc_plans (id, objective, status, project_id, steps, acceptance_criteria, risks, owner_token_hash) VALUES (%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s) RETURNING id, objective, status, project_id, steps, acceptance_criteria, risks, created_at, updated_at""", (plan_id, objective, PlanStatus.DRAFT.value, project_id, json.dumps(steps), json.dumps(acceptance_criteria), json.dumps(risks), hash_token(owner_token)))
                r=cur.fetchone()
        return {"plan_id":r[0],"objective":r[1],"status":r[2],"project_id":r[3],"steps":r[4],"acceptance_criteria":r[5],"risks":r[6],"created_at":r[7].isoformat(),"updated_at":r[8].isoformat()}, owner_token

    def get_plan(self, plan_id: str):
        with self._db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id, objective, status, project_id, steps, acceptance_criteria, risks, created_at, updated_at FROM tc_plans WHERE id=%s", (plan_id,))
                r=cur.fetchone()
        if not r: return None
        return {"plan_id":r[0],"objective":r[1],"status":r[2],"project_id":r[3],"steps":r[4],"acceptance_criteria":r[5],"risks":r[6],"created_at":r[7].isoformat(),"updated_at":r[8].isoformat()}

    def verify_plan_owner(self, plan_id: str, raw_owner_token: str) -> bool:
        with self._db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT owner_token_hash FROM tc_plans WHERE id=%s", (plan_id,))
                r=cur.fetchone()
        return bool(r and r[0] == hash_token(raw_owner_token))

    def update_plan(self, plan_id: str, **fields):
        current=self.get_plan(plan_id)
        if current is None: return None
        if "status" in fields:
            target=PlanStatus(fields["status"]); cur_status=PlanStatus(current["status"])
            allowed={PlanStatus.DRAFT:{PlanStatus.READY,PlanStatus.FAILED},PlanStatus.READY:{PlanStatus.EXECUTING,PlanStatus.FAILED},PlanStatus.EXECUTING:{PlanStatus.COMPLETED,PlanStatus.FAILED},PlanStatus.COMPLETED:set(),PlanStatus.FAILED:set()}
            if target != cur_status and target not in allowed[cur_status]: raise InvalidTransition(f"invalid plan transition {cur_status.value} -> {target.value}")
            fields["status"]=target.value
        mapping={"objective":"objective","status":"status","steps":"steps","acceptance_criteria":"acceptance_criteria","risks":"risks"}
        sets=[]; vals=[]
        for key,col in mapping.items():
            if key in fields:
                if key in {"steps","acceptance_criteria","risks"}: sets.append(f'"{col}"=%s::jsonb'); vals.append(json.dumps(fields[key]))
                else: sets.append(f'"{col}"=%s'); vals.append(fields[key])
        if not sets: return current
        vals.append(plan_id)
        with self._db.connect() as conn:
            with conn.cursor() as cur: cur.execute(f"UPDATE tc_plans SET {', '.join(sets)}, updated_at=now() WHERE id=%s", vals)
        return self.get_plan(plan_id)

    def list_plans(self, project_id: str | None = None, limit: int = 100):
        limit=max(1,min(limit,200))
        with self._db.connect() as conn:
            with conn.cursor() as cur:
                if project_id: cur.execute("SELECT id, objective, status, project_id, steps, acceptance_criteria, risks, created_at, updated_at FROM tc_plans WHERE project_id=%s ORDER BY updated_at DESC LIMIT %s", (project_id,limit))
                else: cur.execute("SELECT id, objective, status, project_id, steps, acceptance_criteria, risks, created_at, updated_at FROM tc_plans ORDER BY updated_at DESC LIMIT %s", (limit,))
                rows=cur.fetchall()
        return [{"plan_id":r[0],"objective":r[1],"status":r[2],"project_id":r[3],"steps":r[4],"acceptance_criteria":r[5],"risks":r[6],"created_at":r[7].isoformat(),"updated_at":r[8].isoformat()} for r in rows]

    def verify_owner(self, task_id: str, raw_owner_token: str) -> bool:
        """Constant-time-ish owner check (hash compare). Never logs the token."""
        owner_hash = hash_token(raw_owner_token)
        with self._db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM tasks WHERE id = %s AND owner_token_hash = %s",
                    (task_id, owner_hash),
                )
                return cur.fetchone() is not None

    # ---- events ----

    def add_event(
        self,
        task_id: str,
        event_type: str,
        *,
        tool_name: str | None = None,
        arguments_metadata: dict | None = None,
        result_metadata: dict | None = None,
        status: str | None = None,
        approval_nonce: str | None = None,
    ) -> int:
        with self._db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO task_events
                        (task_id, event_type, tool_name, arguments_metadata,
                         result_metadata, status, approval_nonce)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        task_id,
                        event_type,
                        tool_name,
                        json.dumps(arguments_metadata) if arguments_metadata else None,
                        json.dumps(result_metadata) if result_metadata else None,
                        status,
                        approval_nonce,
                    ),
                )
                return int(cur.fetchone()[0])

    def list_events(self, task_id: str) -> list[dict]:
        with self._db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, task_id, ts, event_type, tool_name, "
                    "arguments_metadata, result_metadata, status, approval_nonce "
                    "FROM task_events WHERE task_id = %s ORDER BY ts ASC, id ASC",
                    (task_id,),
                )
                cols = [d.name for d in cur.description]
                rows = [dict(zip(cols, r, strict=False)) for r in cur.fetchall()]
        for r in rows:
            if r.get("ts") is not None:
                r["ts"] = r["ts"].isoformat()
            for k in ("arguments_metadata", "result_metadata"):
                v = r.get(k)
                if isinstance(v, str):
                    r[k] = json.loads(v)
        return rows

    def add_learning(self, task_id: str | None, learning: Learning) -> int:
        with self._db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO tc_learnings (task_id, category, lesson, evidence, score)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (task_id, learning.category, learning.lesson, learning.evidence, learning.score),
                )
                return int(cur.fetchone()[0])

    def list_learnings(self, limit: int = 20) -> list[dict]:
        limit = max(1, min(limit, 100))
        with self._db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, task_id, category, lesson, evidence, score, created_at "
                    "FROM tc_learnings ORDER BY created_at DESC, id DESC LIMIT %s",
                    (limit,),
                )
                rows = cur.fetchall()
        return [
            {
                "id": r[0],
                "task_id": r[1],
                "category": r[2],
                "lesson": r[3],
                "evidence": r[4],
                "score": r[5],
                "created_at": r[6].isoformat() if r[6] else None,
            }
            for r in rows
        ]

    def list_project_tasks(self, project_id: str, limit: int = 20) -> list[TaskSummary]:
        limit = max(1, min(limit, 100))
        with self._db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, prompt, status, answer, error, current_step, max_steps, "
                    "owner_token_hash, created_at, updated_at, project_id, plan_id "
                    "FROM tasks WHERE project_id=%s ORDER BY updated_at DESC, created_at DESC LIMIT %s",
                    (project_id, limit),
                )
                rows = cur.fetchall()
        return [_row_to_summary(r) for r in rows]

    def list_project_learnings(self, project_id: str, limit: int = 20) -> list[dict]:
        limit = max(1, min(limit, 100))
        with self._db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT l.id, l.task_id, l.category, l.lesson, l.evidence, l.score, l.created_at "
                    "FROM tc_learnings l JOIN tasks t ON t.id=l.task_id "
                    "WHERE t.project_id=%s ORDER BY l.created_at DESC, l.id DESC LIMIT %s",
                    (project_id, limit),
                )
                rows = cur.fetchall()
        return [
            {"id": r[0], "task_id": r[1], "category": r[2], "lesson": r[3], "evidence": r[4], "score": r[5], "created_at": r[6].isoformat() if r[6] else None}
            for r in rows
        ]

    # ---- approvals ----

    def create_approval(
        self,
        task_id: str,
        tool_name: str,
        arguments_metadata: dict,
        risk_level: str,
        expiry_seconds: int,
    ) -> ApprovalRequest:
        nonce = new_nonce()
        expires_at = expiry_from_now(expiry_seconds)
        with self._db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO task_approvals
                        (task_id, tool_name, arguments_metadata, risk_level,
                         nonce, expires_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING created_at
                    """,
                    (
                        task_id,
                        tool_name,
                        json.dumps(arguments_metadata),
                        risk_level,
                        nonce,
                        expires_at,
                    ),
                )
                created_at = cur.fetchone()[0]
        return ApprovalRequest(
            task_id=task_id,
            tool_name=tool_name,
            arguments_metadata=arguments_metadata,
            risk_level=risk_level,
            nonce=nonce,
            created_at=created_at,
            expires_at=expires_at,
        )

    def get_pending_approval(self, task_id: str) -> ApprovalRequest | None:
        with self._db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT task_id, tool_name, arguments_metadata, risk_level, "
                    "nonce, created_at, expires_at FROM task_approvals "
                    "WHERE task_id = %s AND status = 'pending' "
                    "ORDER BY created_at DESC LIMIT 1",
                    (task_id,),
                )
                row = cur.fetchone()
        if not row:
            return None
        args = json.loads(row[2]) if isinstance(row[2], str) else row[2]
        return ApprovalRequest(
            task_id=row[0],
            tool_name=row[1],
            arguments_metadata=args,
            risk_level=row[3],
            nonce=row[4],
            created_at=row[5],
            expires_at=row[6],
        )

    def decide_approval(self, decision: ApprovalDecision, expected_tool: str) -> ApprovalRequest:
        """Atomically decide a pending approval. Enforces single-use nonce,
        expiry, action match, and terminal-task rejection. Returns the
        approved request (with the exact tool/args) on success.

        Raises:
          ApprovalNotFoundError, ApprovalExpiredError,
          ApprovalAlreadyDecidedError, ApprovalActionMismatchError,
          InvalidTransition (if task is terminal).
        """
        with self._db.connect() as conn:
            with conn.cursor() as cur:
                # Lock the approval row.
                cur.execute(
                    "SELECT task_id, tool_name, arguments_metadata, risk_level, "
                    "nonce, created_at, expires_at, status FROM task_approvals "
                    "WHERE nonce = %s FOR UPDATE",
                    (decision.nonce,),
                )
                row = cur.fetchone()
                if row is None:
                    raise ApprovalNotFoundError("no approval for nonce")
                (
                    t_id,
                    tool_name,
                    args_raw,
                    risk_level,
                    nonce,
                    created_at,
                    expires_at,
                    ap_status,
                ) = row
                if ap_status != "pending":
                    raise ApprovalAlreadyDecidedError(
                        f"approval already {ap_status} (nonce not reusable)"
                    )
                if utcnow() >= expires_at:
                    cur.execute(
                        "UPDATE task_approvals SET status = 'expired', "
                        "decided_at = now() WHERE nonce = %s",
                        (decision.nonce,),
                    )
                    raise ApprovalExpiredError("approval expired")

                # The approval must reference the exact pending action.
                if tool_name != expected_tool or t_id != decision.task_id:
                    raise ApprovalActionMismatchError(
                        "approval does not match the requested action"
                    )

                # Reject approvals for terminal tasks.
                cur.execute("SELECT status FROM tasks WHERE id = %s FOR UPDATE", (t_id,))
                t_row = cur.fetchone()
                if t_row is None:
                    raise ApprovalNotFoundError("task not found")
                if is_terminal(TaskStatus(t_row[0])):
                    raise InvalidTransition("cannot approve an action for a terminal task")

                # Single-use: mark consumed/approved/rejected atomically.
                new_status = "approved" if decision.approved else "rejected"
                cur.execute(
                    "UPDATE task_approvals SET status = %s, decided_at = now(), "
                    "decided_by = %s WHERE nonce = %s",
                    (new_status, decision.decided_by, decision.nonce),
                )
                args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
        return ApprovalRequest(
            task_id=t_id,
            tool_name=tool_name,
            arguments_metadata=args,
            risk_level=risk_level,
            nonce=nonce,
            created_at=created_at,
            expires_at=expires_at,
        )
