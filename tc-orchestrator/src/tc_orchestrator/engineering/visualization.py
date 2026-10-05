"""PyVista adapter for engineering visualizations."""
from __future__ import annotations
from pathlib import Path


def render_mesh(path: str | Path, output: str | Path, *, width: int = 1200, height: int = 800) -> str:
    try:
        import pyvista as pv
    except ImportError as exc:
        raise RuntimeError("pyvista is not installed; install the optional visualization extra") from exc
    mesh = pv.read(str(path))
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plotter = pv.Plotter(off_screen=True, window_size=(width, height))
    plotter.add_mesh(mesh)
    plotter.show(screenshot=str(output_path), auto_close=True)
    return str(output_path)
