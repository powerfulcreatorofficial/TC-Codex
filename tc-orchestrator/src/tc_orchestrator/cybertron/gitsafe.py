"""Hardened Git operations for Cybertron.

Threats addressed:
- malicious repository config (``core.fsmonitor``, ``core.pager``, aliases,
  ``core.hooksPath``) → every invocation force-overrides dangerous keys and
  ignores global/system config entirely
- hooks → ``core.hooksPath`` is pointed at an empty directory for every call
- argument/path injection → paths are always passed after a literal ``--``
  and may never begin with ``-``
- credential/prompt leaks → prompts disabled, env scrubbed by the sandbox

Write operations (commit, branch) are exposed but classified L5 by the tool
layer, so they always require policy approval upstream.
"""

from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .sandbox import LocalProcessSandbox, SandboxLimits, SandboxResult

_SAFE_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/\-]{0,200}$")

# Config force-set on EVERY git invocation (repo config cannot override -c).
_HARDENING_EMPTY_HOOKS: Path | None = None


def _empty_hooks_dir() -> str:
    global _HARDENING_EMPTY_HOOKS
    if _HARDENING_EMPTY_HOOKS is None or not _HARDENING_EMPTY_HOOKS.is_dir():
        _HARDENING_EMPTY_HOOKS = Path(tempfile.mkdtemp(prefix="tc-git-nohooks-"))
    return str(_HARDENING_EMPTY_HOOKS)


def _hardening_args() -> list[str]:
    return [
        "--no-pager",
        "-c", f"core.hooksPath={_empty_hooks_dir()}",
        "-c", "core.fsmonitor=false",
        "-c", "core.pager=cat",
        "-c", "core.editor=false",
        "-c", "credential.helper=",
        "-c", "protocol.file.allow=never",
        "-c", "protocol.ext.allow=never",
        "-c", "uploadpack.allowAnySHA1InWant=false",
        "-c", "user.name=TC Cybertron",
        "-c", "user.email=cybertron@tc.local",
    ]


class GitSafetyError(Exception):
    """Raised when an unsafe git argument is rejected."""


def _check_paths(paths: list[str]) -> list[str]:
    for p in paths:
        if not p or p.startswith("-"):
            raise GitSafetyError(f"unsafe git path argument rejected: {p!r}")
        if p.startswith("/") or p.startswith("~"):
            raise GitSafetyError(f"absolute git path rejected: {p!r}")
        if ".." in Path(p).parts:
            raise GitSafetyError(f"traversal in git path rejected: {p!r}")
    return paths


def _check_ref(name: str) -> str:
    if not _SAFE_REF_RE.match(name) or ".." in name or name.endswith(".lock"):
        raise GitSafetyError(f"unsafe git ref name rejected: {name!r}")
    return name


@dataclass(frozen=True)
class GitFileStatus:
    path: str
    status: str


@dataclass(frozen=True)
class GitState:
    branch: str | None
    clean: bool
    entries: tuple[GitFileStatus, ...]
    is_repo: bool


class SafeGit:
    """All git access for a Cybertron task workspace goes through here."""

    def __init__(self, sandbox: LocalProcessSandbox) -> None:
        self._sandbox = sandbox

    def _run(self, args: list[str], *, timeout: float = 30.0) -> SandboxResult:
        argv = ["git", *_hardening_args(), *args]
        return self._sandbox.run(
            argv, limits=SandboxLimits(timeout_seconds=timeout, network=False)
        )

    # ---- read-only ----

    def state(self) -> GitState:
        res = self._run(["status", "--porcelain=v1", "--branch", "--no-renames"])
        if not res.ok:
            return GitState(branch=None, clean=True, entries=(), is_repo=False)
        branch: str | None = None
        entries: list[GitFileStatus] = []
        for line in res.stdout.splitlines():
            if line.startswith("## "):
                branch = line[3:].split("...")[0].strip()
                continue
            if len(line) >= 4:
                entries.append(GitFileStatus(path=line[3:].strip(), status=line[:2].strip()))
        return GitState(
            branch=branch, clean=not entries, entries=tuple(entries), is_repo=True
        )

    def diff(self, *, staged: bool = False, paths: list[str] | None = None) -> str:
        args = ["diff", "--no-color", "--no-ext-diff"]
        if staged:
            args.append("--cached")
        if paths:
            args += ["--", *_check_paths(paths)]
        res = self._run(args, timeout=60.0)
        return res.stdout if res.status == "completed" else ""

    def changed_files(self) -> list[str]:
        return [e.path for e in self.state().entries]

    def full_diff(self) -> str:
        """Read-only diff covering tracked changes, staged changes AND
        untracked files (via ``git diff --no-index``), so reviewers see the
        complete introduced content."""
        parts = [self.diff(), self.diff(staged=True)]
        for entry in self.state().entries:
            if entry.status == "??":
                res = self._run(
                    ["diff", "--no-color", "--no-ext-diff", "--no-index",
                     "--", "/dev/null", *_check_paths([entry.path])],
                    timeout=30.0,
                )
                # --no-index exits 1 when files differ; stdout is still valid.
                if res.status == "completed":
                    parts.append(res.stdout)
        return "\n".join(p for p in parts if p.strip())

    def log(self, *, limit: int = 10) -> str:
        res = self._run(["log", "--oneline", f"-{max(1, min(limit, 100))}"])
        return res.stdout if res.ok else ""

    # ---- mutating (L5; approval enforced by the tool/policy layer) ----

    def create_branch(self, name: str) -> SandboxResult:
        return self._run(["checkout", "-b", _check_ref(name)])

    def add(self, paths: list[str]) -> SandboxResult:
        if not paths:
            raise GitSafetyError("explicit paths are required; 'git add -A' is not allowed")
        return self._run(["add", "--", *_check_paths(paths)])

    def commit(self, message: str, paths: list[str]) -> SandboxResult:
        if not message.strip():
            raise GitSafetyError("empty commit message rejected")
        if message.startswith("-"):
            raise GitSafetyError("unsafe commit message rejected")
        add_res = self.add(paths)
        if not add_res.ok:
            return add_res
        return self._run(["commit", "--no-verify", "-m", message, "--", *_check_paths(paths)])
