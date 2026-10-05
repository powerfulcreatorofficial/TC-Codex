from types import SimpleNamespace

from tc_orchestrator.context_engine import assemble_project_context, classify_project_health
from tc_orchestrator.models import TaskStatus


def test_context_packet_is_bounded_and_deterministic():
    project = {"id": "p1", "name": "demo", "description": "x", "workspace_path": "demo", "task_count": 2}
    tasks = [SimpleNamespace(task_id="t1", status=TaskStatus.COMPLETED, steps=2, prompt="ship it")]
    learnings = [{"category": "verification", "lesson": "verify first"}]
    plan = {"plan_id": "pl1", "status": "READY", "objective": "ship it", "steps": [{"id": "verify", "title": "Verify", "verification": "pytest", "risk": "low"}]}
    a = assemble_project_context(project, tasks, learnings, plan)
    b = assemble_project_context(project, tasks, learnings, plan)
    assert a == b
    assert a.project_id == "p1"
    assert "[project]" in a.context_text
    assert "[verified_lessons]" in a.context_text
    assert "[approved_plan]" in a.context_text


def test_project_health():
    tasks = [
        SimpleNamespace(status=TaskStatus.COMPLETED),
        SimpleNamespace(status=TaskStatus.FAILED),
        SimpleNamespace(status=TaskStatus.RUNNING),
    ]
    assert classify_project_health(tasks) == {"total": 3, "completed": 1, "failed": 1, "active": 1, "completion_rate": 33}
