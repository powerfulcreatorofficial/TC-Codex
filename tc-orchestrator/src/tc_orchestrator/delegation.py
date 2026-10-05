"""Bounded specialist-agent delegation for TC.

Workers are helpers. The TC orchestrator remains the authority on policies,
approvals, and integration decisions. The default local backend is packet-only
so a worker cannot silently gain arbitrary shell access through delegation.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib import request

from .agent_protocol import AgentCapability, AgentKind, DelegationResult, DelegationTask


class WorkerBackend(Protocol):
    def submit(self, task: DelegationTask, worker: AgentCapability) -> DelegationResult: ...


@dataclass
class PacketBackend:
    """Writes an auditable job packet and waits for an external worker.

    This is the safest default for the master repository: it gives an agent a
    precise handoff without granting the Python process a second shell path.
    """

    root: Path

    def submit(self, task: DelegationTask, worker: AgentCapability) -> DelegationResult:
        job_dir = self.root / task.task_id
        job_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / "task.json").write_text(json.dumps(task.to_dict(), indent=2) + "\n", encoding="utf-8")
        (job_dir / "worker.json").write_text(json.dumps(worker.__dict__, indent=2, default=list) + "\n", encoding="utf-8")
        return DelegationResult(
            task_id=task.task_id,
            status="queued",
            summary=f"Task packet created for {worker.label}",
            worker=worker.label,
            evidence=[str(job_dir / "task.json")],
            metadata={"packet_dir": str(job_dir)},
        )


@dataclass
class HttpBackend:
    """Optional worker backend using a simple HTTP task endpoint."""

    timeout: float = 30.0

    def submit(self, task: DelegationTask, worker: AgentCapability) -> DelegationResult:
        if not worker.endpoint:
            raise ValueError("worker has no endpoint")
        payload = json.dumps(task.to_dict()).encode("utf-8")
        req = request.Request(worker.endpoint, data=payload, headers={"Content-Type": "application/json"})
        with request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310 - endpoint is operator-configured
            data = json.loads(resp.read().decode("utf-8"))
        return DelegationResult(
            task_id=task.task_id,
            status=str(data.get("status", "submitted")),
            summary=str(data.get("summary", "worker accepted task")),
            changed_files=list(data.get("changed_files", [])),
            evidence=list(data.get("evidence", [])),
            tests=list(data.get("tests", [])),
            warnings=list(data.get("warnings", [])),
            worker=worker.label,
            metadata=dict(data.get("metadata", {})),
        )


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[AgentKind, AgentCapability] = {}

    def register(self, capability: AgentCapability) -> None:
        self._agents[capability.kind] = capability

    def get(self, kind: AgentKind) -> AgentCapability:
        try:
            return self._agents[kind]
        except KeyError as exc:
            raise KeyError(f"no registered worker for {kind}") from exc

    def all(self) -> list[AgentCapability]:
        return list(self._agents.values())

    @classmethod
    def from_env(cls) -> "AgentRegistry":
        reg = cls()
        defaults = [
            AgentCapability(AgentKind.PRIMARY_CODER, "TC Primary Coder", "General implementation work"),
            AgentCapability(AgentKind.REPOSITORY_CODER, "Repository Coder", "Repository-aware fixes and refactors"),
            AgentCapability(AgentKind.RESEARCHER, "Engineering Researcher", "Technology and evidence research"),
            AgentCapability(AgentKind.TESTER, "Verification Agent", "Tests, regression checks and acceptance evidence"),
            AgentCapability(AgentKind.UI_ENGINEER, "UI Engineer", "Frontend and visualization work"),
            AgentCapability(AgentKind.SCIENTIFIC_SPECIALIST, "Scientific Specialist", "Numerical, geometry and physics workflows"),
            AgentCapability(AgentKind.REVIEWER, "Independent Reviewer", "Review diffs and evidence before integration"),
        ]
        for item in defaults:
            env = f"TC_AGENT_{item.kind.value.upper()}_URL"
            endpoint = os.getenv(env) or None
            reg.register(item if endpoint is None else AgentCapability(**{**item.__dict__, "endpoint": endpoint}))
        return reg


class DelegationManager:
    def __init__(self, root: str | Path | None = None, *, http_enabled: bool = False) -> None:
        root_path = Path(root or os.getenv("TC_DELEGATION_ROOT", ".tc/delegated-jobs"))
        self.registry = AgentRegistry.from_env()
        self.packet = PacketBackend(root_path)
        self.http = HttpBackend()
        self.http_enabled = http_enabled and os.getenv("TC_ALLOW_HTTP_AGENTS", "0") == "1"
        self._jobs: dict[str, DelegationResult] = {}

    @staticmethod
    def choose_kind(objective: str) -> AgentKind:
        text = objective.lower()
        if any(k in text for k in ("test", "verify", "regression", "benchmark")):
            return AgentKind.TESTER
        if any(k in text for k in ("ui", "frontend", "next.js", "dashboard", "visual")):
            return AgentKind.UI_ENGINEER
        if any(k in text for k in ("physics", "pde", "pinn", "mesh", "trimesh", "pyvista", "simulation")):
            return AgentKind.SCIENTIFIC_SPECIALIST
        if any(k in text for k in ("research", "compare", "investigate", "documentation")):
            return AgentKind.RESEARCHER
        if any(k in text for k in ("review", "audit", "security", "inspect diff")):
            return AgentKind.REVIEWER
        if any(k in text for k in ("bug", "fix", "refactor", "repository", "issue")):
            return AgentKind.REPOSITORY_CODER
        return AgentKind.PRIMARY_CODER

    def delegate(
        self,
        objective: str,
        *,
        workspace: str,
        constraints: list[str] | None = None,
        acceptance_criteria: list[str] | None = None,
        context: dict[str, Any] | None = None,
        agent_kind: AgentKind | None = None,
    ) -> DelegationResult:
        kind = agent_kind or self.choose_kind(objective)
        worker = self.registry.get(kind)
        task = DelegationTask(
            objective=objective,
            agent_kind=kind,
            workspace=workspace,
            constraints=list(constraints or []),
            acceptance_criteria=list(acceptance_criteria or []),
            context=dict(context or {}),
        )
        if self.http_enabled and worker.endpoint:
            result = self.http.submit(task, worker)
        else:
            result = self.packet.submit(task, worker)
        self._jobs[result.task_id] = result
        return result

    def get(self, task_id: str) -> DelegationResult | None:
        return self._jobs.get(task_id)
