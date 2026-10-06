"""Codex-style execution policy for Cybertron's agent loop.

Mirrors the Codex CLI model:

- approval policy: ``untrusted`` (gate everything not known-safe),
  ``on-request`` (auto-run inside the sandbox; the model may explicitly
  request escalated approval with a justification), ``never`` (no prompts;
  rely entirely on the sandbox).
- sandbox mode: ``read-only`` (only known-safe read-only commands may run)
  or ``workspace-write``. ``danger-full-access`` is deliberately NOT
  implemented — Cybertron never offers an unsandboxed mode.

Known-safe classification parses simple ``bash -lc`` command lines, splits
on shell operators, and requires EVERY sub-command to be a known read-only
command with no redirections or substitutions. Anything unparseable is
unsafe — fail closed.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from enum import StrEnum


class ApprovalPolicy(StrEnum):
    UNTRUSTED = "untrusted"      # gate everything that is not known-safe
    ON_REQUEST = "on-request"    # auto-run sandboxed; model may request escalation
    NEVER = "never"              # never prompt; sandbox is the only boundary


class SandboxMode(StrEnum):
    READ_ONLY = "read-only"
    WORKSPACE_WRITE = "workspace-write"
    # danger-full-access intentionally absent.


# Commands that are read-only and side-effect-free on the workspace.
_KNOWN_SAFE: dict[str, set[frozenset[str]] | None] = {
    "ls": None, "cat": None, "head": None, "tail": None, "wc": None,
    "pwd": None, "echo": None, "true": None, "false": None, "which": None,
    "grep": None, "rg": None, "find": None, "sort": None, "uniq": None,
    "cut": None, "tr": None, "basename": None, "dirname": None,
    "env": None, "date": None, "file": None, "stat": None, "du": None,
    "nl": None, "diff": None, "sed": None,
}

_SAFE_GIT_SUBCOMMANDS = {
    "status", "diff", "log", "show", "branch", "rev-parse", "ls-files",
    "blame", "shortlog", "describe",
}

_SAFE_FIND_FORBIDDEN = {"-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprintf", "-fprint"}
_SAFE_SED_REQUIRES = "-n"

_SHELL_OPERATORS = {"&&", "||", ";", "|"}
_UNSAFE_TOKENS = {">", ">>", "<", "<<", "&", "$(", "`", "<(", ">("}


@dataclass(frozen=True)
class SafetyAssessment:
    known_safe: bool
    reason: str


def _word_has_unsafe_token(word: str) -> bool:
    return any(tok in word for tok in _UNSAFE_TOKENS)


def _is_safe_simple_command(words: list[str]) -> SafetyAssessment:
    if not words:
        return SafetyAssessment(False, "empty command")
    exe = words[0].rsplit("/", 1)[-1]
    if any(_word_has_unsafe_token(w) for w in words):
        return SafetyAssessment(False, "redirection/substitution tokens present")
    if exe == "git":
        sub = next((w for w in words[1:] if not w.startswith("-")), "")
        if sub in _SAFE_GIT_SUBCOMMANDS:
            return SafetyAssessment(True, f"read-only git {sub}")
        return SafetyAssessment(False, f"git subcommand not read-only: {sub or '?'}")
    if exe not in _KNOWN_SAFE:
        return SafetyAssessment(False, f"not a known-safe command: {exe}")
    if exe == "find" and any(w in _SAFE_FIND_FORBIDDEN for w in words[1:]):
        return SafetyAssessment(False, "find with mutating/exec arguments")
    if exe == "sed" and (_SAFE_SED_REQUIRES not in words[1:] or "-i" in words[1:]):
        return SafetyAssessment(False, "only 'sed -n' print-mode is known-safe")
    return SafetyAssessment(True, f"known-safe read-only command: {exe}")


def _split_on_operators(tokens: list[str]) -> list[list[str]] | None:
    commands: list[list[str]] = []
    current: list[str] = []
    for tok in tokens:
        if tok in _SHELL_OPERATORS:
            if not current:
                return None
            commands.append(current)
            current = []
        else:
            current.append(tok)
    if current:
        commands.append(current)
    return commands or None


def assess_command(argv: list[str]) -> SafetyAssessment:
    """Classify an argv as known-safe (read-only) or not. Fail closed."""
    if not argv:
        return SafetyAssessment(False, "empty argv")
    # bash -lc / sh -c "<script>": parse the script conservatively.
    exe = argv[0].rsplit("/", 1)[-1]
    if exe in ("bash", "sh") and len(argv) >= 3 and argv[1] in ("-lc", "-c"):
        script = argv[2]
        if any(tok in script for tok in ("$(", "`", "<(", ">(")):
            return SafetyAssessment(False, "command substitution in shell script")
        try:
            lex = shlex.shlex(script, posix=True, punctuation_chars=";&|<>")
            lex.whitespace_split = True
            tokens = list(lex)
        except ValueError:
            return SafetyAssessment(False, "unparseable shell script")
        # shlex with punctuation_chars groups operators like '&&' into tokens.
        normalized: list[str] = []
        for tok in tokens:
            if tok in ("&&", "||", ";", "|"):
                normalized.append(tok)
            elif set(tok) <= set(";&|<>"):
                # some other operator cluster (>, >>, <, &, ...) => unsafe
                return SafetyAssessment(False, f"shell operator not allowed: {tok}")
            else:
                normalized.append(tok)
        commands = _split_on_operators(normalized)
        if commands is None:
            return SafetyAssessment(False, "malformed shell pipeline")
        for cmd in commands:
            verdict = _is_safe_simple_command(cmd)
            if not verdict.known_safe:
                return verdict
        return SafetyAssessment(True, "all pipeline stages known-safe")
    return _is_safe_simple_command(list(argv))


@dataclass(frozen=True)
class ExecDecision:
    allow: bool                 # may run at all (sandbox mode permitting)
    needs_approval: bool        # must pass the external approval gate first
    reason: str


def decide_exec(
    argv: list[str],
    *,
    approval_policy: ApprovalPolicy,
    sandbox_mode: SandboxMode,
    escalation_requested: bool = False,
) -> ExecDecision:
    """Combine sandbox mode and approval policy into a single decision."""
    assessment = assess_command(argv)

    if sandbox_mode == SandboxMode.READ_ONLY and not assessment.known_safe:
        # In read-only mode, non-read-only commands may only run with an
        # explicit external approval — regardless of approval policy.
        return ExecDecision(
            allow=True,
            needs_approval=True,
            reason=f"read-only sandbox: {assessment.reason}",
        )

    if approval_policy == ApprovalPolicy.NEVER:
        return ExecDecision(allow=True, needs_approval=False, reason="policy=never")

    if approval_policy == ApprovalPolicy.ON_REQUEST:
        if escalation_requested:
            return ExecDecision(
                allow=True, needs_approval=True, reason="model requested escalation"
            )
        return ExecDecision(
            allow=True, needs_approval=False,
            reason="policy=on-request: sandboxed auto-run",
        )

    # UNTRUSTED: everything not known-safe needs approval.
    if assessment.known_safe:
        return ExecDecision(allow=True, needs_approval=False, reason=assessment.reason)
    return ExecDecision(allow=True, needs_approval=True, reason=assessment.reason)
