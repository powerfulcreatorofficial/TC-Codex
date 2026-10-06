"""Tool registry — the authoritative allowlist of tools the Brain may call.

The Brain can never register a new tool. Each tool has a name, description,
input schema (a Pydantic model), permission level, timeout, and a handler
that operates through the ``WorkspaceClient`` (never direct host access).
"""

from __future__ import annotations

import hashlib
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, Field, field_validator

from .grpc_client import WorkspaceClient
from .models import ToolResult


class Permission(StrEnum):
    L0 = "L0"  # read-only / safe
    L1 = "L1"  # mutating, workspace-scoped
    L2 = "L2"  # higher-risk / system-wide (reserved for future tools)


class ToolHandler(Protocol):
    def __call__(self, client: WorkspaceClient, args: dict[str, Any]) -> ToolResult: ...


# ---------------------------------------------------------------------------
# Argument schemas (validated with Pydantic; fail closed on malformed input)
# ---------------------------------------------------------------------------


def _reject_traversal(path: str) -> str:
    """Client-side path pre-check (defense in depth). The daemon also rejects."""
    if not path:
        raise ValueError("path must not be empty")
    # Absolute paths and any parent-dir traversal are rejected.
    import os as _os

    if _os.path.isabs(path):
        raise ValueError("absolute paths are not allowed")
    norm = _os.path.normpath(path)
    if norm.startswith("..") or _os.path.isabs(norm):
        raise ValueError("path escapes the workspace root")
    return path


class ReadFileArgs(BaseModel):
    path: str
    offset: int = 0
    length: int = 0

    @field_validator("path")
    @classmethod
    def _check_path(cls, v: str) -> str:
        return _reject_traversal(v)

    @field_validator("offset", "length")
    @classmethod
    def _non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("must be >= 0")
        return v


class WriteFileArgs(BaseModel):
    path: str
    content: str
    # Optional: if omitted the orchestrator reads the current file to compute
    # its hash (transparent compare-and-set). For new files the empty hash is
    # used automatically.
    expected_hash: str | None = None

    @field_validator("path")
    @classmethod
    def _check_path(cls, v: str) -> str:
        return _reject_traversal(v)


class ExecCommandArgs(BaseModel):
    argv: list[str] = Field(min_length=1)
    timeout_seconds: int = 30

    @field_validator("timeout_seconds")
    @classmethod
    def _check_timeout(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("timeout_seconds must be > 0")
        if v > 600:
            raise ValueError("timeout_seconds must be <= 600")
        return v


class GitStatusArgs(BaseModel):
    # No arguments; defined for uniform handling.
    pass


# ---------------------------------------------------------------------------
# Handlers (go through the WorkspaceClient only)
# ---------------------------------------------------------------------------

_EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


def _handle_read_file(client: WorkspaceClient, args: dict[str, Any]) -> ToolResult:
    a = ReadFileArgs.model_validate(args)
    res = client.read_file(a.path, offset=a.offset, length=a.length)
    return ToolResult(
        name="read_file",
        ok=True,
        output=f"sha256={res.sha256} size={res.total_size} truncated={res.truncated}\n{res.text}",
    )


def _handle_write_file(client: WorkspaceClient, args: dict[str, Any]) -> ToolResult:
    a = WriteFileArgs.model_validate(args)
    expected = a.expected_hash
    if expected is None:
        # Transparent CAS: compute current hash by reading the file first.
        # A missing file (or any read error) is treated as a new file whose
        # current hash is the SHA-256 of the empty string.
        try:
            current = client.read_file(a.path)
            expected = current.sha256
        except Exception:  # noqa: BLE001 - missing/protected file => empty hash
            expected = _EMPTY_SHA256
    content_bytes = a.content.encode("utf-8")
    res = client.write_file(a.path, content_bytes, expected)
    if not res.written:
        return ToolResult(name="write_file", ok=False, output="", error="write refused by daemon")
    return ToolResult(name="write_file", ok=True, output=f"written sha256={res.sha256}")


_MAX_EXEC_OUTPUT_CHARS = 32_000


def _cap(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[:limit] + f"\n...[truncated {len(text) - limit} chars]", True


def _handle_exec_command(client: WorkspaceClient, args: dict[str, Any]) -> ToolResult:
    a = ExecCommandArgs.model_validate(args)
    res = client.exec_command(a.argv, a.timeout_seconds)
    # Truthful outcome: a command is only "ok" when it both completed AND
    # exited 0. A failing test run must remain a failure.
    ok = res.status == "completed" and res.exit_code == 0
    stdout, t1 = _cap(res.stdout_text, _MAX_EXEC_OUTPUT_CHARS // 2)
    stderr, t2 = _cap(res.stderr_text, _MAX_EXEC_OUTPUT_CHARS // 2)
    out = (
        f"status={res.status} exit_code={res.exit_code} duration_ms={res.duration_ms}\n"
        f"--- stdout ---\n{stdout}\n--- stderr ---\n{stderr}"
    )
    error = None
    if res.status != "completed":
        error = f"command did not complete: status={res.status}"
    elif res.exit_code != 0:
        error = f"command exited with non-zero code {res.exit_code}"
    return ToolResult(
        name="exec_command",
        ok=ok,
        output=out,
        error=error,
        exit_code=res.exit_code,
        truncated=t1 or t2,
    )


def _handle_git_status(client: WorkspaceClient, args: dict[str, Any]) -> ToolResult:
    GitStatusArgs.model_validate(args)
    res = client.git_status()
    lines = [f"branch={res.branch} clean={res.clean}"]
    for path, status in res.entries:
        lines.append(f"{status}\t{path}")
    return ToolResult(name="git_status", ok=True, output="\n".join(lines))


# ---------------------------------------------------------------------------
# Tool definition + registry
# ---------------------------------------------------------------------------


class Tool:
    __slots__ = (
        "name",
        "description",
        "args_model",
        "permission",
        "read_only",
        "timeout",
        "handler",
    )

    def __init__(
        self,
        name: str,
        description: str,
        args_model: type[BaseModel],
        permission: Permission,
        read_only: bool,
        timeout: int,
        handler: ToolHandler,
    ) -> None:
        self.name = name
        self.description = description
        self.args_model = args_model
        self.permission = permission
        self.read_only = read_only
        self.timeout = timeout
        self.handler = handler

    def openai_schema(self) -> dict[str, Any]:
        """Render the tool in the OpenAI function-calling schema."""
        schema = self.args_model.model_json_schema()
        # OpenAI expects "parameters" with type object.
        params = {
            "type": "object",
            "properties": schema.get("properties", {}),
        }
        required = schema.get("required", [])
        if required:
            params["required"] = required
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": params,
            },
        }


class ToolRegistry:
    """Authoritative allowlist of registered tools."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def has(self, name: str) -> bool:
        return name in self._tools

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def openai_tools(self) -> list[dict[str, Any]]:
        return [t.openai_schema() for t in self._tools.values()]


def default_registry() -> ToolRegistry:
    """Build the default Step 3 tool registry."""
    reg = ToolRegistry()
    reg.register(
        Tool(
            name="read_file",
            description=(
                "Read a file from the workspace root. Paths outside the workspace are rejected."
            ),
            args_model=ReadFileArgs,
            permission=Permission.L0,
            read_only=True,
            timeout=15,
            handler=_handle_read_file,
        )
    )
    reg.register(
        Tool(
            name="write_file",
            description="Atomically write a file using compare-and-set on its current SHA-256.",
            args_model=WriteFileArgs,
            permission=Permission.L1,
            read_only=False,
            timeout=15,
            handler=_handle_write_file,
        )
    )
    reg.register(
        Tool(
            name="exec_command",
            description=(
                "Execute a command through the workspace daemon (cwd-confined, "
                "env-cleared; NOT a kernel-level sandbox) with an explicit timeout."
            ),
            args_model=ExecCommandArgs,
            permission=Permission.L1,
            read_only=False,
            timeout=600,
            handler=_handle_exec_command,
        )
    )
    reg.register(
        Tool(
            name="git_status",
            description="Report the git status of the workspace.",
            args_model=GitStatusArgs,
            permission=Permission.L0,
            read_only=True,
            timeout=15,
            handler=_handle_git_status,
        )
    )
    return reg
