"""The bounded agent orchestration loop.

Creator prompt -> Orchestrator -> Brain -> structured tool call -> validation
-> (approval gate for L1/L2) -> Workspace Daemon -> redacted tool result ->
Brain -> next tool call -> repeat until completion (or MAX_AGENT_STEPS).

When approval is enabled, mutating (L1/L2) tool requests pause the loop: the
pending action is persisted, the task enters ``AWAITING_APPROVAL``, and the
loop resumes only after an external approval decision references the exact
pending action (single-use nonce). The Brain can never approve its own action.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .approval import ApprovalRequest
from .brain import Brain, BrainResponse
from .grpc_client import WorkspaceClient
from .models import ChatMessage, TaskStatus, TaskSummary, ToolResult
from .policy import ApprovalPolicy, needs_approval, risk_level
from .redaction import Redactor
from .tool_registry import Permission, ToolRegistry, default_registry
from .tool_router import ToolRouter, UnknownToolError


@dataclass
class OrchestratorConfig:
    max_steps: int = 20
    system_prompt: str = (
        "You are the Engineering TC Brain. You may ONLY call the registered "
        "tools provided. Never attempt to run shell commands directly. Path "
        "access is confined to the workspace root; traversal attempts are "
        "rejected. Use tools to accomplish the user's task, then give a final "
        "answer."
    )
    # Step 4 approval gating. Default OFF so Step 3 behavior is unchanged;
    # Step 4 enables it via the policy.
    approval_policy: ApprovalPolicy = field(default_factory=ApprovalPolicy.disabled)
    approval_expiry_seconds: int = 300
    learning_context: str = ""
    project_context: str = ""
    plan_context: str = ""
    repository_context: str = ""
    max_repair_attempts: int = 3


@dataclass
class LoopResult:
    finished: bool
    answer: str | None
    steps: int
    tool_results: list[ToolResult] = field(default_factory=list)
    error: str | None = None
    # The full transcript of messages (for debugging; secrets already redacted).
    messages: list[ChatMessage] = field(default_factory=list)
    # Step 4: when set, the loop paused on a tool that needs approval.
    awaiting_approval: ApprovalRequest | None = None
    # The raw (in-process only) arguments of the paused action, used to resume
    # after approval. Never persisted, never shown to the Brain.
    pending_arguments: dict[str, Any] | None = None
    brain_calls: list[Any] = field(default_factory=list)


class Orchestrator:
    def __init__(
        self,
        brain: Brain,
        client: WorkspaceClient,
        registry: ToolRegistry | None = None,
        redactor: Redactor | None = None,
        config: OrchestratorConfig | None = None,
    ) -> None:
        self._brain = brain
        self._client = client
        self._registry = registry or default_registry()
        self._router = ToolRouter(self._registry, client)
        self._redactor = redactor or Redactor.from_env()
        self._config = config or OrchestratorConfig()

    @property
    def registry(self) -> ToolRegistry:
        return self._registry

    @property
    def config(self) -> OrchestratorConfig:
        return self._config

    def run(self, prompt: str) -> LoopResult:
        system_content = self._config.system_prompt
        if self._config.learning_context.strip():
            system_content += "\n\nRelevant verified engineering lessons from prior TC runs:\n" + self._config.learning_context.strip()
        if self._config.project_context.strip():
            system_content += "\n\nActive project context:\n" + self._config.project_context.strip()
        if self._config.plan_context.strip():
            system_content += "\n\nApproved engineering plan:\n" + self._config.plan_context.strip()
        if self._config.repository_context.strip():
            system_content += "\n\nCurrent repository evidence:\n" + self._config.repository_context.strip()
        messages: list[ChatMessage] = [
            ChatMessage(role="system", content=system_content),
            ChatMessage(role="user", content=prompt),
        ]
        return self._loop(messages, prompt)

    def resume(
        self,
        messages: list[ChatMessage],
        approved_action: tuple[str, dict[str, Any]],
    ) -> LoopResult:
        """Resume the loop after an approval. Executes the EXACT approved
        action (tool_name, arguments), feeds the redacted result to the Brain,
        and continues the loop."""
        results: list[ToolResult] = []
        name, arguments = approved_action
        result = self._execute_tool(name, arguments)
        results.append(result)
        call_id = self._find_tool_call_id(messages, name)
        self._append_redacted_tool_result(messages, result, tool_call_id=call_id)
        return self._loop(messages, None, starting_results=results)

    # ---- internals ----

    def _loop(
        self,
        messages: list[ChatMessage],
        prompt: str | None,
        starting_results: list[ToolResult] | None = None,
    ) -> LoopResult:
        tools = self._registry.openai_tools()
        results: list[ToolResult] = list(starting_results or [])
        brain_calls: list[Any] = []
        last_call: tuple[str, str] | None = None
        repeat_count = 0

        for step in range(1, self._config.max_steps + 1):
            brain_resp: BrainResponse = self._brain.chat(messages, tools)
            router_calls = getattr(self._brain, "calls", None)
            if isinstance(router_calls, list):
                brain_calls = list(router_calls)

            if not brain_resp.tool_calls:
                answer = self._redactor.redact(brain_resp.content or "")
                messages.append(ChatMessage(role="assistant", content=answer))
                return LoopResult(
                    finished=True,
                    answer=answer,
                    steps=step,
                    tool_results=results,
                    messages=messages,
                    brain_calls=brain_calls,
                )

            assistant_msg = ChatMessage(
                role="assistant",
                content=brain_resp.content,
                tool_calls=[
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(tc["arguments"]),
                        },
                    }
                    for tc in brain_resp.tool_calls
                ],
            )
            messages.append(assistant_msg)

            if len(brain_resp.tool_calls) == 1:
                tc = brain_resp.tool_calls[0]
                sig = (tc["name"], json.dumps(tc["arguments"], sort_keys=True))
                if sig == last_call:
                    repeat_count += 1
                else:
                    repeat_count = 0
                    last_call = sig
                if repeat_count >= 3:
                    return LoopResult(
                        finished=False,
                        answer=None,
                        steps=step,
                        tool_results=results,
                        error=(
                            "aborted: Brain repeated the identical tool call "
                            f"{repeat_count + 1} times without progress"
                        ),
                        messages=messages,
                        brain_calls=brain_calls,
                    )

            # Execute each requested tool call, applying the approval gate.
            for tc in brain_resp.tool_calls:
                name, arguments = tc["name"], tc["arguments"]

                # Approval gate for mutating tools.
                tool = self._registry.get(name)
                if tool is not None and needs_approval(
                    self._config.approval_policy, tool.permission
                ):
                    # Pause: build the exact pending action (redacted summary +
                    # single-use nonce). The driver persists it and must obtain
                    # an external approval referencing this nonce before
                    # calling resume() with the same (name, arguments).
                    pending = self.build_approval_request("", name, arguments, tool.permission)
                    # Pause: surface the exact pending action (redacted summary +
                    # single-use nonce) plus the raw in-process arguments for
                    # the driver to resume after approval.
                    return LoopResult(
                        finished=False,
                        answer=None,
                        steps=step,
                        tool_results=results,
                        messages=messages,
                        awaiting_approval=pending,
                        brain_calls=brain_calls,
                        pending_arguments=dict(arguments),
                        error=None,
                    )

                result = self._execute_tool(name, arguments)
                results.append(result)
                self._append_redacted_tool_result(messages, result, tool_call_id=tc.get("id"))
                if not result.ok:
                    from .adaptive import classify_failure, recovery_prompt
                    synthetic = TaskSummary(
                        task_id="in-loop",
                        status=TaskStatus.FAILED,
                        prompt=prompt or "",
                        error=result.error or "tool failure",
                        steps=step,
                        current_step=step,
                        max_steps=self._config.max_steps,
                    )
                    decision = classify_failure(synthetic, [{"event_type": "tool_failed", "tool_name": name, "result_metadata": {"error": result.error}}], max_repair_attempts=self._config.max_repair_attempts)
                    messages.append(ChatMessage(role="system", content=recovery_prompt(decision)))

        return LoopResult(
            finished=False,
            answer=None,
            steps=self._config.max_steps,
            tool_results=results,
            error=f"aborted: reached MAX_AGENT_STEPS={self._config.max_steps}",
            messages=messages,
            brain_calls=brain_calls,
        )

    def _approval_for(self, name: str) -> bool:
        """Whether the named tool requires approval under the current policy."""
        tool = self._registry.get(name)
        if tool is None:
            return False
        return needs_approval(self._config.approval_policy, tool.permission)

    def build_approval_request(
        self, task_id: str, tool_name: str, arguments: dict[str, Any], permission: Permission
    ) -> ApprovalRequest:
        """Build a redacted, persistable approval request for a pending action."""
        from .approval import expiry_from_now, new_nonce, utcnow

        summary = self._safe_arg_summary(tool_name, arguments)
        return ApprovalRequest(
            task_id=task_id,
            tool_name=tool_name,
            arguments_metadata=summary,
            risk_level=risk_level(permission),
            nonce=new_nonce(),
            created_at=utcnow(),
            expires_at=expiry_from_now(self._config.approval_expiry_seconds),
        )

    def _safe_arg_summary(self, tool_name: str, arguments: dict[str, Any]) -> dict:
        """A redacted, safe-to-store/show summary of tool arguments (no secrets)."""
        if tool_name == "exec_command":
            return {"argv": [self._redactor.redact(str(a)) for a in arguments.get("argv", [])]}
        if tool_name == "write_file":
            content = str(arguments.get("content", ""))
            redacted = self._redactor.redact(content)
            return {
                "path": arguments.get("path"),
                "content_length": len(content),
                "content_preview": redacted[:64],
            }
        # read_file / git_status / others: path only, redacted.
        return {k: self._redactor.redact(str(v)) for k, v in arguments.items()}

    def _find_tool_call_id(self, messages: list[ChatMessage], name: str) -> str | None:
        for message in reversed(messages):
            if message.role != "assistant":
                continue
            for call in message.tool_calls or []:
                fn = call.get("function") or {}
                if fn.get("name") == name:
                    return call.get("id")
        return None

    def _append_redacted_tool_result(self, messages: list[ChatMessage], result: ToolResult, tool_call_id: str | None = None) -> None:
        redacted_output = self._redactor.redact(result.output)
        redacted_error = self._redactor.redact(result.error) if result.error else None
        safe = ToolResult(
            name=result.name, ok=result.ok, output=redacted_output, error=redacted_error
        )
        messages.append(ChatMessage(role="tool", content=safe.to_compact(), name=safe.name, tool_call_id=tool_call_id))

    def _execute_tool(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        try:
            return self._router.execute(name, arguments)
        except UnknownToolError as exc:
            return ToolResult(name=name, ok=False, output="", error=str(exc))
