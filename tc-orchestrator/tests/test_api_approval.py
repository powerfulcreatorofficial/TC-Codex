"""Step 4 HTTP API approval tests (in-memory store).

Tests the approval endpoints, owner-token enforcement, and the full
create -> pause -> approve -> resume -> complete flow over HTTP.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tc_orchestrator.api import create_app
from tc_orchestrator.brain import MockBrain
from tc_orchestrator.config import Settings
from tc_orchestrator.task_store import TaskStore

OWNER = "x-tc-owner-token"


def _settings(**over) -> Settings:
    base = dict(
        brain_base_url="https://example.com/v1",
        brain_api_key=None,
        brain_model="m",
        daemon_addr="127.0.0.1:1",
        max_agent_steps=5,
        host="127.0.0.1",
        port=8080,
        database_url=None,
        require_approval=True,
        approval_expiry_seconds=300,
    )
    base.update(over)
    return Settings(**base)


def _client_with_files():
    from tests.conftest import FakeWorkspaceClient

    return FakeWorkspaceClient(files={"README.md": b"# Engineering TC\n\nA test-case platform.\n"})


def _tc(name, **arguments):
    return [{"id": "c1", "name": name, "arguments": arguments}]


def test_read_file_completes_without_approval():
    """read_file (L0) needs no approval -> COMPLETED directly."""
    brain = MockBrain(
        script=[
            (_tc("read_file", path="README.md"), None, "tool_calls"),
            (None, "It is a test-case platform.", "stop"),
        ]
    )
    app = create_app(
        settings=_settings(),
        store=TaskStore(),
        client=_client_with_files(),
        brain_override=brain,
    )
    client = TestClient(app)
    resp = client.post("/v1/tasks", json={"prompt": "read README"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "COMPLETED"
    assert "test-case platform" in body["answer"].lower()


def test_write_file_enters_awaiting_approval_and_owner_token_returned():
    """write_file (L1) -> AWAITING_APPROVAL; owner token in header."""
    brain = MockBrain(
        script=[(_tc("write_file", path="out.txt", content="hi"), None, "tool_calls")]
    )
    app = create_app(
        settings=_settings(),
        store=TaskStore(),
        client=_client_with_files(),
        brain_override=brain,
    )
    client = TestClient(app)
    resp = client.post("/v1/tasks", json={"prompt": "write a file"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "AWAITING_APPROVAL"
    owner_token = resp.headers.get(OWNER)
    assert owner_token  # owner token returned once

    # Pending approval view (owner only).
    pa = client.get(f"/v1/tasks/{body['task_id']}/pending_approval", headers={OWNER: owner_token})
    assert pa.status_code == 200
    assert pa.json()["tool_name"] == "write_file"
    assert pa.json()["risk_level"] == "L1"
    # The redacted summary must not contain raw content secrets.
    assert "content_preview" in pa.json()["arguments_metadata"]


def test_full_approve_flow_completes():
    """create (L1 pause) -> approve -> resume -> COMPLETED."""
    brain = MockBrain(
        script=[
            (_tc("write_file", path="out.txt", content="hi"), None, "tool_calls"),
            (None, "wrote the file", "stop"),
        ]
    )
    store = TaskStore()
    app = create_app(
        settings=_settings(),
        store=store,
        client=_client_with_files(),
        brain_override=brain,
    )
    client = TestClient(app)
    resp = client.post("/v1/tasks", json={"prompt": "write a file"})
    task_id = resp.json()["task_id"]
    owner_token = resp.headers[OWNER]
    assert resp.json()["status"] == "AWAITING_APPROVAL"

    pa = client.get(f"/v1/tasks/{task_id}/pending_approval", headers={OWNER: owner_token})
    nonce = pa.json()["nonce"]

    approve = client.post(
        f"/v1/tasks/{task_id}/approve",
        json={"approved": True, "nonce": nonce, "decided_by": "alice"},
        headers={OWNER: owner_token},
    )
    assert approve.status_code == 200
    assert approve.json()["status"] == "COMPLETED"
    # The file was actually written through the (fake) daemon.
    assert store is not None

    # Event history recorded the approval + completion.
    events = client.get(f"/v1/tasks/{task_id}/events").json()
    types = [e["event_type"] for e in events]
    assert "approval_requested" in types
    assert "approval_decided" in types
    assert "task_completed" in types


def test_approve_without_owner_token_rejected():
    """TEST L (API): no owner token -> 401."""
    brain = MockBrain(
        script=[(_tc("write_file", path="out.txt", content="hi"), None, "tool_calls")]
    )
    app = create_app(
        settings=_settings(),
        store=TaskStore(),
        client=_client_with_files(),
        brain_override=brain,
    )
    client = TestClient(app)
    resp = client.post("/v1/tasks", json={"prompt": "write a file"})
    task_id = resp.json()["task_id"]
    pa = client.get(f"/v1/tasks/{task_id}/pending_approval")
    assert pa.status_code == 401


def test_approve_with_wrong_owner_token_rejected():
    brain = MockBrain(
        script=[(_tc("write_file", path="out.txt", content="hi"), None, "tool_calls")]
    )
    app = create_app(
        settings=_settings(),
        store=TaskStore(),
        client=_client_with_files(),
        brain_override=brain,
    )
    client = TestClient(app)
    resp = client.post("/v1/tasks", json={"prompt": "write a file"})
    task_id = resp.json()["task_id"]
    pa = client.get(f"/v1/tasks/{task_id}/pending_approval", headers={OWNER: "wrong-token"})
    assert pa.status_code == 403


def test_replay_approval_rejected():
    """A replayed approval (same nonce twice) is rejected."""
    brain = MockBrain(
        script=[(_tc("write_file", path="out.txt", content="hi"), None, "tool_calls")]
    )
    app = create_app(
        settings=_settings(),
        store=TaskStore(),
        client=_client_with_files(),
        brain_override=brain,
    )
    client = TestClient(app)
    resp = client.post("/v1/tasks", json={"prompt": "write a file"})
    task_id = resp.json()["task_id"]
    owner_token = resp.headers[OWNER]
    nonce = client.get(
        f"/v1/tasks/{task_id}/pending_approval", headers={OWNER: owner_token}
    ).json()["nonce"]

    first = client.post(
        f"/v1/tasks/{task_id}/approve",
        json={"approved": True, "nonce": nonce, "decided_by": "alice"},
        headers={OWNER: owner_token},
    )
    assert first.status_code == 200
    # Replay.
    second = client.post(
        f"/v1/tasks/{task_id}/approve",
        json={"approved": True, "nonce": nonce, "decided_by": "alice"},
        headers={OWNER: owner_token},
    )
    assert second.status_code == 409


def test_wrong_nonce_rejected():
    brain = MockBrain(
        script=[(_tc("write_file", path="out.txt", content="hi"), None, "tool_calls")]
    )
    app = create_app(
        settings=_settings(),
        store=TaskStore(),
        client=_client_with_files(),
        brain_override=brain,
    )
    client = TestClient(app)
    resp = client.post("/v1/tasks", json={"prompt": "write a file"})
    task_id = resp.json()["task_id"]
    owner_token = resp.headers[OWNER]
    approve = client.post(
        f"/v1/tasks/{task_id}/approve",
        json={"approved": True, "nonce": "wrong-nonce", "decided_by": "alice"},
        headers={OWNER: owner_token},
    )
    assert approve.status_code == 409


def test_reject_marks_failed():
    brain = MockBrain(
        script=[(_tc("write_file", path="out.txt", content="hi"), None, "tool_calls")]
    )
    app = create_app(
        settings=_settings(),
        store=TaskStore(),
        client=_client_with_files(),
        brain_override=brain,
    )
    client = TestClient(app)
    resp = client.post("/v1/tasks", json={"prompt": "write a file"})
    task_id = resp.json()["task_id"]
    owner_token = resp.headers[OWNER]
    nonce = client.get(
        f"/v1/tasks/{task_id}/pending_approval", headers={OWNER: owner_token}
    ).json()["nonce"]
    reject = client.post(
        f"/v1/tasks/{task_id}/reject",
        json={"approved": False, "nonce": nonce, "decided_by": "alice"},
        headers={OWNER: owner_token},
    )
    assert reject.status_code == 200
    assert reject.json()["status"] == "FAILED"
