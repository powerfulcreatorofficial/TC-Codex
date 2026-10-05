"""Evidence objects used to keep TC's completion claims auditable."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class EvidenceRecord:
    kind: str
    summary: str
    source: str
    verified: bool = False
    details: dict[str, str] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def compact(self) -> str:
        state = "verified" if self.verified else "unverified"
        return f"[{state}] {self.kind}: {self.summary} ({self.source})"
