"""Optional engineering capability catalog.

The master repository remains runnable without heavyweight scientific packages.
When a package is installed, TC reports the capability as available and can
route tasks to the corresponding specialist.
"""
from __future__ import annotations

import importlib.util
from dataclasses import dataclass


@dataclass(frozen=True)
class Capability:
    name: str
    package: str
    purpose: str
    available: bool


CAPABILITIES = (
    Capability("3d_visualization", "pyvista", "3D rendering and mesh visualization", False),
    Capability("mesh_geometry", "trimesh", "mesh analysis, transforms, collision and mass properties", False),
    Capability("pinn_physics", "deepxde", "PINN/PDE workflows and scientific optimization", False),
    Capability("gpu_inference", "vllm", "high-throughput model serving", False),
    Capability("physics_ml", "physicsnemo", "physics-aware ML and simulation workloads", False),
)


def discover() -> list[Capability]:
    return [
        Capability(item.name, item.package, item.purpose, importlib.util.find_spec(item.package) is not None)
        for item in CAPABILITIES
    ]
