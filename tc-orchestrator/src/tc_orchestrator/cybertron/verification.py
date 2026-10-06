"""Deterministic verification — the hard gate of the Cybertron loop.

Verification runs the plan's verification commands in the sandbox and
requires EVERY command to complete with exit code 0. There is no way to
pass verification without the commands actually succeeding:

- a timeout is a failure
- a non-zero exit code is a failure
- a missing executable is a failure
- zero verification commands is an explicit "not verified" outcome, which
  the engine must treat as (at best) PARTIAL, never SUCCESS.
"""

from __future__ import annotations

from .models import VerificationCheck, VerificationReport
from .sandbox import LocalProcessSandbox, SandboxLimits

_TAIL = 4000


def run_verification(
    sandbox: LocalProcessSandbox,
    commands: list[list[str]],
    *,
    timeout_seconds: float = 600.0,
) -> VerificationReport:
    if not commands:
        return VerificationReport(
            passed=False,
            checks=[],
            reason="no verification commands were defined; the result is unverified",
        )
    checks: list[VerificationCheck] = []
    all_ok = True
    for argv in commands:
        res = sandbox.run(
            list(argv), limits=SandboxLimits(timeout_seconds=timeout_seconds, network=False)
        )
        ok = res.ok  # completed AND exit code 0 — nothing else counts
        checks.append(
            VerificationCheck(
                argv=list(argv),
                ok=ok,
                exit_code=res.exit_code,
                status=res.status,
                stdout_tail=res.stdout[-_TAIL:],
                stderr_tail=res.stderr[-_TAIL:],
                duration_ms=res.duration_ms,
            )
        )
        if not ok:
            all_ok = False
    reason = (
        "all verification commands passed"
        if all_ok
        else "one or more verification commands failed"
    )
    return VerificationReport(passed=all_ok, checks=checks, reason=reason)
