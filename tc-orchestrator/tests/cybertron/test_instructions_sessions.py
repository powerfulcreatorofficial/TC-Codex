"""AGENTS.md project docs and session rollout persistence."""

from __future__ import annotations

from tc_orchestrator.cybertron.instructions import (
    discover_project_docs,
    guidance_text,
)
from tc_orchestrator.cybertron.models import Stage, TaskEvent
from tc_orchestrator.cybertron.sessions import SessionRecorder
from tc_orchestrator.cybertron.workspace import SafeWorkspace


def test_hierarchical_agents_md_discovery(tmp_path):
    (tmp_path / "AGENTS.md").write_text("# Root rules\nUse ruff.\n")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "AGENTS.md").write_text("# Pkg rules\nTests in tests/.\n")
    ws = SafeWorkspace(tmp_path)
    docs = discover_project_docs(ws, subpath="pkg")
    assert [d.path for d in docs] == ["AGENTS.md", "pkg/AGENTS.md"]
    text = guidance_text(docs)
    assert "Use ruff." in text and "Tests in tests/." in text
    # Advisory framing: repository docs can never override policy.
    assert "ADVISORY" in text
    assert "NEVER override safety policy" in text


def test_agents_md_size_cap(tmp_path):
    (tmp_path / "AGENTS.md").write_text("x" * 100_000)
    ws = SafeWorkspace(tmp_path, max_read_bytes=200_000)
    docs = discover_project_docs(ws, max_total_bytes=1000)
    assert docs[0].truncated
    assert len(docs[0].content) <= 1000


def test_missing_agents_md_is_fine(tmp_path):
    ws = SafeWorkspace(tmp_path)
    assert discover_project_docs(ws) == []
    assert guidance_text([]) == ""


def test_session_record_list_load(tmp_path):
    rec = SessionRecorder(tmp_path / "sessions")
    rec.start("task-1", "fix the bug", "/ws")
    rec.record_event("task-1", TaskEvent(
        seq=1, stage=Stage.ORIENT, event_type="repo_model_built", detail={"files": 3},
    ))
    rec.record_event("task-1", TaskEvent(
        seq=2, stage=Stage.VERIFY, event_type="verification_finished",
        detail={"passed": False},
    ))
    sessions = rec.list_sessions()
    assert len(sessions) == 1
    info = sessions[0]
    assert info.task_id == "task-1"
    assert info.objective == "fix the bug"
    assert info.event_count == 2
    assert info.final_status is None  # no report => honestly interrupted

    lines = rec.load("task-1")
    assert lines[0]["type"] == "meta"
    assert lines[1]["event_type"] == "repo_model_built"
    # Events survive across recorder instances (process restart).
    rec2 = SessionRecorder(tmp_path / "sessions")
    assert rec2.load("task-1") == lines


def test_session_report_recorded(tmp_path):
    from tc_orchestrator.cybertron.models import FinalStatus, TaskReport

    rec = SessionRecorder(tmp_path / "s")
    rec.start("t2", "obj", "/ws")
    rec.record_report("t2", TaskReport(
        task_id="t2", status=FinalStatus.FAILED, summary="verification failed",
    ))
    info = rec.list_sessions()[0]
    assert info.final_status == "FAILED"
