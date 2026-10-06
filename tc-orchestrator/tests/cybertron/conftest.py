"""Fixtures for Cybertron tests: real temp workspaces, real subprocesses."""

from __future__ import annotations

import subprocess

import pytest

from tc_orchestrator.cybertron.gitsafe import SafeGit
from tc_orchestrator.cybertron.sandbox import LocalProcessSandbox
from tc_orchestrator.cybertron.workspace import SafeWorkspace


@pytest.fixture()
def ws_root(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("def add(a, b):\n    return a + b\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_app.py").write_text(
        "import sys, os\n"
        "sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))\n"
        "from app import add\n\n\n"
        "def test_add():\n    assert add(1, 2) == 3\n"
    )
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname = \"demo\"\nversion = \"0.1\"\n"
    )
    (tmp_path / "README.md").write_text("# Demo\n")
    return tmp_path


@pytest.fixture()
def workspace(ws_root) -> SafeWorkspace:
    return SafeWorkspace(ws_root)


@pytest.fixture()
def sandbox(ws_root) -> LocalProcessSandbox:
    return LocalProcessSandbox(ws_root)


def init_git_repo(path) -> None:
    env = {"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null",
           "PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": str(path)}
    for args in (
        ["git", "init", "-q", "-b", "main"],
        ["git", "config", "user.email", "t@t"],
        ["git", "config", "user.name", "t"],
        ["git", "add", "-A"],
        ["git", "commit", "-qm", "init"],
    ):
        subprocess.run(args, cwd=path, env=env, check=True, capture_output=True)


@pytest.fixture()
def git_ws(ws_root):
    init_git_repo(ws_root)
    return ws_root


@pytest.fixture()
def safegit(git_ws) -> SafeGit:
    return SafeGit(LocalProcessSandbox(git_ws))
