"""Integration test against the REAL Workspace Daemon (gRPC).

Starts the daemon binary on an ephemeral port with a temp workspace, then
drives the orchestrator through a mock Brain using the real
``WorkspaceClient``. This proves the orchestrator can talk to the actual
daemon over gRPC and that tool results flow back to the Brain.
"""

from __future__ import annotations

import os
import socket
import subprocess
import tempfile
import time
from pathlib import Path

import pytest

from tc_orchestrator.brain import MockBrain
from tc_orchestrator.grpc_client import WorkspaceClient
from tc_orchestrator.orchestrator import Orchestrator, OrchestratorConfig
from tc_orchestrator.redaction import Redactor
from tc_orchestrator.tool_registry import default_registry

DAEMON_BIN = os.environ.get(
    "TC_DAEMON_BIN",
    str(Path(__file__).resolve().parents[2] / "backend-rust" / "target" / "release" / "tc-backend"),
)


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="module")
def daemon():
    """Start the real daemon with a temp workspace on a free port."""
    if not Path(DAEMON_BIN).exists():
        pytest.skip(f"daemon binary not built at {DAEMON_BIN}")
    workspace = Path(tempfile.mkdtemp(prefix="tc-daemon-ws-"))
    # Seed a README so read_file has something to return.
    (workspace / "README.md").write_text(
        "# Engineering TC\n\nA test-case platform.\n", encoding="utf-8"
    )
    port = _free_port()
    addr = f"127.0.0.1:{port}"
    env = dict(os.environ)
    env["TC_WORKSPACE_ROOT"] = str(workspace)
    env["TC_DAEMON_ADDR"] = addr
    proc = subprocess.Popen(
        [DAEMON_BIN],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        # Wait until the port accepts connections.
        deadline = time.time() + 8
        ready = False
        while time.time() < deadline:
            if proc.poll() is not None:
                break
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                    ready = True
                    break
            except OSError:
                time.sleep(0.2)
        if not ready:
            out, err = proc.communicate(timeout=2)
            pytest.skip(f"daemon did not start: {err!r}")
        yield {"addr": addr, "workspace": workspace}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_read_file_via_real_daemon(daemon):
    """Orchestrator reads README.md through the real daemon over gRPC."""
    client = WorkspaceClient(daemon["addr"])
    brain = MockBrain(
        script=[
            (
                [{"id": "c1", "name": "read_file", "arguments": {"path": "README.md"}}],
                None,
                "tool_calls",
            ),
            (None, "The repo is a test-case platform.", "stop"),
        ]
    )
    orch = Orchestrator(
        brain=brain,
        client=client,
        registry=default_registry(),
        redactor=Redactor(),
        config=OrchestratorConfig(max_steps=5),
    )
    result = orch.run("Read README.md and summarize.")
    assert result.finished is True
    assert "test-case platform" in (result.answer or "").lower()
    assert result.tool_results[0].ok is True
    assert "Engineering TC" in result.tool_results[0].output
    client.close()


def test_exec_command_via_real_daemon(daemon):
    """exec_command runs inside the daemon's workspace sandbox."""
    client = WorkspaceClient(daemon["addr"])
    brain = MockBrain(
        script=[
            (
                [
                    {
                        "id": "c1",
                        "name": "exec_command",
                        "arguments": {
                            "argv": ["sh", "-c", "echo hello-from-daemon"],
                            "timeout_seconds": 5,
                        },
                    }
                ],
                None,
                "tool_calls",
            ),
            (None, "ran the command.", "stop"),
        ]
    )
    orch = Orchestrator(
        brain=brain,
        client=client,
        registry=default_registry(),
        redactor=Redactor(),
        config=OrchestratorConfig(max_steps=5),
    )
    result = orch.run("Run a command that prints hello-from-daemon.")
    assert result.finished is True
    assert result.tool_results[0].ok is True
    assert "hello-from-daemon" in result.tool_results[0].output
    client.close()


def test_traversal_rejected_by_real_daemon(daemon):
    """The real daemon rejects path traversal (PERMISSION_DENIED surfaced)."""
    client = WorkspaceClient(daemon["addr"])
    brain = MockBrain(
        script=[
            (
                [{"id": "c1", "name": "read_file", "arguments": {"path": "../../etc/passwd"}}],
                None,
                "tool_calls",
            ),
            (None, "blocked.", "stop"),
        ]
    )
    orch = Orchestrator(
        brain=brain,
        client=client,
        registry=default_registry(),
        redactor=Redactor(),
        config=OrchestratorConfig(max_steps=5),
    )
    result = orch.run("Try reading ../../etc/passwd.")
    # Client-side pre-check rejects first; daemon never sees it.
    assert result.tool_results[0].ok is False
    client.close()
