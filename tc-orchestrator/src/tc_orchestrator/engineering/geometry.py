"""Trimesh adapter with graceful optional-dependency behavior."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MeshReport:
    path: str
    vertices: int
    faces: int
    watertight: bool
    volume: float | None
    area: float | None
    bounds: list[list[float]] | None


def analyze_mesh(path: str | Path) -> MeshReport:
    try:
        import trimesh
    except ImportError as exc:
        raise RuntimeError("trimesh is not installed; install the optional geometry extra") from exc
    mesh = trimesh.load_mesh(str(path), process=False)
    volume = float(mesh.volume) if hasattr(mesh, "volume") else None
    area = float(mesh.area) if hasattr(mesh, "area") else None
    bounds = mesh.bounds.tolist() if getattr(mesh, "bounds", None) is not None else None
    return MeshReport(
        path=str(path),
        vertices=int(len(mesh.vertices)),
        faces=int(len(mesh.faces)) if hasattr(mesh, "faces") else 0,
        watertight=bool(getattr(mesh, "is_watertight", False)),
        volume=volume,
        area=area,
        bounds=bounds,
    )
