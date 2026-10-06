"""End-to-end agentic mode: the Codex-style loop under Cybertron's gates."""

from __future__ import annotations

from tc_orchestrator.cybertron import (
    AgentLoopConfig,
    ApprovalPolicy,
    Cybertron,
    EngineConfig,
    FinalStatus,
    SandboxMode,
    Stage,
    TaskBudget,
)
from tc_orchestrator.cybertron.agent_loop import ModelToolCall, ModelTurn


class ScriptedToolBrain:
    def __init__(self, turns):
        self.queue = list(turns)
        self.calls = 0

    def turn(self, messages, tools):
        self.calls += 1
        self.last_messages = messages
        if not self.queue:
            return ModelTurn(content="nothing left to do", tool_calls=[])
        return self.queue.pop(0)


def call(name, i, **args):
    return ModelToolCall(id=f"c{i}", name=name, arguments=args)


GOOD_PATCH = (
    "*** Begin Patch\n"
    "*** Update File: src/app.py\n"
    "@@ def add(a, b):\n"
    "-    return a + b\n"
    "+    return a + b\n"
    "+\n"
    "+\n"
    "+def sub(a, b):\n"
    "+    return a - b\n"
    "*** End Patch\n"
)

BAD_PATCH = (
    "*** Begin Patch\n"
    "*** Update File: src/app.py\n"
    "@@ def add(a, b):\n"
    "-    return a + b\n"
    "+    return a - b\n"
    "*** End Patch\n"
)

VERIFY = [["python3", "-m", "pytest", "-q", "tests"]]

AUTON = EngineConfig(
    require_approval=False,
    loop=AgentLoopConfig(
        approval_policy=ApprovalPolicy.NEVER,
        sandbox_mode=SandboxMode.WORKSPACE_WRITE,
    ),
)


def test_agentic_success_path(git_ws):
    brain = ScriptedToolBrain([
        ModelTurn(content=None, tool_calls=[call(
            "update_plan", 0,
            plan=[{"step": "add sub()", "status": "in_progress"}],
        )]),
        ModelTurn(content=None, tool_calls=[call("apply_patch", 1, patch=GOOD_PATCH)]),
        ModelTurn(content="added sub(); tests should pass", tool_calls=[]),
    ])
    cy = Cybertron(
        config=AUTON, tool_brain=brain,
        budget_factory=lambda: TaskBudget(max_wall_seconds=300),
    )
    report = cy.execute("add a sub() function", str(git_ws),
                        verification_commands=VERIFY)
    assert report.status == FinalStatus.SUCCESS
    assert report.verification is not None and report.verification.passed
    assert report.review is not None and report.review.approved
    assert "src/app.py" in report.changed_files
    assert Stage.ACT in report.stages_completed
    assert Stage.VERIFY in report.stages_completed
    # Live plan surfaced through events.
    assert any(e.event_type == "plan_updated" for e in report.events)


def test_agentic_verification_failure_then_repair(git_ws):
    brain = ScriptedToolBrain([
        # Attempt 1: break the code, claim done.
        ModelTurn(content=None, tool_calls=[call("apply_patch", 0, patch=BAD_PATCH)]),
        ModelTurn(content="done (it is not)", tool_calls=[]),
        # Repair turn: engine feeds failure evidence; model fixes it.
        ModelTurn(content=None, tool_calls=[call("apply_patch", 1, patch=(
            "*** Begin Patch\n"
            "*** Update File: src/app.py\n"
            "@@ def add(a, b):\n"
            "-    return a - b\n"
            "+    return a + b\n"
            "*** End Patch\n"
        ))]),
        ModelTurn(content="fixed the sign error", tool_calls=[]),
    ])
    cy = Cybertron(
        config=AUTON, tool_brain=brain,
        budget_factory=lambda: TaskBudget(max_repair_attempts=2, max_wall_seconds=300),
    )
    report = cy.execute("improve add()", str(git_ws), verification_commands=VERIFY)
    assert report.status == FinalStatus.SUCCESS
    assert report.usage["repair_attempts_used"] == 1
    assert Stage.REPAIR in report.stages_completed
    # The repair instruction contained real failure evidence.
    repair_msg = next(
        m for m in brain.last_messages
        if m.get("role") == "user" and "verification FAILED" in str(m.get("content"))
    )
    assert "pytest" in repair_msg["content"]


def test_agentic_model_claim_never_beats_verification(git_ws):
    brain = ScriptedToolBrain([
        ModelTurn(content=None, tool_calls=[call("apply_patch", 0, patch=BAD_PATCH)]),
        ModelTurn(content="SUCCESS! Everything works perfectly!", tool_calls=[]),
        # Repair attempts that keep claiming success without fixing anything.
        ModelTurn(content="definitely fixed now", tool_calls=[]),
    ])
    cy = Cybertron(
        config=AUTON, tool_brain=brain,
        budget_factory=lambda: TaskBudget(max_repair_attempts=1, max_wall_seconds=300),
    )
    report = cy.execute("improve add()", str(git_ws), verification_commands=VERIFY)
    assert report.status == FinalStatus.FAILED
    assert not report.verification.passed


def test_agentic_session_approval_denied_blocks(git_ws):
    brain = ScriptedToolBrain([])
    cy = Cybertron(
        config=EngineConfig(require_approval=True, loop=AgentLoopConfig(
            approval_policy=ApprovalPolicy.ON_REQUEST,
            sandbox_mode=SandboxMode.WORKSPACE_WRITE,
        )),
        tool_brain=brain,
        approval_gate=lambda stage, desc, detail: False,
        budget_factory=lambda: TaskBudget(max_wall_seconds=300),
    )
    report = cy.execute("x", str(git_ws), verification_commands=VERIFY)
    assert report.status == FinalStatus.BLOCKED
    assert brain.calls == 0  # nothing ran without session approval
    assert report.changed_files == []


def test_agentic_agents_md_guidance_in_system_prompt(git_ws):
    (git_ws / "AGENTS.md").write_text("# Conventions\nAlways run ruff before tests.\n")
    brain = ScriptedToolBrain([
        ModelTurn(content="noted", tool_calls=[]),
    ])
    cy = Cybertron(
        config=AUTON, tool_brain=brain,
        budget_factory=lambda: TaskBudget(max_repair_attempts=0, max_wall_seconds=300),
    )
    report = cy.execute("x", str(git_ws), verification_commands=[["true"]])
    system = brain.last_messages[0]
    assert system["role"] == "system"
    assert "Always run ruff before tests." in system["content"]
    assert "NEVER override safety policy" in system["content"]
    assert any(e.event_type == "project_docs_loaded" for e in report.events)


def test_agentic_budget_exhaustion_blocks(git_ws):
    brain = ScriptedToolBrain([
        ModelTurn(content=None, tool_calls=[call("shell", 0, command=["ls"])]),
    ])
    cy = Cybertron(
        config=AUTON, tool_brain=brain,
        budget_factory=lambda: TaskBudget(max_model_calls=1),
    )
    report = cy.execute("x", str(git_ws), verification_commands=VERIFY)
    assert report.status == FinalStatus.BLOCKED
    assert "budget" in report.summary
