"""Git safety: hooks disabled, malicious config neutralized, safe arguments."""

from __future__ import annotations

import subprocess

import pytest

from tc_orchestrator.cybertron.gitsafe import GitSafetyError


def test_state_reads_repo(safegit):
    st = safegit.state()
    assert st.is_repo
    assert st.branch == "main"
    assert st.clean


def test_malicious_hook_not_executed(safegit, git_ws):
    hook_dir = git_ws / ".git" / "hooks"
    marker = git_ws / "HOOK_RAN"
    hook = hook_dir / "pre-commit"
    hook.write_text(f"#!/bin/sh\ntouch {marker}\n")
    hook.chmod(0o755)
    (git_ws / "newfile.txt").write_text("x\n")
    res = safegit.commit("add newfile", ["newfile.txt"])
    assert res.ok, res.stderr
    assert not marker.exists(), "repository hook executed despite hardening"


def test_malicious_core_config_neutralized(safegit, git_ws):
    marker = git_ws / "FSMONITOR_RAN"
    # Attacker-controlled repo config tries to run a command via fsmonitor/pager.
    subprocess.run(
        ["git", "config", "core.fsmonitor", f"touch {marker}"],
        cwd=git_ws, check=True, capture_output=True,
        env={"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": str(git_ws),
             "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"},
    )
    st = safegit.state()
    assert st.is_repo
    assert not marker.exists(), "core.fsmonitor from repo config was executed"


def test_unsafe_paths_rejected(safegit):
    with pytest.raises(GitSafetyError):
        safegit.add(["--force"])
    with pytest.raises(GitSafetyError):
        safegit.add(["-rf"])
    with pytest.raises(GitSafetyError):
        safegit.add(["/etc/passwd"])
    with pytest.raises(GitSafetyError):
        safegit.add(["../outside"])
    with pytest.raises(GitSafetyError):
        safegit.commit("msg", ["../x"])


def test_unsafe_refs_rejected(safegit):
    for bad in ("-evil", "a..b", "x.lock", "has space"):
        with pytest.raises(GitSafetyError):
            safegit.create_branch(bad)


def test_add_all_not_allowed(safegit):
    with pytest.raises(GitSafetyError):
        safegit.add([])


def test_commit_requires_explicit_paths_and_works(safegit, git_ws):
    (git_ws / "a.txt").write_text("a\n")
    res = safegit.commit("add a", ["a.txt"])
    assert res.ok
    assert "add a" in safegit.log()
