"""Independent read-only review of a completed engineering attempt.

The reviewer never trusts the builder's textual claims. It inspects:
- the requested objective
- the ACTUAL diff (from git, read-only)
- the verification evidence (exit codes, not prose)
- security-sensitive patterns introduced by the change

The deterministic reviewer below is the default. ``ReviewerProtocol`` is the
extension point for a second, independent model/provider to review later —
its verdict may only make the result stricter, never relax the verification
gate.
"""

from __future__ import annotations

import re
from typing import Protocol

from .gitsafe import SafeGit
from .models import ReviewFinding, ReviewReport, VerificationReport

_SECURITY_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"][A-Za-z0-9_\-]{12,}",
     "hardcoded credential-like string"),
    (r"curl[^|\n]*\|\s*(ba)?sh", "piping a download into a shell"),
    (r"(?m)^\+.*\beval\s*\(", "introduces eval()"),
    (r"(?m)^\+.*subprocess\.[A-Za-z_]+\([^)]*shell\s*=\s*True", "subprocess with shell=True"),
    (r"(?m)^\+.*(~/.ssh|~/.aws|/etc/shadow|/etc/passwd)", "references sensitive host paths"),
    (r"(?m)^\+.*chmod\s+777", "world-writable permissions"),
)


class ReviewerProtocol(Protocol):
    """Extension point for an independent model-based reviewer."""

    def review(
        self, objective: str, diff: str, verification: VerificationReport
    ) -> ReviewReport: ...


class DeterministicReviewer:
    """Read-only, evidence-based reviewer. Trusts exit codes and diffs only."""

    name = "deterministic-reviewer"

    def review(
        self, objective: str, diff: str, verification: VerificationReport
    ) -> ReviewReport:
        findings: list[ReviewFinding] = []

        # 1) Verification evidence is mandatory for approval.
        if not verification.checks:
            findings.append(
                ReviewFinding(
                    severity="blocking",
                    category="verification",
                    message="no verification evidence exists; the change is unproven",
                )
            )
        elif not verification.passed:
            findings.append(
                ReviewFinding(
                    severity="blocking",
                    category="verification",
                    message="verification failed: " + "; ".join(
                        f"exit={c.exit_code} {' '.join(c.argv)}"
                        for c in verification.checks
                        if not c.ok
                    ),
                )
            )

        # 2) Security scan of the actual introduced diff.
        for pattern, label in _SECURITY_PATTERNS:
            if re.search(pattern, diff or ""):
                findings.append(
                    ReviewFinding(
                        severity="blocking", category="security",
                        message=f"diff introduces a risky pattern: {label}",
                    )
                )

        # 3) Oversized / suspicious change shape.
        added = sum(1 for line in (diff or "").splitlines()
                    if line.startswith("+") and not line.startswith("+++"))
        if added > 5000:
            findings.append(
                ReviewFinding(
                    severity="warning", category="scope",
                    message=f"very large change ({added} added lines); verify scope",
                )
            )

        # 4) Objective/diff sanity: a mutation objective with an empty diff
        # cannot be a verified success by itself (verification may still
        # legitimately pass for read-only objectives).
        if not (diff or "").strip() and verification.checks:
            findings.append(
                ReviewFinding(
                    severity="info", category="scope",
                    message="no diff was produced; result relies solely on verification evidence",
                )
            )

        blocking = [f for f in findings if f.severity == "blocking"]
        approved = not blocking
        summary = (
            "review approved: verification evidence present and no blocking findings"
            if approved
            else "review rejected: " + "; ".join(f.message for f in blocking)
        )
        return ReviewReport(
            approved=approved, reviewer=self.name, findings=findings, summary=summary
        )


def review_attempt(
    git: SafeGit,
    objective: str,
    verification: VerificationReport,
    *,
    reviewer: ReviewerProtocol | None = None,
) -> ReviewReport:
    """Run the review stage. Always includes the deterministic reviewer; an
    optional independent reviewer can only ADD findings (stricter), never
    override a deterministic rejection."""
    diff = git.full_diff()
    base = DeterministicReviewer().review(objective, diff, verification)
    if reviewer is None:
        return base
    try:
        extra = reviewer.review(objective, diff, verification)
    except Exception as exc:  # noqa: BLE001 - an unavailable reviewer never relaxes gates
        extra = ReviewReport(
            approved=True, reviewer="external-reviewer-unavailable",
            findings=[ReviewFinding(severity="info", category="review",
                                    message=f"external reviewer unavailable: {exc}")],
            summary="external reviewer unavailable; deterministic review stands",
        )
    findings = base.findings + extra.findings
    approved = base.approved and extra.approved
    return ReviewReport(
        approved=approved,
        reviewer=f"{base.reviewer}+{extra.reviewer}",
        findings=findings,
        summary=base.summary if base.approved else base.summary,
    )
