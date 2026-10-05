"""TEST A — Tool registry."""

from __future__ import annotations

import pytest

from tc_orchestrator.tool_registry import Permission, default_registry


def test_default_registry_has_required_tools():
    reg = default_registry()
    for name in ["read_file", "write_file", "exec_command", "git_status"]:
        assert reg.has(name), f"missing tool: {name}"


def test_unknown_tool_rejected():
    reg = default_registry()
    assert reg.get("delete_everything") is None
    assert not reg.has("delete_everything")


def test_permission_and_readonly_flags():
    reg = default_registry()
    assert reg.get("read_file").read_only is True
    assert reg.get("read_file").permission == Permission.L0
    assert reg.get("write_file").read_only is False
    assert reg.get("write_file").permission == Permission.L1
    assert reg.get("exec_command").read_only is False
    assert reg.get("exec_command").permission == Permission.L1
    assert reg.get("git_status").read_only is True
    assert reg.get("git_status").permission == Permission.L0


def test_openai_schema_has_function_name():
    reg = default_registry()
    schemas = reg.openai_tools()
    names = {s["function"]["name"] for s in schemas}
    assert names == {"read_file", "write_file", "exec_command", "git_status"}


def test_cannot_register_duplicate():
    from tc_orchestrator.tool_registry import GitStatusArgs, Tool, ToolRegistry

    reg = ToolRegistry()
    t = Tool(
        name="x",
        description="d",
        args_model=GitStatusArgs,
        permission=Permission.L0,
        read_only=True,
        timeout=1,
        handler=lambda c, a: None,
    )
    reg.register(t)
    with pytest.raises(ValueError):
        reg.register(t)
