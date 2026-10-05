"""Shared test fixtures and a fake WorkspaceClient.

The fake client lets us exercise the registry/router/orchestrator without a
running gRPC daemon. It implements the same surface as ``WorkspaceClient``.
"""

from __future__ import annotations

import hashlib
import socket
import subprocess
import time

import pytest

from tc_orchestrator.grpc_client import (
    ExecResult,
    GitStatusResult,
    ReadFileResult,
    WriteFileResult,
)


class FakeWorkspaceClient:
    """In-memory stand-in for the gRPC WorkspaceClient."""

    def __init__(self, files: dict[str, bytes] | None = None) -> None:
        self.files: dict[str, bytes] = dict(files or {})
        # Captured exec calls for assertions.
        self.exec_calls: list[tuple[list[str], int]] = []
        self.exec_side_effect: list[ExecResult] | None = None
        # If set, exec raises this once then falls back.
        self.exec_throw: Exception | None = None

    # -- API surface --
    def read_file(self, path: str, offset: int = 0, length: int = 0) -> ReadFileResult:
        if path not in self.files:
            raise FileNotFoundError(path)
        data = self.files[path]
        start = min(offset, len(data))
        end = len(data) if length == 0 else min(start + length, len(data))
        return ReadFileResult(
            content=data[start:end],
            sha256=hashlib.sha256(data).hexdigest(),
            total_size=len(data),
            truncated=(start != 0 or end != len(data)),
        )

    def write_file(self, path: str, content: bytes, expected_hash: str) -> WriteFileResult:
        current = self.files.get(path, b"")
        current_hash = hashlib.sha256(current).hexdigest()
        if current_hash != expected_hash:
            # Mirror the daemon: refuse (signal via written=False).
            return WriteFileResult(sha256=current_hash, written=False)
        self.files[path] = content
        return WriteFileResult(sha256=hashlib.sha256(content).hexdigest(), written=True)

    def exec_command(self, argv: list[str], timeout_seconds: int) -> ExecResult:
        self.exec_calls.append((list(argv), timeout_seconds))
        if self.exec_side_effect:
            return self.exec_side_effect.pop(0)
        if self.exec_throw is not None:
            exc, self.exec_throw = self.exec_throw, None
            raise exc
        return ExecResult(
            exit_code=0,
            status="completed",
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
        )

    def git_status(self) -> GitStatusResult:
        return GitStatusResult(branch="main", clean=True, entries=[])


@pytest.fixture()
def fake_client() -> FakeWorkspaceClient:
    return FakeWorkspaceClient()


@pytest.fixture()
def fake_client_with_files() -> FakeWorkspaceClient:
    return FakeWorkspaceClient(
        files={
            "README.md": b"# Engineering TC\n\nA test-case engineering platform.\n",
            "sub/file.txt": b"nested",
        }
    )


@pytest.fixture()
def redactor_secrets() -> dict[str, str]:
    """A fixed set of fake secrets for redaction tests."""
    return {
        "openrouter": "sk-or-v1-TESTSECRET123",
        "github": "ghp_TESTSECRET123abc",
        "telegram": "123456789:AA_TEST_TELEGRAM_TOKEN",
    }


# ---------------------------------------------------------------------------
# Step 4: real PostgreSQL fixture (ephemeral docker container)
# ---------------------------------------------------------------------------


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _docker_run(args: list[str], *, capture: bool = True, check: bool = False):
    """Run a docker command, wrapping with `sg docker -c` if needed.

    `sg` requires the command as a single shell string, so when the plain
    `docker` socket is not accessible we shell out via `sg docker -c '<cmd>'`.
    """
    import shlex

    # Try plain docker first.
    try:
        r = subprocess.run(["docker", "info"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if r.returncode == 0:
            return subprocess.run(
                ["docker", *args],
                capture_output=capture,
                text=True,
                check=check,
            )
    except FileNotFoundError:
        pass
    # Fall back to sg docker -c '<joined>'.
    shell_cmd = "docker " + " ".join(shlex.quote(a) for a in args)
    return subprocess.run(
        ["sg", "docker", "-c", shell_cmd],
        capture_output=capture,
        text=True,
        check=check,
    )


def _docker_available() -> bool:
    try:
        r = _docker_run(["info"])
        return r.returncode == 0
    except FileNotFoundError:
        return False


@pytest.fixture(scope="session")
def pg_dsn():
    """Start an ephemeral postgres:16-alpine container and yield a DSN.

    Uses a random host port (test-only; does NOT touch the Step 1 compose).
    Skips if Docker is unavailable so unit tests still run.
    """
    if not _docker_available():
        pytest.skip("docker unavailable; real PostgreSQL integration skipped")

    import secrets as _secrets

    pg_user, pg_password, pg_db = "tc", "tctestpass", "tc"
    port = _free_port()
    container_name = f"tc-test-pg-{_secrets.token_hex(4)}"

    proc = _docker_run(
        [
            "run",
            "-d",
            "--name",
            container_name,
            "-e",
            f"POSTGRES_USER={pg_user}",
            "-e",
            f"POSTGRES_PASSWORD={pg_password}",
            "-e",
            f"POSTGRES_DB={pg_db}",
            "-p",
            f"{port}:5432",
            "postgres:16-alpine",
        ]
    )
    if proc.returncode != 0:
        pytest.skip(f"could not start postgres container: {proc.stderr.strip()}")
    container_id = proc.stdout.strip()

    dsn = f"postgresql://{pg_user}:{pg_password}@127.0.0.1:{port}/{pg_db}"
    import psycopg

    deadline = time.time() + 30
    ready = False
    while time.time() < deadline:
        try:
            with psycopg.connect(dsn, connect_timeout=2):
                ready = True
                break
        except psycopg.OperationalError:
            time.sleep(0.5)
    if not ready:
        _docker_run(["rm", "-f", container_id])
        pytest.skip("postgres container did not become ready")

    yield dsn
    _docker_run(["rm", "-f", container_id])


@pytest.fixture()
def pg_store(pg_dsn):
    """A fresh PgTaskStore with a reset schema per test."""
    from tc_orchestrator.db import Database
    from tc_orchestrator.migrations import reset_database
    from tc_orchestrator.pg_task_store import PgTaskStore

    reset_database(pg_dsn)
    yield PgTaskStore(Database(pg_dsn))


def settings_with_pg(pg_dsn, **over):
    """Build Settings pointed at a real DB, approval enabled by default."""
    from tc_orchestrator.config import Settings

    base = dict(
        brain_base_url="https://example.com/v1",
        brain_api_key=None,
        brain_model="m",
        daemon_addr="127.0.0.1:1",
        max_agent_steps=5,
        host="127.0.0.1",
        port=8080,
        database_url=pg_dsn,
        require_approval=True,
        approval_expiry_seconds=300,
    )
    base.update(over)
    return Settings(**base)
