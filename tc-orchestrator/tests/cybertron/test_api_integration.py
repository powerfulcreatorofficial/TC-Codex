"""Cybertron HTTP surface: task lifecycle, approval pause/resume, truthful
status propagation through the control plane."""

from __future__ import annotations

import json
import os
import time

import pytest
from fastapi.testclient import TestClient

from tc_orchestrator.api import create_app
from tc_orchestrator.config import Settings

from .conftest import init_git_repo


def make_settings(**over) -> Settings:
    base = dict(
        brain_base_url=None,  # no model => deterministic planning
        brain_api_key=None,
        brain_model="m",
        daemon_addr="127.0.0.1:1",
        max_agent_steps=5,
        host="127.0.0.1",
        port=8080,
        database_url=None,
        require_approval=False,
        approval_expiry_seconds=5,
    )
    base.update(over)
    return Settings(**base)


@pytest.fixture()
def repo_root(tmp_path):
    root = tmp_path / "workspaces"
    root.mkdir()
    project = root / "demo"
    (project / "src").mkdir(parents=True)
    (project / "src" / "app.py").write_text("def add(a, b):\n    return a + b\n")
    (project / "tests").mkdir()
    (project / "tests" / "test_app.py").write_text(
        "import sys, os\n"
        "sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))\n"
        "from app import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n"
    )
    init_git_repo(project)
    os.environ["CYBERTRON_WORKSPACE_ROOT"] = str(root)
    yield root
    del os.environ["CYBERTRON_WORKSPACE_ROOT"]


def wait_done(client: TestClient, task_id: str, timeout: float = 60.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = client.get(f"/v1/cybertron/tasks/{task_id}").json()
        if data["state"] in ("DONE", "ERROR"):
            return data
        time.sleep(0.1)
    raise AssertionError("cybertron task did not finish in time")


def test_status_endpoint(repo_root):
    app = create_app(settings=make_settings())
    c = TestClient(app)
    body = c.get("/v1/cybertron/status").json()
    assert body["subsystem"] == "cybertron"
    assert "VERIFY" in body["stages"]


def test_task_with_passing_verification(repo_root):
    app = create_app(settings=make_settings())
    c = TestClient(app)
    r = c.post("/v1/cybertron/tasks", json={
        "objective": "confirm the demo project tests pass",
        "workspace_path": "demo",
        "verification_commands": [["python3", "-m", "pytest", "-q", "tests"]],
    })
    assert r.status_code == 200, r.text
    data = wait_done(c, r.json()["task_id"])
    report = data
    # Deterministic plan (no model) + passing verification + clean review.
    assert report["status"] == "SUCCESS"
    assert report["verification"]["passed"] is True
    events = c.get(f"/v1/cybertron/tasks/{data['task_id']}/events").json()
    assert any(e["event_type"] == "verification_finished" for e in events)


def test_task_with_failing_verification_is_failed(repo_root):
    app = create_app(settings=make_settings())
    c = TestClient(app)
    r = c.post("/v1/cybertron/tasks", json={
        "objective": "this cannot pass",
        "workspace_path": "demo",
        "verification_commands": [["python3", "-c", "import sys; sys.exit(3)"]],
    })
    data = wait_done(c, r.json()["task_id"])
    assert data["status"] == "FAILED"
    checks = data["verification"]["checks"]
    assert checks[0]["exit_code"] == 3
    assert data["verification"]["passed"] is False


def test_workspace_escape_rejected(repo_root):
    app = create_app(settings=make_settings())
    c = TestClient(app)
    r = c.post("/v1/cybertron/tasks", json={
        "objective": "x", "workspace_path": "../../etc",
    })
    assert r.status_code == 400


def test_approval_pause_and_resume(repo_root, monkeypatch):
    """A plan with actions pauses for approval; an explicit HTTP approval
    resumes it; the result is verified honestly."""
    plan = json.dumps({
        "objective": "add note",
        "actions": [{"kind": "write_file", "path": "note.txt", "content": "hello\n"}],
        "verification_commands": [["python3", "-m", "pytest", "-q", "tests"]],
    })

    # Install a stub proposer so the plan has actions (triggering approval).
    import tc_orchestrator.cybertron_service as svc

    monkeypatch.setattr(
        svc, "proposer_from_settings", lambda settings: (lambda o, p, f: plan)
    )
    app = create_app(settings=make_settings(require_approval=True,
                                            approval_expiry_seconds=30))
    c = TestClient(app)
    r = c.post("/v1/cybertron/tasks", json={
        "objective": "add note", "workspace_path": "demo",
    })
    task_id = r.json()["task_id"]

    # Wait for the pending approval to appear.
    deadline = time.time() + 20
    pending = []
    while time.time() < deadline:
        pending = c.get("/v1/cybertron/approvals").json()
        if pending:
            break
        time.sleep(0.1)
    assert pending, "no approval was requested"
    assert pending[0]["task_id"] == task_id
    # The approver sees the real planned actions.
    assert pending[0]["detail"]["actions"][0]["path"] == "note.txt"

    ok = c.post(f"/v1/cybertron/approvals/{pending[0]['approval_id']}",
                json={"approved": True, "decided_by": "creator"})
    assert ok.status_code == 200
    data = wait_done(c, task_id)
    assert data["status"] == "SUCCESS"
    assert "note.txt" in data["changed_files"]


def test_approval_denied_blocks(repo_root, monkeypatch):
    plan = json.dumps({
        "objective": "add note",
        "actions": [{"kind": "write_file", "path": "note.txt", "content": "nope\n"}],
        "verification_commands": [["python3", "-m", "pytest", "-q", "tests"]],
    })
    import tc_orchestrator.cybertron_service as svc

    monkeypatch.setattr(
        svc, "proposer_from_settings", lambda settings: (lambda o, p, f: plan)
    )
    app = create_app(settings=make_settings(require_approval=True,
                                            approval_expiry_seconds=30))
    c = TestClient(app)
    r = c.post("/v1/cybertron/tasks", json={
        "objective": "add note", "workspace_path": "demo",
    })
    task_id = r.json()["task_id"]
    deadline = time.time() + 20
    pending = []
    while time.time() < deadline:
        pending = c.get("/v1/cybertron/approvals").json()
        if pending:
            break
        time.sleep(0.1)
    assert pending
    c.post(f"/v1/cybertron/approvals/{pending[0]['approval_id']}",
           json={"approved": False, "decided_by": "creator"})
    data = wait_done(c, task_id)
    assert data["status"] == "BLOCKED"
    assert "note.txt" not in data["changed_files"]
