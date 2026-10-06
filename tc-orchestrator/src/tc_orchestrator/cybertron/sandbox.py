"""Local process sandbox for Cybertron command execution.

What this layer genuinely provides on a plain Linux host:

- working directory confined to the task workspace
- a scrubbed environment (NO inherited host env; no secrets; HOME pointed at
  a throwaway directory inside the workspace so ``~/.ssh``/``~/.aws`` of the
  real user are never resolvable through ``~``)
- process-group execution with reliable whole-tree termination (SIGTERM then
  SIGKILL on the group)
- hard wall-clock timeout
- kernel resource limits (CPU seconds, address space, file size, processes)
- bounded stdout/stderr capture with explicit truncation flags
- truthful exit codes and status

What it does NOT provide — and never claims to: kernel-level filesystem or
network namespacing. ``SandboxResult.isolation`` reports exactly which
guarantees were active, and when ``network`` isolation is requested the
runner attempts ``unshare -rn`` (user+net namespace) and records honestly
whether that worked. A container-based runner is the designed extension
point (see ``SandboxRunner`` protocol).
"""

from __future__ import annotations

import os
import resource
import shutil
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

_OUTPUT_CAP_BYTES = 200_000

# Environment given to sandboxed commands. Nothing from the parent process
# environment is inherited; secrets live only in the control plane.
_BASE_ENV_KEYS = ("PATH",)


@dataclass(frozen=True)
class SandboxLimits:
    timeout_seconds: float = 120.0
    cpu_seconds: int = 300
    memory_bytes: int = 2 * 1024 * 1024 * 1024  # 2 GiB address space
    file_size_bytes: int = 256 * 1024 * 1024
    max_processes: int = 256
    max_output_bytes: int = _OUTPUT_CAP_BYTES
    network: bool = False  # network OFF by default


@dataclass(frozen=True)
class SandboxResult:
    argv: tuple[str, ...]
    status: str  # "completed" | "timeout" | "error"
    exit_code: int | None
    stdout: str
    stderr: str
    duration_ms: int
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    error: str | None = None
    # Honest description of which isolation guarantees were actually active.
    isolation: dict[str, bool | str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        """True only for a completed run with exit code 0. Never anything else."""
        return self.status == "completed" and self.exit_code == 0


class SandboxRunner(Protocol):
    """Extension point: container-based runners implement the same contract."""

    def run(self, argv: list[str], *, cwd: str, limits: SandboxLimits) -> SandboxResult: ...


def _cap_bytes(data: bytes, limit: int) -> tuple[str, bool]:
    truncated = len(data) > limit
    if truncated:
        data = data[:limit]
    return data.decode("utf-8", errors="replace"), truncated


def _unshare_net_available() -> bool:
    exe = shutil.which("unshare")
    if not exe:
        return False
    try:
        probe = subprocess.run(
            [exe, "-rn", "true"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        return probe.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


class LocalProcessSandbox:
    """Runs commands confined to a workspace directory with hard bounds."""

    def __init__(self, workspace_root: str | os.PathLike[str]) -> None:
        self._root = Path(os.path.realpath(workspace_root))
        if not self._root.is_dir():
            raise ValueError(f"sandbox workspace root is not a directory: {workspace_root}")
        self._unshare_net = _unshare_net_available()

    @property
    def root(self) -> Path:
        return self._root

    def _build_env(self, home_dir: str) -> dict[str, str]:
        env: dict[str, str] = {}
        for key in _BASE_ENV_KEYS:
            val = os.environ.get(key)
            if val:
                env[key] = val
        env.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin")
        env["HOME"] = home_dir
        env["TMPDIR"] = home_dir
        env["LANG"] = "C.UTF-8"
        env["LC_ALL"] = "C.UTF-8"
        # Git hardening defaults for anything that shells out to git.
        env["GIT_CONFIG_GLOBAL"] = "/dev/null"
        env["GIT_CONFIG_SYSTEM"] = "/dev/null"
        env["GIT_TERMINAL_PROMPT"] = "0"
        # Make Python output deterministic and unbuffered inside the sandbox.
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONUNBUFFERED"] = "1"
        return env

    def run(
        self,
        argv: list[str],
        *,
        cwd: str | None = None,
        limits: SandboxLimits | None = None,
    ) -> SandboxResult:
        limits = limits or SandboxLimits()
        if not argv or not all(isinstance(a, str) for a in argv):
            return SandboxResult(
                argv=tuple(argv or ()),
                status="error",
                exit_code=None,
                stdout="",
                stderr="",
                duration_ms=0,
                error="argv must be a non-empty list of strings",
            )

        workdir = self._root
        if cwd:
            candidate = Path(os.path.realpath(self._root / cwd))
            if candidate != self._root and self._root not in candidate.parents:
                return SandboxResult(
                    argv=tuple(argv),
                    status="error",
                    exit_code=None,
                    stdout="",
                    stderr="",
                    duration_ms=0,
                    error=f"cwd escapes the workspace root: {cwd}",
                )
            workdir = candidate

        real_argv = list(argv)
        network_isolated = False
        if not limits.network and self._unshare_net:
            real_argv = ["unshare", "-rn", *real_argv]
            network_isolated = True

        isolation: dict[str, bool | str] = {
            "workspace_confined_cwd": True,
            "env_scrubbed": True,
            "process_group_kill": True,
            "rlimits": True,
            "network_isolated": network_isolated,
            "filesystem_namespaced": False,  # honest: no mount namespace here
            "runner": "local-process",
        }

        home_dir = tempfile.mkdtemp(prefix=".tc-sandbox-home-", dir=self._root)
        env = self._build_env(home_dir)

        def _preexec() -> None:  # runs in the child before exec
            os.setsid()
            resource.setrlimit(resource.RLIMIT_CPU, (limits.cpu_seconds, limits.cpu_seconds))
            resource.setrlimit(resource.RLIMIT_AS, (limits.memory_bytes, limits.memory_bytes))
            resource.setrlimit(
                resource.RLIMIT_FSIZE, (limits.file_size_bytes, limits.file_size_bytes)
            )
            try:
                resource.setrlimit(
                    resource.RLIMIT_NPROC, (limits.max_processes, limits.max_processes)
                )
            except (ValueError, OSError):
                pass  # may be lower than current usage on busy hosts

        start = time.monotonic()
        try:
            proc = subprocess.Popen(
                real_argv,
                cwd=str(workdir),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                preexec_fn=_preexec,  # noqa: PLW1509 - deliberate, single-threaded child setup
                close_fds=True,
            )
        except FileNotFoundError as exc:
            shutil.rmtree(home_dir, ignore_errors=True)
            return SandboxResult(
                argv=tuple(argv),
                status="error",
                exit_code=None,
                stdout="",
                stderr="",
                duration_ms=int((time.monotonic() - start) * 1000),
                error=f"executable not found: {exc}",
                isolation=isolation,
            )
        except OSError as exc:
            shutil.rmtree(home_dir, ignore_errors=True)
            return SandboxResult(
                argv=tuple(argv),
                status="error",
                exit_code=None,
                stdout="",
                stderr="",
                duration_ms=int((time.monotonic() - start) * 1000),
                error=f"spawn failed: {exc}",
                isolation=isolation,
            )

        timed_out = False
        try:
            stdout_b, stderr_b = proc.communicate(timeout=limits.timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            self._kill_group(proc)
            try:
                stdout_b, stderr_b = proc.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                stdout_b, stderr_b = b"", b""
        finally:
            shutil.rmtree(home_dir, ignore_errors=True)

        duration_ms = int((time.monotonic() - start) * 1000)
        stdout, t_out = _cap_bytes(stdout_b or b"", limits.max_output_bytes)
        stderr, t_err = _cap_bytes(stderr_b or b"", limits.max_output_bytes)

        if timed_out:
            return SandboxResult(
                argv=tuple(argv),
                status="timeout",
                exit_code=None,
                stdout=stdout,
                stderr=stderr,
                duration_ms=duration_ms,
                stdout_truncated=t_out,
                stderr_truncated=t_err,
                error=f"timed out after {limits.timeout_seconds}s; process tree terminated",
                isolation=isolation,
            )
        return SandboxResult(
            argv=tuple(argv),
            status="completed",
            exit_code=proc.returncode,
            stdout=stdout,
            stderr=stderr,
            duration_ms=duration_ms,
            stdout_truncated=t_out,
            stderr_truncated=t_err,
            error=None if proc.returncode == 0 else f"exit code {proc.returncode}",
            isolation=isolation,
        )

    @staticmethod
    def _kill_group(proc: subprocess.Popen) -> None:
        """Terminate the entire process group: SIGTERM, grace, then SIGKILL."""
        try:
            pgid = os.getpgid(proc.pid)
        except ProcessLookupError:
            return
        try:
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            return
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                break
            time.sleep(0.05)
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
