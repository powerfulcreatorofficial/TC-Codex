"""Tool router: validate and dispatch Brain-requested tool calls.

Responsibilities:
1. Validate the tool name against the registry (fail closed on unknown tools).
2. Validate arguments with the tool's Pydantic schema.
3. Enforce path restrictions (client-side pre-check; daemon also enforces).
4. Dispatch to the handler through the ``WorkspaceClient``.
5. Return a structured ``ToolResult`` (failures are returned as ok=False, not
   raised, so the Brain can react — except for unknown tools which are
   hard-rejected as security violations).
"""

from __future__ import annotations

from typing import Any

from .grpc_client import WorkspaceClient
from .models import ToolResult
from .tool_registry import ToolRegistry


class UnknownToolError(Exception):
    """Raised when the Brain requests a tool that is not in the registry."""


class ToolRouter:
    def __init__(self, registry: ToolRegistry, client: WorkspaceClient) -> None:
        self._registry = registry
        self._client = client

    @property
    def registry(self) -> ToolRegistry:
        return self._registry

    def execute(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        tool = self._registry.get(name)
        if tool is None:
            # Hard reject: the Brain may never call an unregistered tool.
            raise UnknownToolError(f"unknown tool: {name}")

        # Validate arguments (fail closed on malformed input).
        try:
            tool.args_model.model_validate(arguments)
        except Exception as exc:  # noqa: BLE001 - surface validation errors
            return ToolResult(
                name=name,
                ok=False,
                output="",
                error=f"invalid arguments: {exc}",
            )

        # Dispatch to the handler. Handler exceptions become tool failures so
        # the loop can continue; the Brain sees a structured error.
        try:
            return tool.handler(self._client, arguments)
        except Exception as exc:  # noqa: BLE001 - never crash the loop
            return ToolResult(
                name=name,
                ok=False,
                output="",
                error=f"tool execution error: {exc}",
            )
