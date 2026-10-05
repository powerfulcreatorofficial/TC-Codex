"""Brain parsing tests (mocked OpenAI-compatible responses)."""

from __future__ import annotations

import json

from tc_orchestrator.brain import OpenAICompatibleBrain
from tc_orchestrator.models import ChatMessage


class _MockTransport:
    """httpx mock transport that returns a canned JSON body."""

    def __init__(self, body: dict, status: int = 200) -> None:
        self.body = body
        self.status = status
        self.last_request = None

    def handle_request(self, request):
        import httpx

        self.last_request = request
        return httpx.Response(
            self.status,
            content=json.dumps(self.body).encode(),
            request=request,
        )


def _tool_call_msg(name, args):
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_1",
                "function": {"name": name, "arguments": json.dumps(args)},
            }
        ],
    }


def test_brain_parses_tool_call():
    body = {
        "choices": [
            {
                "finish_reason": "tool_calls",
                "message": _tool_call_msg("read_file", {"path": "README.md"}),
            }
        ]
    }
    transport = _MockTransport(body)
    brain = OpenAICompatibleBrain(
        base_url="https://example.com/v1", api_key="sk-test", model="m", transport=transport
    )
    resp = brain.chat([ChatMessage(role="user", content="hi")], tools=[])
    assert resp.tool_calls == [
        {"id": "call_1", "name": "read_file", "arguments": {"path": "README.md"}}
    ]
    assert resp.finish_reason == "tool_calls"


def test_brain_parses_final_answer():
    body = {
        "choices": [
            {"finish_reason": "stop", "message": {"role": "assistant", "content": "all done"}}
        ]
    }
    transport = _MockTransport(body)
    brain = OpenAICompatibleBrain(
        base_url="https://example.com/v1", api_key="sk-test", model="m", transport=transport
    )
    resp = brain.chat([ChatMessage(role="user", content="hi")], tools=[])
    assert resp.content == "all done"
    assert resp.tool_calls == []


def test_brain_invalid_arguments_handled():
    body = {
        "choices": [
            {
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "x",
                            "function": {"name": "read_file", "arguments": "{not json}"},
                        }
                    ],
                },
            }
        ]
    }
    transport = _MockTransport(body)
    brain = OpenAICompatibleBrain(
        base_url="https://example.com/v1", api_key="sk-test", model="m", transport=transport
    )
    resp = brain.chat([ChatMessage(role="user", content="hi")], tools=[])
    assert resp.tool_calls[0]["arguments"] == {"_invalid_arguments": "{not json}"}


def test_brain_api_key_in_header_not_body():
    body = {
        "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "ok"}}]
    }
    transport = _MockTransport(body)
    brain = OpenAICompatibleBrain(
        base_url="https://example.com/v1", api_key="sk-secret-key", model="m", transport=transport
    )
    brain.chat([ChatMessage(role="user", content="hi")], tools=[])
    # The API key must be in the Authorization header.
    assert transport.last_request.headers["Authorization"] == "Bearer sk-secret-key"
    # And must NOT appear in the request body.
    assert b"sk-secret-key" not in transport.last_request.content
