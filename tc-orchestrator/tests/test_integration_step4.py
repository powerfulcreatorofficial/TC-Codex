"""Step 4 HTTP end-to-end integration: real PostgreSQL + real Workspace Daemon.

Spins up a real postgres:16 container (via the pg_dsn fixture) and the real
daemon binary, then drives a full task through the HTTP API:

  POST /v1/tasks (L1 tool) -> AWAITING_APPROVAL (persisted in PG)
  GET  /pending_approval
  POST /approve
  -> orchestrator resumes -> real daemon executes -> COMPLETED
  GET  /v1/tasks/{id} (persisted across a fresh app/process)
  GET  /v1/tasks/{id}/events (PG history)

Uses a mock Brain for determinism. Skips if Docker or the daemon binary is
unavailable.
"""

from __future__ import annotations

import os
import socket
import subprocess
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tc_orchestrator.api import create_app
from tc_orchestrator.brain import MockBrain
from tc_orchestrator.db import Database
from tc_orchestrator.grpc_client import WorkspaceClient
from tc_orchestrator.migrations import reset_database
from tc_orchestrator.pg_task_store import PgTaskStore
from tests.conftest import settings_with_pg

OWNER = "x-tc-owner-token"
DAEMON_BIN = os.environ.get(
    "TC_DAEMON_BIN",
    str(Path(__file__).resolve().parents[2] / "backend-rust" / "target" / "release" / "tc-backend"),
)


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


@pytest.fixture(scope="module")
def daemon():
    if not Path(DAEMON_BIN).exists():
        pytest.skip("daemon binary not built")
    import tempfile

    workspace = Path(tempfile.mkdtemp(prefix="tc-step4-ws-"))
    (workspace / "README.md").write_text("# Engineering TC\n\nA test-case platform.\n")
    port = _free_port()
    addr = f"127.0.0.1:{port}"
    env = dict(os.environ)
    env["TC_WORKSPACE_ROOT"] = str(workspace)
    env["TC_DAEMON_ADDR"] = addr
    proc = subprocess.Popen([DAEMON_BIN], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    deadline = time.time() + 8
    ready = False
    while time.time() < deadline:
        if proc.poll() is not None:
            break
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.5)
            ready = True
            break
        except OSError:
            time.sleep(0.2)
    if not ready:
        proc.terminate()
        pytest.skip("daemon did not start")
    yield {"addr": addr, "workspace": workspace}
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def _tc(name, **a):
    return [{"id": "c1", "name": name, "arguments": a}]


def test_http_e2e_read_file_real_daemon_real_pg(pg_dsn, daemon):
    """L0 read_file completes without approval, persisted in real PG."""
    reset_database(pg_dsn)
    store = PgTaskStore(Database(pg_dsn))
    brain = MockBrain(
        script=[
            (_tc("read_file", path="README.md"), None, "tool_calls"),
            (None, "It is a test-case platform.", "stop"),
        ]
    )
    settings = settings_with_pg(pg_dsn, require_approval=True, daemon_addr=daemon["addr"])
    app = create_app(
        settings=settings, store=store, client=WorkspaceClient(daemon["addr"]), brain_override=brain
    )
    client = TestClient(app)

    resp = client.post("/v1/tasks", json={"prompt": "read README"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "COMPLETED"
    assert "test-case platform" in body["answer"].lower()
    task_id = body["task_id"]

    # Persisted: a brand-new store sees the task.
    store2 = PgTaskStore(Database(pg_dsn))
    assert store2.get(task_id) is not None
    assert store2.get(task_id).status.value == "COMPLETED"

    # Event history in PG.
    events = client.get(f"/v1/tasks/{task_id}/events").json()
    assert any(e["event_type"] == "task_completed" for e in events)


def test_http_e2e_approval_flow_real_daemon_real_pg(pg_dsn, daemon):
    """Full L1 approval flow over HTTP with real PG + real daemon.

    write_file -> AWAITING_APPROVAL -> approve -> resume -> COMPLETED,
    and the file is actually written through the real daemon.
    """
    reset_database(pg_dsn)
    store = PgTaskStore(Database(pg_dsn))
    brain = MockBrain(
        script=[
            (_tc("write_file", path="out.txt", content="hello-step4"), None, "tool_calls"),
            (None, "wrote the file successfully.", "stop"),
        ]
    )
    settings = settings_with_pg(pg_dsn, require_approval=True, daemon_addr=daemon["addr"])
    app = create_app(
        settings=settings, store=store, client=WorkspaceClient(daemon["addr"]), brain_override=brain
    )
    client = TestClient(app)

    # 1. Create task -> pauses for approval.
    resp = client.post("/v1/tasks", json={"prompt": "write out.txt"})
    assert resp.status_code == 200, resp.text
    task_id = resp.json()["task_id"]
    owner_token = resp.headers[OWNER]
    assert resp.json()["status"] == "AWAITING_APPROVAL"

    # Persisted as AWAITING_APPROVAL in PG.
    store2 = PgTaskStore(Database(pg_dsn))
    assert store2.get(task_id).status.value == "AWAITING_APPROVAL"

    # 2. View pending approval (owner only).
    pa = client.get(f"/v1/tasks/{task_id}/pending_approval", headers={OWNER: owner_token})
    assert pa.status_code == 200
    nonce = pa.json()["nonce"]
    assert pa.json()["tool_name"] == "write_file"

    # 3. Approve -> resume -> real daemon writes the file.
    approve = client.post(
        f"/v1/tasks/{task_id}/approve",
        json={"approved": True, "nonce": nonce, "decided_by": "alice"},
        headers={OWNER: owner_token},
    )
    assert approve.status_code == 200, approve.text
    assert approve.json()["status"] == "COMPLETED"

    # 4. The file was actually written through the real daemon.
    ws_client = WorkspaceClient(daemon["addr"])
    rd = ws_client.read_file("out.txt")
    assert rd.content == b"hello-step4"
    ws_client.close()

    # 5. PG history recorded the full lifecycle.
    events = client.get(f"/v1/tasks/{task_id}/events").json()
    types = [e["event_type"] for e in events]
    assert "approval_requested" in types
    assert "approval_decided" in types
    assert "task_completed" in types


def test_task_survives_app_restart_real_pg(pg_dsn, daemon):
    """TEST D: restart the application -> task remains available in PG."""
    reset_database(pg_dsn)
    store = PgTaskStore(Database(pg_dsn))
    brain = MockBrain(
        script=[
            (_tc("read_file", path="README.md"), None, "tool_calls"),
            (None, "done.", "stop"),
        ]
    )
    settings = settings_with_pg(pg_dsn, require_approval=True, daemon_addr=daemon["addr"])
    app1 = create_app(
        settings=settings, store=store, client=WorkspaceClient(daemon["addr"]), brain_override=brain
    )
    c1 = TestClient(app1)
    resp = c1.post("/v1/tasks", json={"prompt": "read README"})
    task_id = resp.json()["task_id"]
    assert resp.json()["status"] == "COMPLETED"

    # A completely new app instance with a new store reads the same task from PG.
    store2 = PgTaskStore(Database(pg_dsn))
    app2 = create_app(
        settings=settings,
        store=store2,
        client=WorkspaceClient(daemon["addr"]),
        brain_override=brain,
    )
    c2 = TestClient(app2)
    got = c2.get(f"/v1/tasks/{task_id}")
    assert got.status_code == 200
    assert got.json()["status"] == "COMPLETED"
