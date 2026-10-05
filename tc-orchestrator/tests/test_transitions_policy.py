"""Step 4 unit tests: state transitions, approval policy, nonces.

These run without PostgreSQL or Docker.
"""

from __future__ import annotations

import time

import pytest

from tc_orchestrator.approval import (
    ApprovalRequest,
    expiry_from_now,
    hash_token,
    new_nonce,
    new_owner_token,
    utcnow,
)
from tc_orchestrator.models import TaskStatus
from tc_orchestrator.policy import ApprovalPolicy, needs_approval, risk_level
from tc_orchestrator.tool_registry import Permission
from tc_orchestrator.transitions import (
    InvalidTransition,
    allowed_transitions,
    is_terminal,
    validate_transition,
)

# ---- transitions ----


def test_allowed_transitions_match_spec():
    assert TaskStatus.RUNNING in allowed_transitions(TaskStatus.PENDING)
    assert TaskStatus.AWAITING_APPROVAL in allowed_transitions(TaskStatus.RUNNING)
    assert TaskStatus.COMPLETED in allowed_transitions(TaskStatus.RUNNING)
    assert TaskStatus.FAILED in allowed_transitions(TaskStatus.RUNNING)
    assert TaskStatus.RUNNING in allowed_transitions(TaskStatus.AWAITING_APPROVAL)
    assert TaskStatus.FAILED in allowed_transitions(TaskStatus.AWAITING_APPROVAL)


def test_invalid_transition_rejected():
    # PENDING -> COMPLETED is not allowed directly.
    with pytest.raises(InvalidTransition):
        validate_transition(TaskStatus.PENDING, TaskStatus.COMPLETED)
    with pytest.raises(InvalidTransition):
        validate_transition(TaskStatus.COMPLETED, TaskStatus.RUNNING)


def test_terminal_states_have_no_outgoing():
    assert is_terminal(TaskStatus.COMPLETED)
    assert is_terminal(TaskStatus.FAILED)
    assert not is_terminal(TaskStatus.RUNNING)
    assert allowed_transitions(TaskStatus.COMPLETED) == set()


def test_idempotent_same_status_allowed():
    validate_transition(TaskStatus.RUNNING, TaskStatus.RUNNING)


# ---- policy ----


def test_policy_l0_never_needs_approval():
    assert needs_approval(ApprovalPolicy(), Permission.L0) is False
    assert needs_approval(ApprovalPolicy.disabled(), Permission.L0) is False


def test_policy_l1_requires_approval_when_enabled():
    assert needs_approval(ApprovalPolicy(), Permission.L1) is True


def test_policy_l1_executes_when_disabled():
    assert needs_approval(ApprovalPolicy.disabled(), Permission.L1) is False


def test_policy_l2_always_requires_approval_when_enabled():
    assert needs_approval(ApprovalPolicy(), Permission.L2) is True


def test_risk_level_is_permission_value():
    assert risk_level(Permission.L1) == "L1"
    assert risk_level(Permission.L2) == "L2"


# ---- approval nonces / tokens ----


def test_nonces_are_unique():
    nonces = {new_nonce() for _ in range(50)}
    assert len(nonces) == 50


def test_owner_tokens_are_unique_and_hashed():
    t1, t2 = new_owner_token(), new_owner_token()
    assert t1 != t2
    # Stored hash never equals the raw token.
    assert hash_token(t1) != t1
    assert hash_token(t1) == hash_token(t1)
    assert hash_token(t1) != hash_token(t2)


def test_approval_request_expiry():
    req = ApprovalRequest(
        task_id="t",
        tool_name="write_file",
        arguments_metadata={"path": "a.txt"},
        risk_level="L1",
        nonce=new_nonce(),
        created_at=utcnow(),
        expires_at=expiry_from_now(1),
    )
    assert not req.is_expired()
    time.sleep(1.2)
    assert req.is_expired()


def test_approval_request_safe_view_has_no_raw_args_secrets():
    req = ApprovalRequest(
        task_id="t",
        tool_name="exec_command",
        arguments_metadata={"argv": ["echo", "x"]},
        risk_level="L1",
        nonce=new_nonce(),
        created_at=utcnow(),
        expires_at=expiry_from_now(60),
    )
    view = req.safe_view()
    assert "nonce" not in view
    assert view["tool_name"] == "exec_command"
    assert view["risk_level"] == "L1"
