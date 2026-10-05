from tc_orchestrator.evaluation import evaluate_task
from tc_orchestrator.models import TaskStatus, TaskSummary


def test_completed_verified_task_scores_strongly():
    summary = TaskSummary(
        task_id="task-1",
        status=TaskStatus.COMPLETED,
        prompt="run tests",
        answer="done",
        steps=3,
        current_step=3,
    )
    events = [
        {"event_type": "task_started"},
        {"event_type": "tool_call", "tool_name": "run_tests", "result_metadata": {"output": "pytest passed"}},
        {"event_type": "task_completed"},
    ]
    result = evaluate_task(summary, events)
    assert result.overall_score >= 85
    assert result.verdict == "strong"
    assert result.verification_signals >= 2


def test_failed_task_is_not_scored_as_success():
    summary = TaskSummary(
        task_id="task-2",
        status=TaskStatus.FAILED,
        prompt="broken",
        error="provider error",
        steps=1,
    )
    result = evaluate_task(summary, [{"event_type": "task_started"}, {"event_type": "task_failed"}])
    assert result.overall_score < 60
    assert result.verdict == "failed"


def test_approval_compliance_is_observable():
    summary = TaskSummary(
        task_id="task-3",
        status=TaskStatus.COMPLETED,
        prompt="approved change",
        steps=2,
    )
    result = evaluate_task(
        summary,
        [
            {"event_type": "approval_requested"},
            {"event_type": "approval_decided", "status": "approved"},
            {"event_type": "verification_passed"},
            {"event_type": "task_completed"},
        ],
    )
    assert result.approvals_requested == 1
    assert result.approvals_decided == 1
    assert any(d.key == "control" and d.score == 100 for d in result.dimensions)


def test_repair_lesson_is_derived_from_completed_verified_run():
    from tc_orchestrator.learning import derive_learnings

    summary = TaskSummary(
        task_id="task-4",
        status=TaskStatus.COMPLETED,
        prompt="repair a test",
        steps=9,
        answer="fixed",
    )
    events = [
        {"event_type": "tool_call", "tool_name": "read_file", "result_metadata": {}},
        {"event_type": "tool_call", "tool_name": "exec_command", "result_metadata": {"output": "pytest failed"}},
        {"event_type": "tool_call", "tool_name": "edit_file", "result_metadata": {}},
        {"event_type": "tool_call", "tool_name": "exec_command", "result_metadata": {"output": "pytest passed"}},
        {"event_type": "task_completed"},
    ]
    lessons = derive_learnings(summary, events)
    assert any(x.category == "repair" for x in lessons)
    assert any(x.category == "verification" for x in lessons)
    assert any(x.category == "efficiency" for x in lessons)
