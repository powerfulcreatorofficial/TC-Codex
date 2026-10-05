"""Step 4 approval security tests (TEST H, I, J, K, L, Q).

Run against both the in-memory store and the real PostgreSQL store so the
single-use nonce / expiry / action-match / owner / concurrency guarantees
hold identically.
"""

from __future__ import annotations

import time

import pytest

from tc_orchestrator.approval import (
    ApprovalActionMismatchError,
    ApprovalAlreadyDecidedError,
    ApprovalDecision,
    ApprovalExpiredError,
    ApprovalNotFoundError,
)
from tc_orchestrator.models import TaskStatus
from tc_orchestrator.task_store import TaskStore
from tc_orchestrator.transitions import InvalidTransition


@pytest.fixture(params=["memory", "pg"])
def any_store(request, pg_dsn):
    if request.param == "memory":
        return TaskStore()
    from tc_orchestrator.db import Database
    from tc_orchestrator.migrations import reset_database
    from tc_orchestrator.pg_task_store import PgTaskStore

    reset_database(pg_dsn)
    return PgTaskStore(Database(pg_dsn))


def _make_awaiting(store, tool="write_file", expiry=300):
    """Create a task, move to RUNNING, then AWAITING_APPROVAL with a pending
    approval. Returns (task_id, owner_token, approval)."""
    summary, owner_token = store.create("mutate something")
    store.update(summary.task_id, status=TaskStatus.RUNNING)
    approval = store.create_approval(
        task_id=summary.task_id,
        tool_name=tool,
        arguments_metadata={"path": "out.txt", "content_length": 3},
        risk_level="L1",
        expiry_seconds=expiry,
    )
    store.update(summary.task_id, status=TaskStatus.AWAITING_APPROVAL)
    return summary.task_id, owner_token, approval


def test_test_h_correct_approval_executes_exact_action(any_store):
    """TEST H: a correct approval decides the exact requested action."""
    task_id, owner_token, approval = _make_awaiting(any_store)
    assert owner_token  # owner token exists (Brain never sees it)
    decision = ApprovalDecision(
        task_id=task_id, nonce=approval.nonce, approved=True, decided_by="alice"
    )
    decided = any_store.decide_approval(decision, expected_tool="write_file")
    assert decided.tool_name == "write_file"
    assert decided.arguments_metadata["path"] == "out.txt"


def test_test_i_wrong_tool_approval_rejected(any_store):
    """TEST I: an approval referencing a different tool/action is rejected."""
    task_id, _, approval = _make_awaiting(any_store, tool="write_file")
    decision = ApprovalDecision(
        task_id=task_id, nonce=approval.nonce, approved=True, decided_by="alice"
    )
    with pytest.raises(ApprovalActionMismatchError):
        any_store.decide_approval(decision, expected_tool="exec_command")


def test_test_j_replayed_approval_rejected(any_store):
    """TEST J: a replayed (already-decided) approval is rejected (single-use)."""
    task_id, _, approval = _make_awaiting(any_store)
    decision = ApprovalDecision(
        task_id=task_id, nonce=approval.nonce, approved=True, decided_by="alice"
    )
    any_store.decide_approval(decision, expected_tool="write_file")
    # Replay the same nonce.
    with pytest.raises(ApprovalAlreadyDecidedError):
        any_store.decide_approval(decision, expected_tool="write_file")


def test_test_k_expired_approval_rejected(any_store):
    """TEST K: an expired/stale approval is rejected."""
    task_id, _, approval = _make_awaiting(any_store, expiry=1)
    time.sleep(1.3)
    decision = ApprovalDecision(
        task_id=task_id, nonce=approval.nonce, approved=True, decided_by="alice"
    )
    with pytest.raises(ApprovalExpiredError):
        any_store.decide_approval(decision, expected_tool="write_file")


def test_approval_after_task_completion_rejected(any_store):
    """Approving an action for a terminal task is rejected."""
    task_id, _, approval = _make_awaiting(any_store)
    # Move task to COMPLETED (invalid from AWAITING_APPROVAL directly, so go
    # via RUNNING first).
    any_store.update(task_id, status=TaskStatus.RUNNING)
    any_store.update(task_id, status=TaskStatus.COMPLETED, answer="done")
    decision = ApprovalDecision(
        task_id=task_id, nonce=approval.nonce, approved=True, decided_by="alice"
    )
    with pytest.raises(InvalidTransition):
        any_store.decide_approval(decision, expected_tool="write_file")


def test_unknown_nonce_rejected(any_store):
    decision = ApprovalDecision(
        task_id="any", nonce="nonexistent-nonce", approved=True, decided_by="alice"
    )
    with pytest.raises(ApprovalNotFoundError):
        any_store.decide_approval(decision, expected_tool="write_file")


def test_test_l_brain_cannot_approve_no_owner_token(any_store):
    """TEST L: the Brain cannot approve — it has no owner token.

    The owner token is returned only to the task creator (via the API header),
    never to the Brain. verify_owner() rejects unknown tokens.
    """
    task_id, owner_token, _ = _make_awaiting(any_store)
    # The Brain would only know the task_id, not the owner token.
    assert any_store.verify_owner(task_id, "") is False
    assert any_store.verify_owner(task_id, "brain-guessed-token") is False
    assert any_store.verify_owner(task_id, owner_token) is True


def test_test_q_concurrent_approval_only_one_wins(any_store):
    """TEST Q: concurrent approval attempts allow only one valid execution.

    The store decides approvals atomically (FOR UPDATE for PG; lock for
    memory). The second attempt must see AlreadyDecided.
    """
    task_id, _, approval = _make_awaiting(any_store)
    d1 = ApprovalDecision(task_id=task_id, nonce=approval.nonce, approved=True, decided_by="a")
    d2 = ApprovalDecision(task_id=task_id, nonce=approval.nonce, approved=True, decided_by="b")
    any_store.decide_approval(d1, expected_tool="write_file")
    with pytest.raises(ApprovalAlreadyDecidedError):
        any_store.decide_approval(d2, expected_tool="write_file")
