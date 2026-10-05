"""Evidence-first repository snapshotting through the WorkspaceClient only."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .grpc_client import WorkspaceClient

_COMMON_FILES = (
    "README.md",
    "README.txt",
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "Cargo.toml",
    "go.mod",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "tsconfig.json",
    "vite.config.ts",
    "next.config.js",
    "next.config.mjs",
)
_TEXT_SUFFIXES = (".md", ".txt", ".json", ".toml", ".yaml", ".yml", ".py", ".ts", ".tsx", ".js", ".jsx", ".rs", ".go", ".sh", ".css", ".scss", ".env.example")


@dataclass(frozen=True)
class RepositoryFile:
    path: str
    status: str
    size: int | None = None
    sha256: str | None = None
    preview: str | None = None


@dataclass(frozen=True)
class RepositorySnapshot:
    project_path: str
    branch: str | None
    clean: bool | None
    changed_files: tuple[RepositoryFile, ...]
    manifests: tuple[RepositoryFile, ...]

    @property
    def context_text(self) -> str:
        lines = [
            "[repository_snapshot]",
            f"project_path={self.project_path or '.'}",
            f"branch={self.branch or 'unknown'}",
            f"clean={self.clean if self.clean is not None else 'unknown'}",
        ]
        if self.changed_files:
            lines.append("changed_files:")
            for item in self.changed_files:
                bits = [f"- {item.status} {item.path}"]
                if item.size is not None:
                    bits.append(f"size={item.size}")
                if item.sha256:
                    bits.append(f"sha256={item.sha256}")
                lines.append(" | ".join(bits))
        else:
            lines.append("changed_files: none observed")
        if self.manifests:
            lines.append("manifests:")
            for item in self.manifests:
                lines.append(
                    f"- {item.path} size={item.size if item.size is not None else 'unknown'} "
                    f"sha256={item.sha256 or 'unknown'}"
                )
                if item.preview:
                    lines.append("  preview=" + item.preview.replace("\n", " "))
        return "\n".join(lines)


def _safe_project_path(project_path: str | None) -> str:
    value = (project_path or "").strip().replace("\\", "/")
    while value.startswith("./"):
        value = value[2:]
    if value in ("", "."):
        return ""
    parts = [part for part in value.split("/") if part]
    if any(part == ".." for part in parts):
        raise ValueError("project path escapes workspace")
    return "/".join(parts)


def _under_project(path: str, project_path: str) -> bool:
    if not project_path:
        return True
    return path == project_path or path.startswith(project_path + "/")


def _relative_to_project(path: str, project_path: str) -> str:
    if not project_path:
        return path
    if path == project_path:
        return "."
    prefix = project_path + "/"
    return path[len(prefix):] if path.startswith(prefix) else path


def build_repository_snapshot(
    client: WorkspaceClient,
    project_path: str | None,
    *,
    max_changed: int = 12,
    max_manifest_bytes: int = 2400,
) -> RepositorySnapshot:
    project = _safe_project_path(project_path)
    status = None
    try:
        status = client.git_status()
    except Exception:
        status = None

    changed: list[RepositoryFile] = []
    if status is not None:
        for path, state in status.entries:
            if not _under_project(path, project):
                continue
            changed.append(RepositoryFile(path=_relative_to_project(path, project), status=state))
        changed.sort(key=lambda x: (x.path, x.status))
        changed = changed[: max(0, min(max_changed, 50))]

    enriched: list[RepositoryFile] = []
    for item in changed:
        full = f"{project}/{item.path}" if project else item.path
        try:
            result = client.read_file(full)
            enriched.append(RepositoryFile(
                path=item.path,
                status=item.status,
                size=result.total_size,
                sha256=result.sha256,
            ))
        except Exception:
            enriched.append(item)

    manifests: list[RepositoryFile] = []
    for name in _COMMON_FILES:
        if project and not _under_project(name, project):
            continue
        full = f"{project}/{name}" if project else name
        try:
            result = client.read_file(full, length=max_manifest_bytes)
            preview = result.text if name.endswith(_TEXT_SUFFIXES) else None
            manifests.append(RepositoryFile(
                path=name,
                status="present",
                size=result.total_size,
                sha256=result.sha256,
                preview=preview[:max_manifest_bytes] if preview else None,
            ))
        except Exception:
            continue
    manifests.sort(key=lambda x: x.path)

    return RepositorySnapshot(
        project_path=project,
        branch=status.branch if status is not None else None,
        clean=status.clean if status is not None else None,
        changed_files=tuple(enriched),
        manifests=tuple(manifests),
    )
