"""Brain: an OpenAI-compatible Chat Completions client.

Provider-independent — works with OpenRouter, OpenAI, or any local
OpenAI-compatible server by changing only configuration. Uses ``httpx``.

The Brain is the ONLY thing that decides *which* tool to call; it can never
execute anything itself. Tool calls are returned as structured data for the
orchestrator to validate and dispatch.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from .models import ChatMessage


@dataclass
class BrainResponse:
    """Parsed Brain response: either a final answer or tool calls."""

    content: str | None
    tool_calls: list[dict[str, Any]]  # each: {"id":..., "name":..., "arguments": dict}
    finish_reason: str
    raw: dict[str, Any]


class Brain(Protocol):
    def chat(self, messages: list[ChatMessage], tools: list[dict[str, Any]]) -> BrainResponse: ...


class OpenAICompatibleBrain:
    """Real Brain backed by an OpenAI-compatible Chat Completions endpoint."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        *,
        timeout: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._timeout = timeout
        # `transport` allows tests to inject a mock transport without network.
        self._client = httpx.Client(timeout=timeout, transport=transport)

    def chat(self, messages: list[ChatMessage], tools: list[dict[str, Any]]) -> BrainResponse:
        url = f"{self._base_url}/chat/completions"
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [m.model_dump(exclude_none=True) for m in messages],
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        # The API key is sent only in the Authorization header; it is never
        # logged and never placed in the message body.
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        resp = self._client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return self._parse(data)

    @staticmethod
    def _parse(data: dict[str, Any]) -> BrainResponse:
        choices = data.get("choices") or []
        if not choices:
            return BrainResponse(content=None, tool_calls=[], finish_reason="empty", raw=data)
        choice = choices[0]
        msg = choice.get("message", {}) or {}
        content = msg.get("content")
        finish_reason = choice.get("finish_reason", "unknown")
        tool_calls: list[dict[str, Any]] = []
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function", {}) or {}
            args_raw = fn.get("arguments", "{}")
            try:
                args = json.loads(args_raw) if isinstance(args_raw, str) else (args_raw or {})
            except json.JSONDecodeError:
                args = {"_invalid_arguments": args_raw}
            tool_calls.append(
                {"id": tc.get("id", ""), "name": fn.get("name", ""), "arguments": args}
            )
        return BrainResponse(
            content=content, tool_calls=tool_calls, finish_reason=finish_reason, raw=data
        )

    def close(self) -> None:
        self._client.close()


# ---------------------------------------------------------------------------
# Mock Brain for tests / integration without a paid provider.
# ---------------------------------------------------------------------------


class MockBrain:
    """A scripted Brain that returns a pre-defined sequence of responses.

    Each entry in ``script`` is a ``(tool_calls, content, finish_reason)``
    tuple. When the script is exhausted it returns a final answer.
    """

    def __init__(
        self,
        script: list[tuple[list[dict[str, Any]] | None, str | None, str]] | None = None,
    ) -> None:
        # script entries: (tool_calls, content, finish_reason)
        self._script = list(script or [])
        self._idx = 0
        # Tracks the sequence of (messages, tool_names) seen for inspection.
        self.calls: list[dict[str, Any]] = []

    def chat(self, messages: list[ChatMessage], tools: list[dict[str, Any]]) -> BrainResponse:
        tool_names_requested = [t["function"]["name"] for t in tools] if tools else []
        self.calls.append({"num_messages": len(messages), "tools_offered": tool_names_requested})
        if self._idx < len(self._script):
            tool_calls, content, finish_reason = self._script[self._idx]
            self._idx += 1
            return BrainResponse(
                content=content,
                tool_calls=tool_calls or [],
                finish_reason=finish_reason,
                raw={},
            )
        # Default: final answer.
        return BrainResponse(content="done", tool_calls=[], finish_reason="stop", raw={})


class RepeatingToolBrain:
    """A Brain that always requests the same tool call (for max-loop tests)."""

    def __init__(self, name: str, arguments: dict[str, Any]) -> None:
        self._name = name
        self._arguments = arguments
        self.calls: list[dict[str, Any]] = []

    def chat(self, messages: list[ChatMessage], tools: list[dict[str, Any]]) -> BrainResponse:
        self.calls.append({"num_messages": len(messages)})
        return BrainResponse(
            content=None,
            tool_calls=[{"id": "repeat", "name": self._name, "arguments": dict(self._arguments)}],
            finish_reason="tool_calls",
            raw={},
        )

class OpenAIResponsesBrain:
    """OpenAI Responses API Brain adapter, used for higher-brain tool calling.

    This keeps TC's internal Brain protocol stable while translating its
    ChatMessage/tool representation into Responses API input/tool items.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        *,
        timeout: float = 120.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._timeout = timeout
        self._client = httpx.Client(timeout=timeout, transport=transport)

    def chat(self, messages: list[ChatMessage], tools: list[dict[str, Any]]) -> BrainResponse:
        input_items: list[dict[str, Any]] = []
        for message in messages:
            if message.role in {"system", "user"}:
                input_items.append({"role": message.role, "content": message.content or ""})
                continue
            if message.role == "assistant":
                if message.content:
                    input_items.append({"role": "assistant", "content": message.content})
                for tc in message.tool_calls or []:
                    fn = tc.get("function") or {}
                    input_items.append(
                        {
                            "type": "function_call",
                            "call_id": tc.get("id", ""),
                            "name": fn.get("name", ""),
                            "arguments": fn.get("arguments", "{}"),
                        }
                    )
                continue
            if message.role == "tool":
                input_items.append(
                    {
                        "type": "function_call_output",
                        "call_id": message.tool_call_id or "",
                        "output": message.content or "",
                    }
                )

        response_tools = []
        for tool in tools:
            fn = tool.get("function", {}) or {}
            response_tools.append(
                {
                    "type": "function",
                    "name": fn.get("name", ""),
                    "description": fn.get("description", ""),
                    "parameters": fn.get("parameters", {"type": "object", "properties": {}}),
                }
            )

        payload: dict[str, Any] = {
            "model": self._model,
            "input": input_items,
            "store": False,
        }
        if response_tools:
            payload["tools"] = response_tools
            payload["tool_choice"] = "auto"

        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        resp = self._client.post(f"{self._base_url}/responses", json=payload, headers=headers)
        resp.raise_for_status()
        return self._parse(resp.json())

    @staticmethod
    def _parse(data: dict[str, Any]) -> BrainResponse:
        tool_calls: list[dict[str, Any]] = []
        text_parts: list[str] = []
        for item in data.get("output") or []:
            kind = item.get("type")
            if kind == "function_call":
                args_raw = item.get("arguments", "{}")
                try:
                    args = json.loads(args_raw) if isinstance(args_raw, str) else (args_raw or {})
                except json.JSONDecodeError:
                    args = {"_invalid_arguments": args_raw}
                tool_calls.append(
                    {
                        "id": item.get("call_id") or item.get("id", ""),
                        "name": item.get("name", ""),
                        "arguments": args,
                    }
                )
            elif kind == "message":
                for content in item.get("content") or []:
                    if content.get("type") in {"output_text", "text"} and content.get("text"):
                        text_parts.append(str(content["text"]))
        if data.get("output_text"):
            text_parts.append(str(data["output_text"]))
        return BrainResponse(
            content="\n".join(text_parts) if text_parts else None,
            tool_calls=tool_calls,
            finish_reason="tool_calls" if tool_calls else str(data.get("status", "completed")),
            raw=data,
        )

    def close(self) -> None:
        self._client.close()
