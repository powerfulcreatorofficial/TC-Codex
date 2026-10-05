"""TEST B / TEST G — Tool router: argument validation + workspace boundary."""

from __future__ import annotations

import pytest

from tc_orchestrator.models import ToolResult
from tc_orchestrator.tool_registry import default_registry
from tc_orchestrator.tool_router import ToolRouter, UnknownToolError


def router_with(client) -> ToolRouter:
    return ToolRouter(default_registry(), client)


def test_unknown_tool_rejected(fake_client):
    router = router_with(fake_client)
    with pytest.raises(UnknownToolError):
        router.execute("delete_everything", {})


def test_malformed_arguments_fail_safely(fake_client):
    router = router_with(fake_client)
    # read_file requires a non-empty path string.
    res = router.execute("read_file", {"path": ""})
    assert isinstance(res, ToolResult)
    assert res.ok is False
    assert res.error is not None


def test_exec_command_requires_argv(fake_client):
    router = router_with(fake_client)
    res = router.execute("exec_command", {"argv": [], "timeout_seconds": 5})
    assert res.ok is False


def test_exec_command_requires_positive_timeout(fake_client):
    router = router_with(fake_client)
    res = router.execute("exec_command", {"argv": ["true"], "timeout_seconds": 0})
    assert res.ok is False
    assert "timeout" in (res.error or "").lower()


def test_path_traversal_rejected(fake_client):
    """TEST G — ../../etc/passwd must be rejected before reaching the daemon."""
    router = router_with(fake_client)
    res = router.execute("read_file", {"path": "../../etc/passwd"})
    assert res.ok is False
    assert "escape" in (res.error or "").lower() or "workspace" in (res.error or "").lower()
    # The fake client must NOT have been asked for the escaped path.
    assert "../../etc/passwd" not in fake_client.files


def test_absolute_path_rejected(fake_client):
    router = router_with(fake_client)
    res = router.execute("read_file", {"path": "/etc/passwd"})
    assert res.ok is False


def test_write_file_traversal_rejected(fake_client):
    router = router_with(fake_client)
    res = router.execute("write_file", {"path": "../../etc/shadow", "content": "x"})
    assert res.ok is False


def test_valid_read_file_dispatches(fake_client_with_files):
    router = router_with(fake_client_with_files)
    res = router.execute("read_file", {"path": "README.md"})
    assert res.ok is True
    assert "Engineering TC" in res.output
