"""Optional scientific adapters and capability reporting."""
from __future__ import annotations
from dataclasses import dataclass
from .catalog import discover


@dataclass(frozen=True)
class ScientificStatus:
    available: list[str]
    unavailable: list[str]


def status() -> ScientificStatus:
    caps = discover()
    return ScientificStatus(
        available=[c.name for c in caps if c.available],
        unavailable=[c.name for c in caps if not c.available],
    )
