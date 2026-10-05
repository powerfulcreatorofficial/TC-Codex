"""TEST C/D/E/H — Orchestrator loop with a mocked Brain.

These tests use the FakeWorkspaceClient (no gRPC daemon required).
"""

from __future__ import annotations

from tc_orchestrator.brain import MockBrain, RepeatingToolBrain
from tc_orchestrator.orchestrator import Orchestrator, OrchestratorConfig
from tc_orchestrator.redaction import Redactor
from tc_orchestrator.tool_registry import default_registry


def make_orchestrator(brain, client, *, max_steps=20, redactor=None):
    return Orchestrator(
        brain=brain,
        client=client,
        registry=default_registry(),
        redactor=redactor or Redactor(),
        config=OrchestratorConfig(max_steps=max_steps),
    )


def _tc(name, **arguments):
    return [{"id": "call_1", "name": name, "arguments": arguments}]


def test_test_c_single_tool_then_final(fake_client_with_files):
    """TEST C: read_file -> result -> final answer."""
    brain = MockBrain(
        script=[
            (_tc("read_file", path="README.md"), None, "tool_calls"),
            (None, "The repo is an engineering test platform.", "stop"),
        ]
    )
    orch = make_orchestrator(brain, fake_client_with_files)
    result = orch.run("Read README.md and tell me what this repo does.")
    assert result.finished is True
    assert result.steps == 2
    assert "engineering test platform" in (result.answer or "").lower()
    assert len(result.tool_results) == 1
    assert result.tool_results[0].name == "read_file"
    assert result.tool_results[0].ok is True


def test_test_d_two_tools_then_final(fake_client_with_files):
    """TEST D: read_file -> exec_command -> final answer."""
    brain = MockBrain(
        script=[
            (_tc("read_file", path="README.md"), None, "tool_calls"),
            (_tc("exec_command", argv=["uname", "-s"], timeout_seconds=5), None, "tool_calls"),
            (None, "Done after reading and running a command.", "stop"),
        ]
    )
    orch = make_orchestrator(brain, fake_client_with_files)
    result = orch.run("Read README then run uname -s.")
    assert result.finished is True
    assert result.steps == 3
    assert len(result.tool_results) == 2
    # Confirm the exec call was actually dispatched to the fake client.
    assert fake_client_with_files.exec_calls[-1] == (["uname", "-s"], 5)


def test_test_e_unknown_tool_rejected_then_final(fake_client_with_files):
    """TEST E: Brain requests delete_everything() -> rejected -> final."""
    brain = MockBrain(
        script=[
            (
                _tc(
                    "delete_everything",
                ),
                None,
                "tool_calls",
            ),
            (None, "I could not delete anything; finishing.", "stop"),
        ]
    )
    orch = make_orchestrator(brain, fake_client_with_files)
    result = orch.run("Delete everything.")
    assert result.finished is True
    # The unknown tool must have produced a failing tool result fed back.
    assert len(result.tool_results) == 1
    res = result.tool_results[0]
    assert res.name == "delete_everything"
    assert res.ok is False
    assert "unknown" in (res.error or "").lower()


def test_test_h_max_loop_terminates(fake_client_with_files):
    """TEST H: Brain repeats the same tool forever -> orchestrator stops."""
    brain = RepeatingToolBrain("read_file", {"path": "README.md"})
    orch = make_orchestrator(brain, fake_client_with_files, max_steps=5)
    result = orch.run("Loop forever.")
    assert result.finished is False
    # Either hit MAX_AGENT_STEPS or the repeated-call abort.
    assert result.error is not None
    assert "MAX_AGENT_STEPS" in result.error or "repeated" in result.error.lower()


def test_test_g_traversal_via_loop(fake_client_with_files):
    """TEST G through the loop: traversal is rejected, Brain told of failure."""
    brain = MockBrain(
        script=[
            (_tc("read_file", path="../../etc/passwd"), None, "tool_calls"),
            (None, "Traversal was blocked; finishing.", "stop"),
        ]
    )
    orch = make_orchestrator(brain, fake_client_with_files)
    result = orch.run("Try to read ../../etc/passwd.")
    assert result.finished is True
    assert len(result.tool_results) == 1
    assert result.tool_results[0].ok is False
    assert "../../etc/passwd" not in fake_client_with_files.files


def test_secret_never_reaches_brain(fake_client_with_files, redactor_secrets):
    """TEST F: secrets in tool output must be redacted in Brain-facing text."""
    fake_client_with_files.exec_side_effect = [
        # stdout contains a fake openrouter key
        type(
            "E",
            (),
            {
                "exit_code": 0,
                "status": "completed",
                "stdout": f"leaked {redactor_secrets['openrouter']}".encode(),
                "stderr": b"",
                "duration_ms": 1,
                "stdout_text": f"leaked {redactor_secrets['openrouter']}",
                "stderr_text": "",
            },
        )()
    ]
    brain = MockBrain(
        script=[
            (_tc("exec_command", argv=["env"], timeout_seconds=5), None, "tool_calls"),
            (None, "done", "stop"),
        ]
    )
    # Seed the redactor with the fake secret so it is scrubbed as a literal too.
    redactor = Redactor(extra_secrets=list(redactor_secrets.values()))
    orch = make_orchestrator(brain, fake_client_with_files, redactor=redactor)
    result = orch.run("Print env.")
    assert result.finished is True
    # The Brain-facing transcript (messages) must never contain the raw secret.
    for msg in result.messages:
        if msg.content:
            assert redactor_secrets["openrouter"] not in msg.content, "secret leaked to Brain"
    # The tool result message sent to the Brain must contain the redaction sentinel.
    tool_msg_contents = [
        m.content for m in result.messages if m.role == "tool" and m.name == "exec_command"
    ]
    assert tool_msg_contents, "no exec_command tool message reached the Brain"
    brain_facing = " ".join(tool_msg_contents)
    assert redactor_secrets["openrouter"] not in brain_facing, "raw secret in Brain-facing text"
    assert "[REDACTED_SECRET]" in brain_facing


def test_loop_passes_tools_to_brain(fake_client_with_files):
    """The orchestrator must offer the registered tools to the Brain each turn."""
    brain = MockBrain(script=[(None, "final", "stop")])
    orch = make_orchestrator(brain, fake_client_with_files)
    orch.run("do something")
    assert brain.calls, "Brain was never called"
    offered = brain.calls[0]["tools_offered"]
    assert set(["read_file", "write_file", "exec_command", "git_status"]).issubset(set(offered))
