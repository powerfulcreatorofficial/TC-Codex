from pathlib import Path

from tc_orchestrator.delegation import DelegationManager
from tc_orchestrator.engineering.catalog import discover


def test_agent_choice() -> None:
    manager = DelegationManager(root=Path.cwd() / ".tmp-jobs")
    assert manager.choose_kind("fix a repository bug") == "repository_coder"
    assert manager.choose_kind("run a mesh physics simulation") == "scientific_specialist"
    assert manager.choose_kind("verify regression tests") == "tester"


def test_packet_delegation(tmp_path) -> None:
    manager = DelegationManager(root=tmp_path / "jobs")
    result = manager.delegate("investigate a PDE solver", workspace=str(tmp_path))
    assert result.status == "queued"
    assert (tmp_path / "jobs" / result.task_id / "task.json").exists()


def test_capability_discovery() -> None:
    names = {item.name for item in discover()}
    assert "mesh_geometry" in names
    assert "3d_visualization" in names
