"""Codex-style iterative agent loop for Cybertron's ACT stage.

Instead of executing a fixed up-front plan, the model works in turns: it
calls tools (shell, apply_patch, read_file, grep, glob, list_dir,
update_plan), observes each structured result, and decides the next action
— exactly the interaction model of Codex. Cybertron keeps its own hard
guarantees around the loop:

- every model call is budget-charged BEFORE it is made
- every shell command passes the execution policy (approval policy ×
  sandbox mode × known-safe classification); the model may request
  escalated permissions with a justification, which routes to the external
  approval gate — denial is fed back to the model as data, never bypassed
- patches/writes are confined to the SafeWorkspace (traversal/symlink safe)
- tool outputs are truncated and the transcript is compacted when it grows
  past its budget (oldest tool outputs are elided first)
- repeated identical tool calls abort the loop
- the loop NEVER decides success: the engine's deterministic VERIFY and
  independent REVIEW stages remain the only path to a SUCCESS report.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from .apply_patch import apply_any_patch
from .budget import TaskBudget
from .exec_policy import ApprovalPolicy, SandboxMode, decide_exec
from .live_plan import LivePlan
from .tools import CybertronToolset

# ---------------------------------------------------------------------------
# model protocol (provider-independent)
# ---------------------------------------------------------------------------


@dataclass
class ModelToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ModelTurn:
    content: str | None
    tool_calls: list[ModelToolCall] = field(default_factory=list)


class ToolBrain(Protocol):
    """Anything that can take OpenAI-style messages + tool schemas and
    return one assistant turn. Satisfied by an adapter over any provider."""

    def turn(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ModelTurn: ...


# ---------------------------------------------------------------------------
# tool schemas exposed to the model
# ---------------------------------------------------------------------------


def _fn(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


def agent_tool_schemas() -> list[dict[str, Any]]:
    return [
        _fn(
            "shell",
            "Run a command in the sandboxed workspace. Network is off. "
            "Set with_escalated_permissions=true plus a justification to "
            "request external approval for commands outside your sandbox "
            "policy.",
            {
                "command": {"type": "array", "items": {"type": "string"},
                            "description": "argv, e.g. ['python','-m','pytest','-q']"},
                "workdir": {"type": "string"},
                "timeout_seconds": {"type": "number"},
                "with_escalated_permissions": {"type": "boolean"},
                "justification": {"type": "string"},
            },
            ["command"],
        ),
        _fn(
            "apply_patch",
            "Edit files using the apply_patch envelope: '*** Begin Patch' / "
            "'*** Add File:'/'*** Update File:'/'*** Delete File:' (+ optional "
            "'*** Move to:'), '@@' context hunks, '*** End Patch'. Classic "
            "unified diffs are also accepted.",
            {"patch": {"type": "string"}},
            ["patch"],
        ),
        _fn(
            "read_file",
            "Read a file (optionally a line range).",
            {
                "path": {"type": "string"},
                "start_line": {"type": "integer"},
                "max_lines": {"type": "integer"},
            },
            ["path"],
        ),
        _fn("list_dir", "List a directory.", {"path": {"type": "string"}}, []),
        _fn(
            "grep",
            "Regex search across the workspace.",
            {
                "pattern": {"type": "string"},
                "path_glob": {"type": "string"},
                "max_matches": {"type": "integer"},
            },
            ["pattern"],
        ),
        _fn("glob", "Find files matching a glob pattern.",
            {"pattern": {"type": "string"}}, ["pattern"]),
        _fn(
            "update_plan",
            "Maintain your live step plan. Provide the full list of steps "
            "with statuses (pending|in_progress|completed); keep at most one "
            "step in_progress.",
            {
                "explanation": {"type": "string"},
                "plan": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "step": {"type": "string"},
                            "status": {"type": "string",
                                       "enum": ["pending", "in_progress", "completed"]},
                        },
                        "required": ["step", "status"],
                    },
                },
            },
            ["plan"],
        ),
    ]


# ---------------------------------------------------------------------------
# loop
# ---------------------------------------------------------------------------


@dataclass
class AgentLoopConfig:
    approval_policy: ApprovalPolicy = ApprovalPolicy.UNTRUSTED
    sandbox_mode: SandboxMode = SandboxMode.WORKSPACE_WRITE
    max_tool_output_chars: int = 10_000
    transcript_char_budget: int = 160_000
    max_identical_calls: int = 3
    default_shell_timeout: float = 120.0


@dataclass
class AgentLoopResult:
    finished: bool
    final_message: str | None
    model_turns: int
    tool_calls: int
    live_plan: LivePlan
    denials: int = 0
    error: str | None = None


EventHook = Callable[[str, dict[str, Any]], None]
# Approval gate contract matches the engine's: (stage, description, detail) -> bool
GateFn = Callable[[str, str, dict[str, Any]], bool]

_TRIMMED = "[output elided to fit context budget]"


class AgentLoop:
    """One stateful loop per task; ``run`` can be called again for repair
    turns and continues the same transcript."""

    def __init__(
        self,
        brain: ToolBrain,
        toolset: CybertronToolset,
        budget: TaskBudget,
        *,
        system_prompt: str,
        config: AgentLoopConfig | None = None,
        gate: GateFn | None = None,
        on_event: EventHook | None = None,
    ) -> None:
        self._brain = brain
        self._toolset = toolset
        self._budget = budget
        self._config = config or AgentLoopConfig()
        self._gate = gate
        self._on_event = on_event
        self._messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt}
        ]
        self.live_plan = LivePlan()
        self._turns = 0
        self._tool_calls = 0
        self._denials = 0
        self._last_sig: str | None = None
        self._repeat = 0

    # ------------------------------------------------------------------

    def run(self, user_message: str) -> AgentLoopResult:
        self._messages.append({"role": "user", "content": user_message})
        tools = agent_tool_schemas()

        while True:
            self._budget.charge_step()
            # Budget must be charged BEFORE the model call.
            self._budget.charge_model_call()
            turn = self._brain.turn(list(self._messages), tools)
            self._turns += 1

            if not turn.tool_calls:
                final = (turn.content or "").strip()
                self._messages.append({"role": "assistant", "content": final})
                self._emit("model_final_message", {"chars": len(final)})
                return self._result(finished=True, final=final)

            self._messages.append({
                "role": "assistant",
                "content": turn.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments),
                        },
                    }
                    for tc in turn.tool_calls
                ],
            })

            if len(turn.tool_calls) == 1:
                tc = turn.tool_calls[0]
                sig = tc.name + json.dumps(tc.arguments, sort_keys=True, default=str)
                if sig == self._last_sig:
                    self._repeat += 1
                else:
                    self._repeat = 0
                    self._last_sig = sig
                if self._repeat >= self._config.max_identical_calls - 1:
                    return self._result(
                        finished=False,
                        final=None,
                        error=(
                            "aborted: model repeated the identical tool call "
                            f"{self._repeat + 1} times without progress"
                        ),
                    )

            for tc in turn.tool_calls:
                self._budget.charge_tool_call()
                self._tool_calls += 1
                payload = self._dispatch(tc)
                text = json.dumps(payload, default=str)
                if len(text) > self._config.max_tool_output_chars:
                    text = text[: self._config.max_tool_output_chars] + '..."}'
                self._messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": tc.name,
                    "content": text,
                })
            self._compact_if_needed()

    # ------------------------------------------------------------------
    # dispatch
    # ------------------------------------------------------------------

    def _dispatch(self, tc: ModelToolCall) -> dict[str, Any]:
        name, args = tc.name, tc.arguments or {}
        self._emit("tool_started", {"tool": name})
        try:
            if name == "shell":
                out = self._shell(args)
            elif name == "apply_patch":
                out = self._apply_patch(args)
            elif name == "update_plan":
                out = self._update_plan(args)
            elif name in ("read_file", "list_dir", "grep", "glob"):
                outcome = self._toolset.execute(name, args)
                out = {
                    "ok": outcome.ok,
                    "output": outcome.output,
                    "error": outcome.error,
                    "truncated": outcome.truncated,
                }
            else:
                out = {"ok": False, "error": f"unknown tool: {name}"}
        except Exception as exc:  # noqa: BLE001 - loop must report, not crash
            out = {"ok": False, "error": f"tool error: {exc}"}
        self._emit("tool_finished", {
            "tool": name,
            "ok": bool(out.get("ok")),
            "exit_code": out.get("exit_code"),
            "error": (str(out.get("error"))[:300] if out.get("error") else None),
        })
        return out

    def _shell(self, args: dict[str, Any]) -> dict[str, Any]:
        argv = args.get("command")
        if not isinstance(argv, list) or not all(isinstance(a, str) for a in argv) or not argv:
            return {"ok": False, "error": "command must be a non-empty argv array"}
        escalated = bool(args.get("with_escalated_permissions"))
        justification = str(args.get("justification") or "")[:500]
        decision = decide_exec(
            argv,
            approval_policy=self._config.approval_policy,
            sandbox_mode=self._config.sandbox_mode,
            escalation_requested=escalated,
        )
        if decision.needs_approval:
            detail = {
                "command": argv,
                "reason": decision.reason,
                "justification": justification,
                "sandbox_mode": self._config.sandbox_mode.value,
            }
            approved = bool(self._gate and self._gate("ACT", "run command", detail))
            self._emit("exec_approval_decided", {
                "command": " ".join(argv)[:200], "approved": approved,
                "reason": decision.reason,
            })
            if not approved:
                self._denials += 1
                return {
                    "ok": False,
                    "approval": "denied",
                    "error": (
                        "approval denied or unavailable for this command "
                        f"({decision.reason}); choose a different approach"
                    ),
                }
        timeout = float(args.get("timeout_seconds") or self._config.default_shell_timeout)
        outcome = self._toolset.execute("run_command", {
            "argv": argv,
            "cwd": args.get("workdir"),
            "timeout_seconds": max(1.0, min(timeout, 1800.0)),
        })
        return {
            "ok": outcome.ok,
            "exit_code": outcome.exit_code,
            "output": outcome.output,
            "error": outcome.error,
            "truncated": outcome.truncated,
        }

    def _apply_patch(self, args: dict[str, Any]) -> dict[str, Any]:
        patch = args.get("patch")
        if not isinstance(patch, str) or not patch.strip():
            return {"ok": False, "error": "patch must be a non-empty string"}
        # Workspace writes: read-only sandbox or untrusted policy => gate.
        needs_approval = (
            self._config.sandbox_mode == SandboxMode.READ_ONLY
            or self._config.approval_policy == ApprovalPolicy.UNTRUSTED
        )
        if needs_approval:
            approved = bool(
                self._gate
                and self._gate("ACT", "apply patch", {"patch_bytes": len(patch)})
            )
            if not approved:
                self._denials += 1
                return {"ok": False, "approval": "denied",
                        "error": "patch approval denied or unavailable"}
        try:
            changed = apply_any_patch(self._toolset.workspace, patch)
        except Exception as exc:  # noqa: BLE001 - structured failure to the model
            return {"ok": False, "error": f"patch failed: {exc}"}
        self._emit("patch_applied", {"changed_files": changed})
        return {"ok": True, "changed_files": changed}

    def _update_plan(self, args: dict[str, Any]) -> dict[str, Any]:
        error = self.live_plan.update(
            args.get("plan") or [], str(args.get("explanation") or "")
        )
        if error:
            return {"ok": False, "error": error}
        self._emit("plan_updated", self.live_plan.as_dict())
        return {"ok": True, "plan": self.live_plan.as_dict()}

    # ------------------------------------------------------------------
    # context compaction
    # ------------------------------------------------------------------

    def _compact_if_needed(self) -> None:
        total = sum(len(str(m.get("content") or "")) for m in self._messages)
        if total <= self._config.transcript_char_budget:
            return
        # Elide oldest tool outputs first (never the system prompt or the
        # latest exchanges); honest placeholder, no fabricated summaries.
        for message in self._messages[1:-6]:
            if message.get("role") == "tool" and message.get("content") != _TRIMMED:
                message["content"] = _TRIMMED
                total = sum(len(str(m.get("content") or "")) for m in self._messages)
                if total <= self._config.transcript_char_budget:
                    break
        self._emit("transcript_compacted", {"chars": total})

    # ------------------------------------------------------------------

    def _result(
        self, *, finished: bool, final: str | None, error: str | None = None
    ) -> AgentLoopResult:
        return AgentLoopResult(
            finished=finished,
            final_message=final,
            model_turns=self._turns,
            tool_calls=self._tool_calls,
            live_plan=self.live_plan,
            denials=self._denials,
            error=error,
        )

    def _emit(self, event_type: str, detail: dict[str, Any]) -> None:
        if self._on_event is not None:
            try:
                self._on_event(event_type, detail)
            except Exception:  # noqa: BLE001 - telemetry never affects execution
                pass
