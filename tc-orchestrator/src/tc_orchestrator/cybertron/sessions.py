"""Session rollouts (Codex-style): persist task events + final report as
JSONL so engineering sessions survive process restarts and can be listed
and inspected later.

Layout: ``<sessions_dir>/<task_id>.jsonl`` where each line is either
``{"type": "meta" | "event" | "report", ...}``. Recording is append-only
and never fabricates events; a missing report line means the process died
before REPORT.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import TaskEvent, TaskReport


@dataclass(frozen=True)
class SessionInfo:
    task_id: str
    path: str
    created_at: float
    objective: str
    final_status: str | None  # None => no report recorded (interrupted)
    event_count: int


class SessionRecorder:
    """Appends rollout lines for one or more tasks (thread-safe)."""

    def __init__(self, sessions_dir: str | os.PathLike[str]) -> None:
        self._dir = Path(sessions_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    @property
    def directory(self) -> Path:
        return self._dir

    def _path(self, task_id: str) -> Path:
        safe = "".join(c for c in task_id if c.isalnum() or c in "-_")[:80]
        if not safe:
            raise ValueError("invalid task id for session file")
        return self._dir / f"{safe}.jsonl"

    def _append(self, task_id: str, payload: dict[str, Any]) -> None:
        line = json.dumps(payload, default=str)
        with self._lock:
            with self._path(task_id).open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")

    # ------------------------------------------------------------------

    def start(self, task_id: str, objective: str, workspace_path: str) -> None:
        self._append(task_id, {
            "type": "meta",
            "task_id": task_id,
            "objective": objective[:2000],
            "workspace_path": workspace_path,
            "ts": time.time(),
        })

    def record_event(self, task_id: str, event: TaskEvent) -> None:
        self._append(task_id, {"type": "event", **event.model_dump()})

    def record_report(self, task_id: str, report: TaskReport) -> None:
        payload = report.model_dump()
        payload.pop("events", None)  # events are already on their own lines
        self._append(task_id, {"type": "report", **payload})

    # ------------------------------------------------------------------

    def list_sessions(self, *, limit: int = 50) -> list[SessionInfo]:
        infos: list[SessionInfo] = []
        for path in sorted(
            self._dir.glob("*.jsonl"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:limit]:
            info = self._read_info(path)
            if info is not None:
                infos.append(info)
        return infos

    def load(self, task_id: str) -> list[dict[str, Any]]:
        path = self._path(task_id)
        if not path.is_file():
            return []
        out: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                out.append({"type": "corrupt", "raw": line[:500]})
        return out

    def _read_info(self, path: Path) -> SessionInfo | None:
        objective = ""
        task_id = path.stem
        created_at = path.stat().st_mtime
        final_status: str | None = None
        events = 0
        try:
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                kind = data.get("type")
                if kind == "meta":
                    objective = data.get("objective", "")
                    task_id = data.get("task_id", task_id)
                    created_at = float(data.get("ts") or created_at)
                elif kind == "event":
                    events += 1
                elif kind == "report":
                    final_status = data.get("status")
        except OSError:
            return None
        return SessionInfo(
            task_id=task_id,
            path=str(path),
            created_at=created_at,
            objective=objective,
            final_status=final_status,
            event_count=events,
        )
