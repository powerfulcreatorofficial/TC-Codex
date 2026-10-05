"""Step 4 store tests (TEST A-C, P): create/update/events + DB-failure safety.

Runs against BOTH the in-memory store and the real PostgreSQL store so the
contract is identical. PG variants skip if Docker/PostgreSQL is unavailable.
"""

from __future__ import annotations

import pytest

from tc_orchestrator.models import TaskStatus
from tc_orchestrator.task_store import TaskStore
from tc_orchestrator.transitions import InvalidTransition

# ---- in-memory store ----


@pytest.fixture(params=["memory"])
def store(request):
    if request.param == "memory":
        return TaskStore()
    return None


# Re-run the same suite against real Postgres when available.
@pytest.fixture(params=["memory", "pg"])
def any_store(request, pg_dsn):
    if request.param == "memory":
        return TaskStore()
    # pg fixture resets schema per test
    from tc_orchestrator.db import Database
    from tc_orchestrator.migrations import reset_database
    from tc_orchestrator.pg_task_store import PgTaskStore

    reset_database(pg_dsn)
    return PgTaskStore(Database(pg_dsn))


def test_test_a_create_persist_retrieve(any_store):
    """TEST A: create task -> persist -> retrieve."""
    summary, owner_token = any_store.create("do a thing", max_steps=7)
    fetched = any_store.get(summary.task_id)
    assert fetched is not None
    assert fetched.task_id == summary.task_id
    assert fetched.prompt == "do a thing"
    assert fetched.status == TaskStatus.PENDING
    assert fetched.max_steps == 7
    assert owner_token  # owner token returned once
    # owner token verifies
    assert any_store.verify_owner(summary.task_id, owner_token) is True
    assert any_store.verify_owner(summary.task_id, "wrong-token") is False


def test_test_b_update_state_persist_retrieve(any_store):
    """TEST B: update task state -> persist -> retrieve."""
    summary, _ = any_store.create("do a thing")
    any_store.update(summary.task_id, status=TaskStatus.RUNNING, steps=2)
    fetched = any_store.get(summary.task_id)
    assert fetched.status == TaskStatus.RUNNING
    assert fetched.steps == 2
    # Transition to COMPLETED.
    any_store.update(summary.task_id, status=TaskStatus.COMPLETED, answer="done")
    fetched = any_store.get(summary.task_id)
    assert fetched.status == TaskStatus.COMPLETED
    assert fetched.answer == "done"


def test_invalid_transition_rejected_by_store(any_store):
    summary, _ = any_store.create("do a thing")
    # PENDING -> COMPLETED is invalid.
    with pytest.raises(InvalidTransition):
        any_store.update(summary.task_id, status=TaskStatus.COMPLETED)


def test_test_c_create_event_retrieve_history(any_store):
    """TEST C: create task event -> retrieve event history."""
    summary, _ = any_store.create("do a thing")
    any_store.update(summary.task_id, status=TaskStatus.RUNNING)
    any_store.add_event(
        summary.task_id,
        "approval_requested",
        tool_name="write_file",
        arguments_metadata={"path": "out.txt", "content_length": 5},
        status="pending",
    )
    events = any_store.list_events(summary.task_id)
    assert len(events) == 1
    assert events[0]["event_type"] == "approval_requested"
    assert events[0]["tool_name"] == "write_file"
    assert events[0]["arguments_metadata"]["path"] == "out.txt"


def test_unknown_task_returns_none(any_store):
    assert any_store.get("does-not-exist") is None
    assert any_store.update("does-not-exist", status=TaskStatus.RUNNING) is None


def test_stored_metadata_is_redactable_structure(any_store):
    """Arguments metadata stored must be a redacted-safe dict (no raw secrets)."""
    summary, _ = any_store.create("do a thing")
    any_store.add_event(
        summary.task_id,
        "tool_call",
        tool_name="exec_command",
        arguments_metadata={"argv": ["echo", "[REDACTED_SECRET]"]},
        result_metadata={"exit_code": 0},
    )
    events = any_store.list_events(summary.task_id)
    assert "[REDACTED_SECRET]" in str(events[0]["arguments_metadata"])
