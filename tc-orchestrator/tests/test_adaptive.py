from tc_orchestrator.adaptive import classify_failure
from tc_orchestrator.models import TaskStatus, TaskSummary


def make_summary(error: str, status: TaskStatus = TaskStatus.FAILED) -> TaskSummary:
    return TaskSummary(task_id="t", status=status, prompt="p", error=error, steps=2)


def test_verification_failure_allows_bounded_repair():
    decision = classify_failure(make_summary("pytest failed: assertion"), [{"event_type": "test_failed", "tool_name": "exec_command"}])
    assert decision.recovery_class.value == "verification_failure"
    assert decision.retry_allowed is True


def test_provider_failure_does_not_mutate_workspace():
    decision = classify_failure(make_summary("402 Payment Required"), [])
    assert decision.recovery_class.value == "provider_failure"
    assert decision.retry_allowed is False


def test_repair_budget_is_bounded():
    events = [{"event_type": "repair", "tool_name": "edit_file"}] * 3
    decision = classify_failure(make_summary("pytest failed"), events, max_repair_attempts=3)
    assert decision.repair_attempts == 3
    assert decision.retry_allowed is False
