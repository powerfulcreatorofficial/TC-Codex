"""Cybertron tool surface — capability-levelled, schema-validated, audited.

Levels:
  L0 — safe read-only inspection (read, list, git state)
  L1 — search / context (glob, grep, symbols)
  L2 — patch / edit (apply_patch, write_file)
  L3 — tests / build / static checks (allowlisted verification commands)
  L4 — controlled shell execution (arbitrary argv in the sandbox)
  L5 — git write operations (branch, commit) — strongest approval

Every tool returns a structured :class:`ToolOutcome` with a truthful ``ok``,
real exit codes where applicable, bounded output, and an audit record.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from .gitsafe import GitSafetyError, SafeGit
from .models import CapabilityLevel
from .repo_intel import RepoIntelligence
from .sandbox import LocalProcessSandbox, SandboxLimits
from .workspace import SafeWorkspace, WorkspaceSecurityError

_TAIL = 4000


@dataclass(frozen=True)
class ToolOutcome:
    tool: str
    level: CapabilityLevel
    ok: bool
    output: str
    error: str | None = None
    exit_code: int | None = None
    truncated: bool = False
    duration_ms: int = 0
    data: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# argument schemas
# ---------------------------------------------------------------------------


class ReadArgs(BaseModel):
    path: str
    start_line: int = Field(default=1, ge=1)
    max_lines: int = Field(default=0, ge=0, le=5000)


class ListArgs(BaseModel):
    path: str = "."


class GlobArgs(BaseModel):
    pattern: str = Field(min_length=1, max_length=400)


class GrepArgs(BaseModel):
    pattern: str = Field(min_length=1, max_length=800)
    path_glob: str = "*"
    max_matches: int = Field(default=100, ge=1, le=500)


class SymbolArgs(BaseModel):
    name_pattern: str = Field(min_length=1, max_length=200)


class PatchArgs(BaseModel):
    patch: str = Field(min_length=1, max_length=400_000)


class WriteArgs(BaseModel):
    path: str
    content: str = Field(max_length=2_000_000)
    expected_sha256: str | None = None


class RunArgs(BaseModel):
    argv: list[str] = Field(min_length=1, max_length=64)
    cwd: str | None = None
    timeout_seconds: float = Field(default=120.0, gt=0, le=1800)


class GitDiffArgs(BaseModel):
    staged: bool = False


class GitBranchArgs(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class GitCommitArgs(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    paths: list[str] = Field(min_length=1, max_length=200)


class NoArgs(BaseModel):
    pass


# ---------------------------------------------------------------------------
# tool definitions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ToolSpec:
    name: str
    level: CapabilityLevel
    description: str
    args_model: type[BaseModel]
    read_only: bool


AuditHook = Callable[[str, CapabilityLevel, dict[str, Any], ToolOutcome], None]


class CybertronToolset:
    """The authoritative tool allowlist for Cybertron engineering tasks."""

    def __init__(
        self,
        workspace: SafeWorkspace,
        sandbox: LocalProcessSandbox,
        git: SafeGit,
        intel: RepoIntelligence,
        *,
        audit_hook: AuditHook | None = None,
    ) -> None:
        self._ws = workspace
        self._sandbox = sandbox
        self._git = git
        self._intel = intel
        self._audit = audit_hook
        self._specs: dict[str, ToolSpec] = {}
        self._handlers: dict[str, Callable[[BaseModel], ToolOutcome]] = {}
        self._register_all()

    # ------------------------------------------------------------------

    def specs(self) -> list[ToolSpec]:
        return list(self._specs.values())

    def spec(self, name: str) -> ToolSpec | None:
        return self._specs.get(name)

    def level_of(self, name: str) -> CapabilityLevel | None:
        spec = self._specs.get(name)
        return spec.level if spec else None

    def execute(self, name: str, arguments: dict[str, Any]) -> ToolOutcome:
        spec = self._specs.get(name)
        if spec is None:
            outcome = ToolOutcome(
                tool=name,
                level=CapabilityLevel.L4,
                ok=False,
                output="",
                error=f"unknown tool: {name}",
            )
            self._emit(name, CapabilityLevel.L4, arguments, outcome)
            return outcome
        try:
            args = spec.args_model.model_validate(arguments)
        except ValidationError as exc:
            outcome = ToolOutcome(
                tool=name, level=spec.level, ok=False, output="",
                error=f"invalid arguments: {exc.errors()[:3]}",
            )
            self._emit(name, spec.level, arguments, outcome)
            return outcome
        start = time.monotonic()
        try:
            outcome = self._handlers[name](args)
        except (WorkspaceSecurityError, GitSafetyError) as exc:
            outcome = ToolOutcome(
                tool=name, level=spec.level, ok=False, output="",
                error=f"security rejection: {exc}",
            )
        except FileNotFoundError as exc:
            outcome = ToolOutcome(
                tool=name, level=spec.level, ok=False, output="", error=f"not found: {exc}"
            )
        except ValueError as exc:
            outcome = ToolOutcome(
                tool=name, level=spec.level, ok=False, output="", error=str(exc)
            )
        except Exception as exc:  # noqa: BLE001 - tools never crash the engine
            outcome = ToolOutcome(
                tool=name, level=spec.level, ok=False, output="",
                error=f"tool execution error: {exc}",
            )
        if outcome.duration_ms == 0:
            outcome = ToolOutcome(
                tool=outcome.tool, level=outcome.level, ok=outcome.ok,
                output=outcome.output, error=outcome.error, exit_code=outcome.exit_code,
                truncated=outcome.truncated,
                duration_ms=int((time.monotonic() - start) * 1000),
                data=outcome.data,
            )
        self._emit(name, spec.level, arguments, outcome)
        return outcome

    def _emit(
        self, name: str, level: CapabilityLevel, args: dict[str, Any], outcome: ToolOutcome
    ) -> None:
        if self._audit is not None:
            safe_args = {
                k: (v if isinstance(v, (int, float, bool)) else str(v)[:200])
                for k, v in args.items()
                if k not in ("content", "patch")
            }
            if "content" in args:
                safe_args["content_bytes"] = len(str(args["content"]))
            if "patch" in args:
                safe_args["patch_bytes"] = len(str(args["patch"]))
            self._audit(name, level, safe_args, outcome)

    # ------------------------------------------------------------------
    # registration
    # ------------------------------------------------------------------

    def _reg(
        self,
        name: str,
        level: CapabilityLevel,
        description: str,
        args_model: type[BaseModel],
        handler: Callable[[Any], ToolOutcome],
        *,
        read_only: bool,
    ) -> None:
        self._specs[name] = ToolSpec(
            name=name, level=level, description=description,
            args_model=args_model, read_only=read_only,
        )
        self._handlers[name] = handler

    def _register_all(self) -> None:
        self._reg("read_file", CapabilityLevel.L0,
                  "Read a file (optionally a line range) inside the workspace.",
                  ReadArgs, self._t_read, read_only=True)
        self._reg("list_dir", CapabilityLevel.L0,
                  "List a directory inside the workspace.",
                  ListArgs, self._t_list, read_only=True)
        self._reg("git_state", CapabilityLevel.L0,
                  "Branch, cleanliness and changed files of the workspace repo.",
                  NoArgs, self._t_git_state, read_only=True)
        self._reg("git_diff", CapabilityLevel.L0,
                  "Unified diff of current changes (read-only).",
                  GitDiffArgs, self._t_git_diff, read_only=True)
        self._reg("repo_model", CapabilityLevel.L1,
                  "Structured repository intelligence summary.",
                  NoArgs, self._t_repo_model, read_only=True)
        self._reg("glob", CapabilityLevel.L1, "Find files matching a glob pattern.",
                  GlobArgs, self._t_glob, read_only=True)
        self._reg("grep", CapabilityLevel.L1, "Regex search across workspace files.",
                  GrepArgs, self._t_grep, read_only=True)
        self._reg("find_symbols", CapabilityLevel.L1,
                  "Find function/class/type definitions by name pattern.",
                  SymbolArgs, self._t_symbols, read_only=True)
        self._reg("apply_patch", CapabilityLevel.L2,
                  "Apply a unified diff to workspace files (preferred edit mechanism).",
                  PatchArgs, self._t_patch, read_only=False)
        self._reg("write_file", CapabilityLevel.L2,
                  "Atomically write a whole file (CAS-protected when hash given).",
                  WriteArgs, self._t_write, read_only=False)
        self._reg("run_check", CapabilityLevel.L3,
                  "Run a test/build/lint command in the sandbox (network off).",
                  RunArgs, self._t_run, read_only=False)
        self._reg("run_command", CapabilityLevel.L4,
                  "Run an arbitrary command in the sandbox (network off; approval-gated).",
                  RunArgs, self._t_run, read_only=False)
        self._reg("git_create_branch", CapabilityLevel.L5,
                  "Create and switch to a new git branch.",
                  GitBranchArgs, self._t_git_branch, read_only=False)
        self._reg("git_commit", CapabilityLevel.L5,
                  "Commit explicit paths with a message (hooks disabled).",
                  GitCommitArgs, self._t_git_commit, read_only=False)

    # ------------------------------------------------------------------
    # handlers
    # ------------------------------------------------------------------

    def _t_read(self, a: ReadArgs) -> ToolOutcome:
        res = self._ws.read_file(a.path, start_line=a.start_line, max_lines=a.max_lines)
        return ToolOutcome(
            tool="read_file", level=CapabilityLevel.L0, ok=True, output=res.text,
            truncated=res.truncated,
            data={"sha256": res.sha256, "total_size": res.total_size,
                  "start_line": res.start_line, "end_line": res.end_line},
        )

    def _t_list(self, a: ListArgs) -> ToolOutcome:
        entries = self._ws.list_dir(a.path)
        return ToolOutcome(
            tool="list_dir", level=CapabilityLevel.L0, ok=True, output="\n".join(entries)
        )

    def _t_git_state(self, _: NoArgs) -> ToolOutcome:
        st = self._git.state()
        lines = [f"is_repo={st.is_repo} branch={st.branch} clean={st.clean}"]
        lines += [f"{e.status}\t{e.path}" for e in st.entries[:100]]
        return ToolOutcome(
            tool="git_state", level=CapabilityLevel.L0, ok=True, output="\n".join(lines),
            data={"branch": st.branch, "clean": st.clean, "is_repo": st.is_repo},
        )

    def _t_git_diff(self, a: GitDiffArgs) -> ToolOutcome:
        diff = self._git.diff(staged=a.staged)
        truncated = len(diff) > 120_000
        return ToolOutcome(
            tool="git_diff", level=CapabilityLevel.L0, ok=True,
            output=diff[:120_000], truncated=truncated,
        )

    def _t_repo_model(self, _: NoArgs) -> ToolOutcome:
        model = self._intel.build_model()
        return ToolOutcome(
            tool="repo_model", level=CapabilityLevel.L1, ok=True,
            output=model.context_text(),
        )

    def _t_glob(self, a: GlobArgs) -> ToolOutcome:
        results = self._ws.glob(a.pattern)
        return ToolOutcome(
            tool="glob", level=CapabilityLevel.L1, ok=True, output="\n".join(results)
        )

    def _t_grep(self, a: GrepArgs) -> ToolOutcome:
        matches = self._ws.grep(a.pattern, path_glob=a.path_glob, max_matches=a.max_matches)
        out = "\n".join(f"{m.path}:{m.line_no}: {m.line}" for m in matches)
        return ToolOutcome(tool="grep", level=CapabilityLevel.L1, ok=True, output=out)

    def _t_symbols(self, a: SymbolArgs) -> ToolOutcome:
        syms = self._intel.find_symbols(a.name_pattern)
        out = "\n".join(f"{s.path}:{s.line_no}: {s.kind} {s.name}" for s in syms)
        return ToolOutcome(tool="find_symbols", level=CapabilityLevel.L1, ok=True, output=out)

    def _t_patch(self, a: PatchArgs) -> ToolOutcome:
        changed = self._ws.apply_patch(a.patch)
        return ToolOutcome(
            tool="apply_patch", level=CapabilityLevel.L2, ok=True,
            output="patched: " + ", ".join(changed), data={"changed_files": changed},
        )

    def _t_write(self, a: WriteArgs) -> ToolOutcome:
        res = self._ws.write_file(a.path, a.content, expected_sha256=a.expected_sha256)
        if not res.written:
            return ToolOutcome(
                tool="write_file", level=CapabilityLevel.L2, ok=False, output="",
                error=res.reason or "write refused",
            )
        return ToolOutcome(
            tool="write_file", level=CapabilityLevel.L2, ok=True,
            output=f"written sha256={res.sha256}", data={"sha256": res.sha256},
        )

    def _t_run(self, a: RunArgs) -> ToolOutcome:
        res = self._sandbox.run(
            a.argv, cwd=a.cwd, limits=SandboxLimits(timeout_seconds=a.timeout_seconds)
        )
        out = (
            f"status={res.status} exit_code={res.exit_code} duration_ms={res.duration_ms}\n"
            f"--- stdout ---\n{res.stdout[-_TAIL:]}\n--- stderr ---\n{res.stderr[-_TAIL:]}"
        )
        return ToolOutcome(
            tool="run_check", level=CapabilityLevel.L3, ok=res.ok, output=out,
            error=res.error, exit_code=res.exit_code,
            truncated=res.stdout_truncated or res.stderr_truncated,
            duration_ms=res.duration_ms, data={"isolation": res.isolation},
        )

    def _t_git_branch(self, a: GitBranchArgs) -> ToolOutcome:
        res = self._git.create_branch(a.name)
        return ToolOutcome(
            tool="git_create_branch", level=CapabilityLevel.L5, ok=res.ok,
            output=res.stdout + res.stderr, error=res.error, exit_code=res.exit_code,
        )

    def _t_git_commit(self, a: GitCommitArgs) -> ToolOutcome:
        res = self._git.commit(a.message, a.paths)
        return ToolOutcome(
            tool="git_commit", level=CapabilityLevel.L5, ok=res.ok,
            output=res.stdout + res.stderr, error=res.error, exit_code=res.exit_code,
        )
