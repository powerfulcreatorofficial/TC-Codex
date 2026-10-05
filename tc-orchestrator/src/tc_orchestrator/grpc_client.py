"""gRPC client for the Workspace Daemon.

This is the only path through which the orchestrator touches the workspace.
It never uses ``open()``, ``pathlib`` writes, ``subprocess``, ``os.system()``,
etc. The daemon remains the security boundary.
"""

from __future__ import annotations

import grpc

from .proto_gen import daemon_pb2, daemon_pb2_grpc


class ReadFileResult:
    __slots__ = ("content", "sha256", "total_size", "truncated")

    def __init__(self, content: bytes, sha256: str, total_size: int, truncated: bool) -> None:
        self.content = content
        self.sha256 = sha256
        self.total_size = total_size
        self.truncated = truncated

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")


class WriteFileResult:
    __slots__ = ("sha256", "written")

    def __init__(self, sha256: str, written: bool) -> None:
        self.sha256 = sha256
        self.written = written


class ExecResult:
    __slots__ = ("exit_code", "status", "stdout", "stderr", "duration_ms")

    def __init__(
        self, exit_code: int, status: str, stdout: bytes, stderr: bytes, duration_ms: int
    ) -> None:
        self.exit_code = exit_code
        self.status = status
        self.stdout = stdout
        self.stderr = stderr
        self.duration_ms = duration_ms

    @property
    def stdout_text(self) -> str:
        return self.stdout.decode("utf-8", errors="replace")

    @property
    def stderr_text(self) -> str:
        return self.stderr.decode("utf-8", errors="replace")


class GitStatusResult:
    __slots__ = ("branch", "clean", "entries")

    def __init__(self, branch: str, clean: bool, entries: list[tuple[str, str]]) -> None:
        self.branch = branch
        self.clean = clean
        self.entries = entries  # list of (path, status)


class WorkspaceClient:
    """Thin gRPC client over the WorkspaceDaemon service."""

    def __init__(self, addr: str, timeout: float = 30.0) -> None:
        self._addr = addr
        self._timeout = timeout
        # A lazily-created channel; kept for reuse.
        self._channel: grpc.Channel | None = None
        self._stub: daemon_pb2_grpc.WorkspaceDaemonStub | None = None

    @property
    def addr(self) -> str:
        return self._addr

    def _ensure(self) -> daemon_pb2_grpc.WorkspaceDaemonStub:
        if self._stub is None:
            self._channel = grpc.insecure_channel(self._addr)
            self._stub = daemon_pb2_grpc.WorkspaceDaemonStub(self._channel)
        return self._stub

    def close(self) -> None:
        if self._channel is not None:
            self._channel.close()
            self._channel = None
            self._stub = None

    def __enter__(self) -> WorkspaceClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ---- API methods (match the daemon gRPC API) ----

    def read_file(self, path: str, offset: int = 0, length: int = 0) -> ReadFileResult:
        stub = self._ensure()
        resp = stub.ReadFile(
            daemon_pb2.ReadFileRequest(path=path, offset=offset, length=length),
            timeout=self._timeout,
        )
        return ReadFileResult(
            content=resp.content,
            sha256=resp.sha256,
            total_size=resp.total_size,
            truncated=resp.truncated,
        )

    def write_file(self, path: str, content: bytes, expected_hash: str) -> WriteFileResult:
        stub = self._ensure()
        resp = stub.WriteFile(
            daemon_pb2.WriteFileRequest(path=path, content=content, expected_hash=expected_hash),
            timeout=self._timeout,
        )
        return WriteFileResult(sha256=resp.sha256, written=resp.written)

    def exec_command(self, argv: list[str], timeout_seconds: int) -> ExecResult:
        stub = self._ensure()
        resp = stub.ExecCommand(
            daemon_pb2.ExecCommandRequest(argv=argv, timeout_seconds=timeout_seconds),
            timeout=self._timeout + timeout_seconds,
        )
        return ExecResult(
            exit_code=resp.exit_code,
            status=resp.status,
            stdout=resp.stdout,
            stderr=resp.stderr,
            duration_ms=resp.duration_ms,
        )

    def git_status(self) -> GitStatusResult:
        stub = self._ensure()
        resp = stub.GitStatus(daemon_pb2.GitStatusRequest(), timeout=self._timeout)
        entries = [(e.path, e.status) for e in resp.entries]
        return GitStatusResult(branch=resp.branch, clean=resp.clean, entries=entries)

    def git_create_branch(self, branch_name: str, from_head: bool = False) -> tuple[str, str]:
        stub = self._ensure()
        resp = stub.GitCreateBranch(
            daemon_pb2.GitCreateBranchRequest(branch_name=branch_name, from_head=from_head),
            timeout=self._timeout,
        )
        return resp.branch_name, resp.message

    def git_commit(self, message: str, paths: list[str] | None = None) -> tuple[str, str]:
        stub = self._ensure()
        resp = stub.GitCommit(
            daemon_pb2.GitCommitRequest(message=message, paths=paths or []),
            timeout=self._timeout,
        )
        return resp.commit_hash, resp.message
