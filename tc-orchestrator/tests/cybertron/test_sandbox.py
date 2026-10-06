"""Sandbox: truthful exit codes, timeouts, process-tree kill, env scrubbing."""

from __future__ import annotations

import os
import time

from tc_orchestrator.cybertron.sandbox import SandboxLimits


def test_truthful_exit_codes(sandbox):
    ok = sandbox.run(["true"])
    assert ok.status == "completed" and ok.exit_code == 0 and ok.ok
    bad = sandbox.run(["false"])
    assert bad.status == "completed" and bad.exit_code == 1
    assert not bad.ok  # a failing command is NEVER ok
    assert bad.error is not None


def test_failing_test_command_stays_failed(sandbox):
    res = sandbox.run(["python3", "-c", "import sys; print('1 failed'); sys.exit(1)"])
    assert res.exit_code == 1
    assert not res.ok


def test_missing_executable_is_error(sandbox):
    res = sandbox.run(["definitely-not-a-real-binary-xyz"])
    # Without the unshare wrapper the spawn fails (status="error"); with it,
    # the wrapper reports exit code 127. Both are truthful failures.
    assert not res.ok
    assert res.status == "error" or res.exit_code == 127


def test_timeout_kills_process_tree(sandbox):
    # Parent spawns a child that would outlive it; both must die.
    marker = sandbox.root / "child_alive.txt"
    script = (
        "import subprocess, time\n"
        f"subprocess.Popen(['/bin/sh', '-c',\n"
        f"    'while true; do echo tick >> {marker}; sleep 0.2; done'])\n"
        "time.sleep(60)\n"
    )
    start = time.monotonic()
    res = sandbox.run(
        ["python3", "-c", script],
        limits=SandboxLimits(timeout_seconds=1.5),
    )
    assert res.status == "timeout"
    assert not res.ok
    assert time.monotonic() - start < 15
    # After the kill, the grandchild must stop writing.
    time.sleep(1.0)
    size_a = marker.stat().st_size if marker.exists() else 0
    time.sleep(1.0)
    size_b = marker.stat().st_size if marker.exists() else 0
    assert size_a == size_b, "grandchild survived the process-group kill"


def test_output_capped(sandbox):
    res = sandbox.run(
        ["python3", "-c", "print('x' * 100000)"],
        limits=SandboxLimits(max_output_bytes=1000),
    )
    assert res.stdout_truncated
    assert len(res.stdout) <= 1100


def test_env_is_scrubbed(sandbox):
    os.environ["TC_TEST_FAKE_SECRET"] = "sk-secret-value-123"
    try:
        res = sandbox.run(["python3", "-c", "import os; print(sorted(os.environ))"])
        assert res.ok
        assert "TC_TEST_FAKE_SECRET" not in res.stdout
        assert "sk-secret-value-123" not in res.stdout
    finally:
        del os.environ["TC_TEST_FAKE_SECRET"]


def test_home_is_not_real_home(sandbox):
    res = sandbox.run(["python3", "-c", "import os; print(os.environ['HOME'])"])
    assert res.ok
    reported = res.stdout.strip()
    assert reported != os.path.expanduser("~")
    assert str(sandbox.root) in reported  # throwaway HOME inside the workspace


def test_cwd_escape_rejected(sandbox):
    res = sandbox.run(["true"], cwd="../..")
    assert res.status == "error"
    assert "escapes" in (res.error or "")


def test_isolation_report_is_honest(sandbox):
    res = sandbox.run(["true"])
    iso = res.isolation
    assert iso["filesystem_namespaced"] is False  # never overclaimed
    assert iso["env_scrubbed"] is True
    assert isinstance(iso["network_isolated"], bool)
