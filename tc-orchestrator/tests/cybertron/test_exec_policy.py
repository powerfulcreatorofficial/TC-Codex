"""Codex-style exec policy: known-safe classification + approval decisions."""

from __future__ import annotations

from tc_orchestrator.cybertron.exec_policy import (
    ApprovalPolicy,
    SandboxMode,
    assess_command,
    decide_exec,
)


def test_known_safe_commands():
    for argv in (
        ["ls", "-la"],
        ["cat", "src/app.py"],
        ["grep", "-rn", "def add", "src"],
        ["rg", "pattern"],
        ["git", "status"],
        ["git", "diff", "--stat"],
        ["git", "log", "--oneline"],
        ["sed", "-n", "1,10p", "file.py"],
        ["find", ".", "-name", "*.py"],
    ):
        assert assess_command(argv).known_safe, argv


def test_unsafe_commands():
    for argv in (
        ["rm", "-rf", "/"],
        ["git", "push"],
        ["git", "commit", "-m", "x"],
        ["curl", "http://evil"],
        ["python", "-c", "x"],
        ["pytest", "-q"],
        ["find", ".", "-delete"],
        ["find", ".", "-exec", "rm", "{}", ";"],
        ["sed", "-i", "s/a/b/", "f"],
        ["echo", "x", ">", "file"],
        [],
    ):
        assert not assess_command(argv).known_safe, argv


def test_bash_lc_pipeline_safe():
    assert assess_command(["bash", "-lc", "ls && git status | head -5"]).known_safe
    assert assess_command(["sh", "-c", "cat a.py ; grep foo b.py"]).known_safe


def test_bash_lc_unsafe():
    for script in (
        "ls > /tmp/out",            # redirection
        "ls && rm -rf x",           # unsafe stage
        "echo $(cat /etc/passwd)",  # substitution
        "git status && git push",   # mutating git
        "cat `whoami`",             # backticks
    ):
        assert not assess_command(["bash", "-lc", script]).known_safe, script


def test_untrusted_policy_gates_unsafe_only():
    safe = decide_exec(["ls"], approval_policy=ApprovalPolicy.UNTRUSTED,
                       sandbox_mode=SandboxMode.WORKSPACE_WRITE)
    assert safe.allow and not safe.needs_approval
    unsafe = decide_exec(["pytest", "-q"], approval_policy=ApprovalPolicy.UNTRUSTED,
                         sandbox_mode=SandboxMode.WORKSPACE_WRITE)
    assert unsafe.allow and unsafe.needs_approval


def test_on_request_auto_runs_until_escalation():
    auto = decide_exec(["pytest", "-q"], approval_policy=ApprovalPolicy.ON_REQUEST,
                       sandbox_mode=SandboxMode.WORKSPACE_WRITE)
    assert auto.allow and not auto.needs_approval
    escalated = decide_exec(["pytest", "-q"], approval_policy=ApprovalPolicy.ON_REQUEST,
                            sandbox_mode=SandboxMode.WORKSPACE_WRITE,
                            escalation_requested=True)
    assert escalated.needs_approval


def test_never_policy_never_prompts():
    d = decide_exec(["pytest", "-q"], approval_policy=ApprovalPolicy.NEVER,
                    sandbox_mode=SandboxMode.WORKSPACE_WRITE)
    assert d.allow and not d.needs_approval


def test_read_only_sandbox_gates_non_readonly_regardless_of_policy():
    for policy in ApprovalPolicy:
        d = decide_exec(["pytest", "-q"], approval_policy=policy,
                        sandbox_mode=SandboxMode.READ_ONLY)
        assert d.needs_approval, policy
        safe = decide_exec(["git", "diff"], approval_policy=policy,
                           sandbox_mode=SandboxMode.READ_ONLY)
        # Known-safe read-only commands run without prompting in read-only
        # mode under never/on-request.
        if policy != ApprovalPolicy.UNTRUSTED:
            assert not safe.needs_approval, policy


def test_no_danger_full_access_mode_exists():
    assert "danger-full-access" not in [m.value for m in SandboxMode]
