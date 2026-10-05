from fastapi.testclient import TestClient

from tc_orchestrator.api import create_app
from tc_orchestrator.config import Settings
from tc_orchestrator.task_store import TaskStore


def settings():
    return Settings(
        brain_base_url="https://example.com/v1", brain_api_key=None, brain_model="m",
        daemon_addr="127.0.0.1:1", max_agent_steps=5, host="127.0.0.1", port=8080,
        database_url=None, require_approval=True, approval_expiry_seconds=300,
    )


def test_project_crud_and_task_association():
    store=TaskStore()
    client=TestClient(create_app(settings=settings(), store=store, client=__import__("tests.conftest", fromlist=["FakeWorkspaceClient"]).FakeWorkspaceClient()))
    created=client.post("/v1/projects", json={"name":"tc-app","description":"test app","workspace_path":"tc-app"})
    assert created.status_code == 200
    project=created.json()
    assert project["task_count"] == 0
    got=client.get(f"/v1/projects/{project['id']}")
    assert got.status_code == 200
    assert got.json()["name"] == "tc-app"
    updated=client.patch(f"/v1/projects/{project['id']}", json={"description":"updated"})
    assert updated.status_code == 200
    assert updated.json()["description"] == "updated"
    duplicate=client.post("/v1/projects", json={"name":"tc-app","description":"","workspace_path":"other"})
    assert duplicate.status_code == 409


def test_task_unknown_project_rejected():
    store=TaskStore()
    client=TestClient(create_app(settings=settings(), store=store, client=__import__("tests.conftest", fromlist=["FakeWorkspaceClient"]).FakeWorkspaceClient()))
    resp=client.post("/v1/tasks", json={"prompt":"hello","project_id":"missing"})
    assert resp.status_code == 404


def test_project_context_includes_recent_tasks_and_learnings():
    from tc_orchestrator.models import TaskStatus
    from tc_orchestrator.learning import Learning

    store = TaskStore()
    client = TestClient(create_app(settings=settings(), store=store, client=__import__("tests.conftest", fromlist=["FakeWorkspaceClient"]).FakeWorkspaceClient()))
    created = client.post(
        "/v1/projects",
        json={"name": "tc-context", "description": "context project", "workspace_path": "tc-context"},
    )
    assert created.status_code == 200
    project = created.json()

    task, _ = store.create("Implement a context-aware feature", max_steps=5, project_id=project["id"])
    store.update(task.task_id, status=TaskStatus.RUNNING, steps=2)
    store.add_event(task.task_id, "task_started", status=TaskStatus.RUNNING.value)
    store.add_learning(
        task.task_id,
        Learning(
            category="verification",
            lesson="Verify observable test evidence before claiming completion.",
            evidence=f"task={task.task_id}",
            score=90,
        ),
    )

    response = client.get(f"/v1/projects/{project['id']}/context")
    assert response.status_code == 200
    body = response.json()
    assert body["total_tasks"] == 1
    assert body["active_tasks"] == 1
    assert body["recent_tasks"][0]["task_id"] == task.task_id
    assert body["recent_learnings"][0]["category"] == "verification"
    assert "Implement a context-aware feature" in body["context_text"]
    assert "Verify observable test evidence" in body["context_text"]


def test_project_context_unknown_project_is_404():
    store = TaskStore()
    client = TestClient(create_app(settings=settings(), store=store, client=__import__("tests.conftest", fromlist=["FakeWorkspaceClient"]).FakeWorkspaceClient()))
    response = client.get("/v1/projects/missing/context")
    assert response.status_code == 404
