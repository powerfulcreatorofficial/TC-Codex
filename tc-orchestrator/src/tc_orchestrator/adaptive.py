"""Deterministic, evidence-driven failure classification and bounded recovery policy."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .models import RecoveryClass, TaskStatus, TaskSummary


@dataclass(frozen=True)
class RecoveryDecision:
    recovery_class: RecoveryClass
    severity: str
    repair_attempts: int
    max_repair_attempts: int
    retry_allowed: bool
    recommended_action: str
    evidence: tuple[str, ...]


def _text(event: dict[str, Any]) -> str:
    return " ".join(str(event.get(k) or "") for k in ("event_type", "tool_name", "status", "result_metadata")).lower()


def _repair_attempts(events: list[dict[str, Any]]) -> int:
    signals = 0
    for event in events:
        text = _text(event)
        if any(token in text for token in ("repair", "fix", "patch", "edit_file")):
            signals += 1
    return signals


def classify_failure(summary: TaskSummary, events: Iterable[dict[str, Any]], *, max_repair_attempts: int = 3) -> RecoveryDecision:
    event_list = list(events)
    attempts = min(_repair_attempts(event_list), max_repair_attempts)
    text = " ".join(_text(e) for e in event_list[-12:]) + " " + str(summary.error or "").lower()
    evidence: list[str] = []

    if summary.status == TaskStatus.AWAITING_APPROVAL or "approval" in text and "pending" in text:
        recovery_class = RecoveryClass.APPROVAL_BLOCKED
        severity = "blocking"
        retry = False
        action = "Wait for the Owner to approve or reject the exact pending action. Do not bypass approval."
        evidence.append("Task is waiting at the approval boundary.")
    elif any(token in text for token in ("402", "payment required", "provider unavailable", "authentication failed", "rate limit", "429")):
        recovery_class = RecoveryClass.PROVIDER_FAILURE
        severity = "blocking"
        retry = False
        action = "Verify provider/account/model availability outside the workspace before retrying. Do not mutate project files."
        evidence.append("Recent task evidence contains a provider/authentication/billing failure signal.")
    elif any(token in text for token in ("verification", "pytest", "test failed", "build failed", "check failed")):
        recovery_class = RecoveryClass.VERIFICATION_FAILURE
        severity = "recoverable" if attempts < max_repair_attempts else "blocking"
        retry = attempts < max_repair_attempts
        action = "Inspect the concrete verification failure, apply one targeted repair, then rerun the same verification." if retry else "Repair budget exhausted; require a new plan or explicit Owner intervention."
        evidence.append("Recent events indicate a verification failure or verification check.")
    elif "repeated" in text or "identical tool call" in text:
        recovery_class = RecoveryClass.REPEATED_ACTION
        severity = "blocking"
        retry = False
        action = "Stop repeating the same action and replan from the latest evidence."
        evidence.append("The loop detected repeated identical tool behavior.")
    elif any(token in text for token in ("tool failed", "tool_failure", "exec_command", "write_file")) and summary.status == TaskStatus.FAILED:
        recovery_class = RecoveryClass.TOOL_FAILURE
        severity = "recoverable" if attempts < max_repair_attempts else "blocking"
        retry = attempts < max_repair_attempts
        action = "Inspect the concrete tool error, correct the smallest relevant issue, and rerun the failed tool." if retry else "Repair budget exhausted; require a new plan or explicit Owner intervention."
        evidence.append("Task events contain a tool failure signal.")
    else:
        recovery_class = RecoveryClass.UNKNOWN_FAILURE
        severity = "blocking" if summary.status == TaskStatus.FAILED else "advisory"
        retry = summary.status != TaskStatus.COMPLETED and attempts < max_repair_attempts
        action = "Inspect the latest evidence and derive a bounded next step before retrying." if retry else "No safe automatic recovery is available from current evidence."
        evidence.append("No more specific deterministic failure class matched the available evidence.")

    evidence.append(f"Observed {attempts} repair signal(s); budget is {max_repair_attempts}.")
    return RecoveryDecision(recovery_class, severity, attempts, max_repair_attempts, retry, action, tuple(evidence))


def recovery_prompt(decision: RecoveryDecision) -> str:
    if not decision.retry_allowed:
        return f"Recovery policy: {decision.recovery_class.value}. {decision.recommended_action}"
    return (
        f"Recovery policy: {decision.recovery_class.value}. "
        f"{decision.recommended_action} "
        f"This is bounded recovery attempt {decision.repair_attempts + 1} of {decision.max_repair_attempts}."
    )
