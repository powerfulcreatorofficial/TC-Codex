from types import SimpleNamespace

from tc_orchestrator.retrieval import retrieve_project_evidence


def task(task_id, prompt, status="COMPLETED", steps=3):
    return SimpleNamespace(task_id=task_id, prompt=prompt, status=status, steps=steps, answer="pytest passed", error=None)


def test_retrieval_is_relevant_and_stable():
    tasks = [
        task("t1", "Fix pytest authentication failure and rerun tests"),
        task("t2", "Update marketing copy for the homepage"),
        task("t3", "Refactor authentication middleware"),
    ]
    learnings = [{"id": 1, "category": "verification", "lesson": "Run pytest after authentication changes.", "evidence": "pytest passed"}]
    a = retrieve_project_evidence("authentication pytest", tasks, learnings)
    b = retrieve_project_evidence("authentication pytest", tasks, learnings)
    assert a.context_text == b.context_text
    assert a.items
    assert a.items[0].record_id in {"t1", "1"}
    assert all(item.record_id != "t2" for item in a.items)
    assert all(item.score >= 15 for item in a.items)
    assert len(a.items) <= 6


def test_unrelated_query_returns_thresholded_context():
    tasks = [task("t1", "Build a payment webhook")]
    packet = retrieve_project_evidence("kubernetes cluster networking", tasks, [])
    assert not packet.items
    assert "No relevant persisted project evidence" in packet.context_text
