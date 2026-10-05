"""TEST I — FastAPI API tests (Step 3 behavior; approval disabled)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tc_orchestrator.api import create_app
from tc_orchestrator.brain import MockBrain
from tc_orchestrator.config import Settings
from tc_orchestrator.grpc_client import WorkspaceClient
from tc_orchestrator.task_store import TaskStore


def _settings(**over) -> Settings:
    base = dict(
        brain_base_url="https://example.com/v1",
        brain_api_key=None,
        brain_model="m",
        daemon_addr="127.0.0.1:1",  # unreachable -> daemon: unreachable
        max_agent_steps=5,
        host="127.0.0.1",
        port=8080,
        database_url=None,
        require_approval=False,  # Step 3 behavior: no approval gating
        approval_expiry_seconds=300,
    )
    base.update(over)
    return Settings(**base)


def _make_client_with_files() -> WorkspaceClient:  # type: ignore[type-arg]
    from tests.conftest import FakeWorkspaceClient

    return FakeWorkspaceClient(  # type: ignore[return-value]
        files={"README.md": b"# Engineering TC\n\nA test-case engineering platform.\n"}
    )


def test_health_endpoint():
    app = create_app(
        settings=_settings(),
        store=TaskStore(),
        client=_make_client_with_files(),
        brain_override=None,
    )
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "daemon" in body


def test_post_task_and_get_task():
    brain = MockBrain(
        script=[
            (
                [{"id": "c1", "name": "read_file", "arguments": {"path": "README.md"}}],
                None,
                "tool_calls",
            ),
            (None, "The repo is an engineering test platform.", "stop"),
        ]
    )
    store = TaskStore()
    app = create_app(
        settings=_settings(),
        store=store,
        client=_make_client_with_files(),
        brain_override=brain,
    )
    client = TestClient(app)

    resp = client.post("/v1/tasks", json={"prompt": "Read README.md and summarize."})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "COMPLETED"
    assert body["answer"] is not None
    assert "engineering test platform" in body["answer"].lower()
    task_id = body["task_id"]

    resp2 = client.get(f"/v1/tasks/{task_id}")
    assert resp2.status_code == 200
    assert resp2.json()["task_id"] == task_id


def test_get_unknown_task_404():
    store = TaskStore()
    app = create_app(
        settings=_settings(),
        store=store,
        client=_make_client_with_files(),
        brain_override=MockBrain(script=[(None, "done", "stop")]),
    )
    client = TestClient(app)
    resp = client.get("/v1/tasks/does-not-exist")
    assert resp.status_code == 404


def test_list_tasks_returns_persisted_summaries_without_owner_tokens():
    brain = MockBrain(script=[(None, "done", "stop")])
    store = TaskStore()
    app = create_app(
        settings=_settings(),
        store=store,
        client=_make_client_with_files(),
        brain_override=brain,
    )
    client = TestClient(app)
    created = client.post("/v1/tasks", json={"prompt": "finish a task"})
    assert created.status_code == 200
    task_id = created.json()["task_id"]
    listed = client.get("/v1/tasks")
    assert listed.status_code == 200
    body = listed.json()
    assert any(task["task_id"] == task_id and task["status"] == "COMPLETED" for task in body)
    assert all("owner_token" not in task for task in body)


def test_list_tasks_supports_status_and_limit():
    brain = MockBrain(script=[(None, "done", "stop")])
    store = TaskStore()
    app = create_app(settings=_settings(), store=store, client=_make_client_with_files(), brain_override=brain)
    client = TestClient(app)
    for prompt in ("one", "two", "three"):
        assert client.post("/v1/tasks", json={"prompt": prompt}).status_code == 200
    listed = client.get("/v1/tasks?status=COMPLETED&limit=2")
    assert listed.status_code == 200
    assert len(listed.json()) == 2
    assert all(task["status"] == "COMPLETED" for task in listed.json())


def test_event_stream_emits_real_history_and_closes_on_terminal():
    brain = MockBrain(script=[(None, "done", "stop")])
    app = create_app(settings=_settings(), store=TaskStore(), client=_make_client_with_files(), brain_override=brain)
    client = TestClient(app)
    created = client.post("/v1/tasks", json={"prompt": "stream this"})
    task_id = created.json()["task_id"]
    with client.stream("GET", f"/v1/tasks/{task_id}/events/stream") as response:
        assert response.status_code == 200
        text = "".join(response.iter_text())
    assert "event_type" in text
    assert "task_started" in text
    assert "task_completed" in text
