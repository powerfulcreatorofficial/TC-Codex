"""Codex-style agent loop: iterative tool calling under Cybertron's gates."""

from __future__ import annotations

import json

from tc_orchestrator.cybertron.agent_loop import (
    AgentLoop,
    AgentLoopConfig,
    ModelToolCall,
    ModelTurn,
)
from tc_orchestrator.cybertron.budget import BudgetExceeded, TaskBudget
from tc_orchestrator.cybertron.exec_policy import ApprovalPolicy, SandboxMode
from tc_orchestrator.cybertron.gitsafe import SafeGit
from tc_orchestrator.cybertron.repo_intel import RepoIntelligence
from tc_orchestrator.cybertron.sandbox import LocalProcessSandbox
from tc_orchestrator.cybertron.tools import CybertronToolset
from tc_orchestrator.cybertron.workspace import SafeWorkspace


class ScriptedToolBrain:
    """Returns queued turns; records the transcript it was shown."""

    def __init__(self, turns):
        self.queue = list(turns)
        self.seen_messages: list[list[dict]] = []

    def turn(self, messages, tools):
        self.seen_messages.append(messages)
        if not self.queue:
            return ModelTurn(content="done", tool_calls=[])
        return self.queue.pop(0)


def call(name, i=0, **args):
    return ModelToolCall(id=f"c{i}", name=name, arguments=args)


def make_loop(root, brain, *, policy=ApprovalPolicy.NEVER, gate=None,
              budget=None, sandbox_mode=SandboxMode.WORKSPACE_WRITE, config=None):
    ws = SafeWorkspace(root)
    sb = LocalProcessSandbox(root)
    git = SafeGit(sb)
    toolset = CybertronToolset(ws, sb, git, RepoIntelligence(ws, git))
    cfg = config or AgentLoopConfig(approval_policy=policy, sandbox_mode=sandbox_mode)
    return AgentLoop(
        brain, toolset, budget or TaskBudget(),
        system_prompt="system", config=cfg, gate=gate,
    )


V4A = (
    "*** Begin Patch\n"
    "*** Update File: src/app.py\n"
    "@@ def add(a, b):\n"
    "-    return a + b\n"
    "+    return a + b  # touched\n"
    "*** End Patch\n"
)


def test_full_iteration_read_patch_shell_final(ws_root):
    brain = ScriptedToolBrain([
        ModelTurn(content=None, tool_calls=[call("read_file", 0, path="src/app.py")]),
        ModelTurn(content=None, tool_calls=[call("apply_patch", 1, patch=V4A)]),
        ModelTurn(content=None, tool_calls=[call("shell", 2, command=["true"])]),
        ModelTurn(content="I changed src/app.py and ran a check.", tool_calls=[]),
    ])
    loop = make_loop(ws_root, brain)
    result = loop.run("do the thing")
    assert result.finished
    assert result.final_message.startswith("I changed")
    assert result.model_turns == 4
    assert result.tool_calls == 3
    assert "# touched" in SafeWorkspace(ws_root).read_file("src/app.py").text
    # The model saw real structured tool results, including file content.
    tool_msgs = [m for m in brain.seen_messages[-1] if m.get("role") == "tool"]
    assert any("def add" in m["content"] for m in tool_msgs)


def test_failing_shell_reported_truthfully(ws_root):
    brain = ScriptedToolBrain([
        ModelTurn(content=None, tool_calls=[call("shell", 0, command=["false"])]),
        ModelTurn(content="the command failed", tool_calls=[]),
    ])
    loop = make_loop(ws_root, brain)
    loop.run("x")
    tool_msg = [m for m in brain.seen_messages[-1] if m.get("role") == "tool"][-1]
    payload = json.loads(tool_msg["content"])
    assert payload["ok"] is False
    assert payload["exit_code"] == 1


def test_untrusted_policy_denies_without_gate(ws_root):
    brain = ScriptedToolBrain([
        ModelTurn(content=None, tool_calls=[call("shell", 0, command=["python3", "-c", "1"])]),
        ModelTurn(content="ok", tool_calls=[]),
    ])
    loop = make_loop(ws_root, brain, policy=ApprovalPolicy.UNTRUSTED, gate=None)
    result = loop.run("x")
    assert result.denials == 1
    tool_msg = [m for m in brain.seen_messages[-1] if m.get("role") == "tool"][-1]
    payload = json.loads(tool_msg["content"])
    assert payload["approval"] == "denied"


def test_known_safe_runs_without_gate_in_untrusted(ws_root):
    brain = ScriptedToolBrain([
        ModelTurn(content=None, tool_calls=[call("shell", 0, command=["ls"])]),
        ModelTurn(content="ok", tool_calls=[]),
    ])
    loop = make_loop(ws_root, brain, policy=ApprovalPolicy.UNTRUSTED, gate=None)
    result = loop.run("x")
    assert result.denials == 0


def test_escalation_routes_to_gate_with_justification(ws_root):
    seen = []

    def gate(stage, desc, detail):
        seen.append(detail)
        return True

    brain = ScriptedToolBrain([
        ModelTurn(content=None, tool_calls=[call(
            "shell", 0, command=["python3", "-c", "print(1)"],
            with_escalated_permissions=True,
            justification="need to run a python check",
        )]),
        ModelTurn(content="ok", tool_calls=[]),
    ])
    loop = make_loop(ws_root, brain, policy=ApprovalPolicy.ON_REQUEST, gate=gate)
    result = loop.run("x")
    assert result.denials == 0
    assert seen and seen[0]["justification"] == "need to run a python check"
    assert seen[0]["command"] == ["python3", "-c", "print(1)"]


def test_patch_gated_in_untrusted_mode(ws_root):
    decisions = []

    def gate(stage, desc, detail):
        decisions.append(detail)
        return False  # deny

    brain = ScriptedToolBrain([
        ModelTurn(content=None, tool_calls=[call("apply_patch", 0, patch=V4A)]),
        ModelTurn(content="denied", tool_calls=[]),
    ])
    loop = make_loop(ws_root, brain, policy=ApprovalPolicy.UNTRUSTED, gate=gate)
    result = loop.run("x")
    assert result.denials == 1
    # Denied => file untouched.
    assert "# touched" not in SafeWorkspace(ws_root).read_file("src/app.py").text


def test_update_plan_tracked_and_validated(ws_root):
    brain = ScriptedToolBrain([
        ModelTurn(content=None, tool_calls=[call(
            "update_plan", 0,
            plan=[{"step": "inspect", "status": "completed"},
                  {"step": "edit", "status": "in_progress"},
                  {"step": "test", "status": "pending"}],
            explanation="standard flow",
        )]),
        ModelTurn(content=None, tool_calls=[call(
            "update_plan", 1,
            plan=[{"step": "a", "status": "in_progress"},
                  {"step": "b", "status": "in_progress"}],
        )]),
        ModelTurn(content="done", tool_calls=[]),
    ])
    loop = make_loop(ws_root, brain)
    result = loop.run("x")
    # First update accepted; second rejected (two in_progress).
    assert result.live_plan.updates == 1
    assert [s.status for s in result.live_plan.steps] == [
        "completed", "in_progress", "pending"]
    tool_msgs = [m for m in brain.seen_messages[-1] if m.get("role") == "tool"]
    second = json.loads(tool_msgs[-1]["content"])
    assert second["ok"] is False and "in_progress" in second["error"]


def test_repeated_identical_call_aborts(ws_root):
    same = ModelTurn(content=None, tool_calls=[call("shell", 0, command=["ls"])])
    brain = ScriptedToolBrain([same, same, same, same, same])
    loop = make_loop(ws_root, brain)
    result = loop.run("x")
    assert not result.finished
    assert "repeated the identical tool call" in result.error


def test_model_call_budget_charged_before_call(ws_root):
    brain = ScriptedToolBrain([
        ModelTurn(content=None, tool_calls=[call("shell", 0, command=["ls"])]),
        ModelTurn(content="done", tool_calls=[]),
    ])
    budget = TaskBudget(max_model_calls=1)
    loop = make_loop(ws_root, brain, budget=budget)
    try:
        loop.run("x")
        raise AssertionError("expected BudgetExceeded")
    except BudgetExceeded:
        pass
    # Exactly one model call was made; the second was blocked BEFORE issue.
    assert len(brain.seen_messages) == 1


def test_transcript_compaction_elides_old_tool_output(ws_root):
    brain = ScriptedToolBrain([
        ModelTurn(content=None, tool_calls=[call("read_file", 0, path="src/app.py")]),
        ModelTurn(content=None, tool_calls=[call("read_file", 1, path="tests/test_app.py")]),
        ModelTurn(content=None, tool_calls=[call("read_file", 2, path="README.md")]),
        ModelTurn(content=None, tool_calls=[call("read_file", 3, path="pyproject.toml")]),
        ModelTurn(content=None, tool_calls=[call("list_dir", 4, path=".")]),
        ModelTurn(content=None, tool_calls=[call("grep", 5, pattern="def add", path="src")]),
        ModelTurn(content="done", tool_calls=[]),
    ])
    cfg = AgentLoopConfig(
        approval_policy=ApprovalPolicy.NEVER,
        sandbox_mode=SandboxMode.WORKSPACE_WRITE,
        transcript_char_budget=300,
    )
    loop = make_loop(ws_root, brain, config=cfg)
    result = loop.run("x")
    assert result.finished
    final_transcript = brain.seen_messages[-1]
    assert any(
        m.get("content") == "[output elided to fit context budget]"
        for m in final_transcript if m.get("role") == "tool"
    )
    # System prompt is never elided.
    assert final_transcript[0]["content"] == "system"
