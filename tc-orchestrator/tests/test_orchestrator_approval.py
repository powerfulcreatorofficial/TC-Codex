"""Step 4 orchestrator approval tests (TEST E, F, G, M, N, O).

Approval enabled. Uses the in-memory store + fake client (no daemon needed).
"""

from __future__ import annotations

from tc_orchestrator.brain import MockBrain
from tc_orchestrator.orchestrator import Orchestrator, OrchestratorConfig
from tc_orchestrator.policy import ApprovalPolicy
from tc_orchestrator.redaction import Redactor
from tc_orchestrator.task_store import TaskStore
from tc_orchestrator.tool_registry import default_registry


def _tc(name, **arguments):
    return [{"id": "call_1", "name": name, "arguments": arguments}]


def _orch(brain, client, store, *, redactor=None):
    return Orchestrator(
        brain=brain,
        client=client,
        registry=default_registry(),
        redactor=redactor or Redactor(),
        config=OrchestratorConfig(
            max_steps=5,
            approval_policy=ApprovalPolicy(),  # L1 requires approval
            approval_expiry_seconds=300,
        ),
    )


def test_test_e_read_file_no_approval(fake_client_with_files):
    """TEST E: read_file (L0) executes without approval."""
    brain = MockBrain(
        script=[
            (_tc("read_file", path="README.md"), None, "tool_calls"),
            (None, "done", "stop"),
        ]
    )
    store = TaskStore()
    orch = _orch(brain, fake_client_with_files, store)
    result = orch.run("read README")
    assert result.finished is True
    assert result.awaiting_approval is None
    assert result.tool_results[0].name == "read_file"
    assert result.tool_results[0].ok is True


def test_test_f_write_file_enters_awaiting(fake_client_with_files):
    """TEST F: write_file (L1) pauses for approval."""
    brain = MockBrain(
        script=[
            (_tc("write_file", path="out.txt", content="hi"), None, "tool_calls"),
        ]
    )
    store = TaskStore()
    orch = _orch(brain, fake_client_with_files, store)
    result = orch.run("write a file")
    assert result.finished is False
    assert result.awaiting_approval is not None
    assert result.awaiting_approval.tool_name == "write_file"
    assert result.awaiting_approval.risk_level == "L1"
    assert result.pending_arguments == {"path": "out.txt", "content": "hi"}
    # The file must NOT have been written (no approval yet).
    assert "out.txt" not in fake_client_with_files.files


def test_test_g_exec_command_enters_awaiting(fake_client_with_files):
    """TEST G: exec_command (L1) pauses for approval."""
    brain = MockBrain(
        script=[
            (_tc("exec_command", argv=["echo", "hi"], timeout_seconds=5), None, "tool_calls"),
        ]
    )
    store = TaskStore()
    orch = _orch(brain, fake_client_with_files, store)
    result = orch.run("run echo")
    assert result.finished is False
    assert result.awaiting_approval.tool_name == "exec_command"
    # exec must NOT have run.
    assert fake_client_with_files.exec_calls == []


def test_resume_after_approval_executes_exact_action(fake_client_with_files):
    """After approval, resume() executes the EXACT approved action."""
    brain = MockBrain(
        script=[
            (_tc("write_file", path="out.txt", content="hello"), None, "tool_calls"),
            (None, "wrote the file", "stop"),
        ]
    )
    store = TaskStore()
    orch = _orch(brain, fake_client_with_files, store)
    result = orch.run("write a file")
    assert result.awaiting_approval is not None
    # Resume with the exact approved action.
    resumed = orch.resume(
        result.messages,
        (result.awaiting_approval.tool_name, result.pending_arguments),
    )
    assert resumed.finished is True
    assert "out.txt" in fake_client_with_files.files
    assert fake_client_with_files.files["out.txt"] == b"hello"


def test_test_m_unknown_tool_rejected(fake_client_with_files):
    """TEST M: unknown tool is rejected (fail closed)."""
    brain = MockBrain(
        script=[
            (
                _tc(
                    "delete_everything",
                ),
                None,
                "tool_calls",
            ),
            (None, "could not delete", "stop"),
        ]
    )
    store = TaskStore()
    orch = _orch(brain, fake_client_with_files, store)
    result = orch.run("delete everything")
    # Unknown tool is not an approval pause; it produces a failing result.
    assert result.awaiting_approval is None
    assert result.tool_results[0].ok is False
    assert "unknown" in (result.tool_results[0].error or "").lower()


def test_test_n_traversal_rejected_with_approval_enabled(fake_client_with_files):
    """TEST N: workspace traversal remains rejected even with approval on."""
    brain = MockBrain(
        script=[
            (_tc("read_file", path="../../etc/passwd"), None, "tool_calls"),
            (None, "blocked", "stop"),
        ]
    )
    store = TaskStore()
    orch = _orch(brain, fake_client_with_files, store)
    result = orch.run("read passwd")
    assert result.tool_results[0].ok is False
    assert "../../etc/passwd" not in fake_client_with_files.files


def test_test_o_secrets_redacted_in_approval_summary(fake_client_with_files):
    """TEST O: the approval summary shown to the approver has no raw secrets."""
    secret = "sk-or-v1-TESTSECRET123"
    brain = MockBrain(
        script=[
            (
                _tc("exec_command", argv=["echo", secret], timeout_seconds=5),
                None,
                "tool_calls",
            ),
        ]
    )
    redactor = Redactor(extra_secrets=[secret])
    store = TaskStore()
    orch = _orch(brain, fake_client_with_files, store, redactor=redactor)
    result = orch.run("echo a secret")
    assert result.awaiting_approval is not None
    summary = result.awaiting_approval.arguments_metadata
    rendered = str(summary)
    assert secret not in rendered
    assert "[REDACTED_SECRET]" in rendered
