"""SafeWorkspace — confined filesystem access for Cybertron.

Every path is resolved against the workspace root and verified AFTER symlink
resolution (``realpath``), so neither ``../`` traversal nor symlinks placed
inside the repository can escape the root. Writes are atomic
(write-to-temp + rename) with optional SHA-256 compare-and-set.

This module is a filesystem-confinement layer, not a full sandbox; command
execution isolation lives in :mod:`.sandbox`.
"""

from __future__ import annotations

import fnmatch
import hashlib
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

_DEFAULT_MAX_READ_BYTES = 256 * 1024
_DEFAULT_MAX_WRITE_BYTES = 4 * 1024 * 1024
_SKIP_DIRS = {
    ".git",
    "node_modules",
    "target",
    "dist",
    "build",
    "__pycache__",
    ".venv",
    "venv",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".next",
    ".turbo",
    "coverage",
}


class WorkspaceSecurityError(Exception):
    """Raised on any attempted escape from the workspace root."""


@dataclass(frozen=True)
class ReadResult:
    path: str
    text: str
    sha256: str
    total_size: int
    truncated: bool
    start_line: int = 1
    end_line: int = 0


@dataclass(frozen=True)
class WriteResult:
    path: str
    sha256: str
    written: bool
    reason: str | None = None


@dataclass(frozen=True)
class GrepMatch:
    path: str
    line_no: int
    line: str


class SafeWorkspace:
    """Filesystem operations confined to a single real directory."""

    def __init__(
        self,
        root: str | os.PathLike[str],
        *,
        max_read_bytes: int = _DEFAULT_MAX_READ_BYTES,
        max_write_bytes: int = _DEFAULT_MAX_WRITE_BYTES,
    ) -> None:
        real = Path(os.path.realpath(root))
        if not real.is_dir():
            raise WorkspaceSecurityError(f"workspace root is not a directory: {root}")
        self._root = real
        self._max_read = max_read_bytes
        self._max_write = max_write_bytes

    @property
    def root(self) -> Path:
        return self._root

    # ------------------------------------------------------------------
    # path confinement
    # ------------------------------------------------------------------

    def resolve(self, rel_path: str, *, must_exist: bool = False) -> Path:
        """Resolve ``rel_path`` inside the root; reject absolute paths,
        traversal, and symlink escapes."""
        if not rel_path or rel_path.strip() == "":
            raise WorkspaceSecurityError("empty path")
        if os.path.isabs(rel_path) or rel_path.startswith("~"):
            raise WorkspaceSecurityError(f"absolute/home paths are not allowed: {rel_path}")
        norm = os.path.normpath(rel_path)
        if norm.startswith("..") or norm == "..":
            raise WorkspaceSecurityError(f"path escapes the workspace root: {rel_path}")
        candidate = self._root / norm
        # Resolve symlinks on the DEEPEST EXISTING ancestor so a symlinked
        # directory cannot smuggle the final component outside the root.
        probe = candidate
        while not probe.exists() and probe != self._root:
            probe = probe.parent
        real_probe = Path(os.path.realpath(probe))
        if real_probe != self._root and self._root not in real_probe.parents:
            raise WorkspaceSecurityError(f"path escapes the workspace root: {rel_path}")
        if candidate.exists():
            real = Path(os.path.realpath(candidate))
            if real != self._root and self._root not in real.parents:
                raise WorkspaceSecurityError(
                    f"symlink escape rejected: {rel_path} -> {real}"
                )
            return real
        if must_exist:
            raise FileNotFoundError(rel_path)
        return candidate

    def rel(self, path: Path) -> str:
        return str(path.relative_to(self._root)) if path != self._root else "."

    # ------------------------------------------------------------------
    # read / list / glob / grep
    # ------------------------------------------------------------------

    def read_file(
        self, rel_path: str, *, start_line: int = 1, max_lines: int = 0
    ) -> ReadResult:
        p = self.resolve(rel_path, must_exist=True)
        if not p.is_file():
            raise WorkspaceSecurityError(f"not a regular file: {rel_path}")
        data = p.read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        total = len(data)
        truncated = False
        if total > self._max_read:
            data = data[: self._max_read]
            truncated = True
        text = data.decode("utf-8", errors="replace")
        if start_line > 1 or max_lines > 0:
            lines = text.splitlines(keepends=True)
            start_idx = max(0, start_line - 1)
            end_idx = start_idx + max_lines if max_lines > 0 else len(lines)
            selected = lines[start_idx:end_idx]
            truncated = truncated or end_idx < len(lines) or start_idx > 0
            text = "".join(selected)
            return ReadResult(
                path=rel_path,
                text=text,
                sha256=sha,
                total_size=total,
                truncated=truncated,
                start_line=start_idx + 1,
                end_line=min(end_idx, len(lines)),
            )
        return ReadResult(
            path=rel_path, text=text, sha256=sha, total_size=total, truncated=truncated
        )

    def list_dir(self, rel_path: str = ".", *, max_entries: int = 500) -> list[str]:
        p = self.resolve(rel_path, must_exist=True)
        if not p.is_dir():
            raise WorkspaceSecurityError(f"not a directory: {rel_path}")
        out: list[str] = []
        for entry in sorted(p.iterdir()):
            suffix = "/" if entry.is_dir() else ""
            out.append(self.rel(entry) + suffix)
            if len(out) >= max_entries:
                out.append(f"...[truncated at {max_entries} entries]")
                break
        return out

    def _walk(self, max_files: int = 20_000):
        count = 0
        for dirpath, dirnames, filenames in os.walk(self._root, followlinks=False):
            dirnames[:] = sorted(d for d in dirnames if d not in _SKIP_DIRS)
            for fname in sorted(filenames):
                full = Path(dirpath) / fname
                if full.is_symlink():
                    continue
                count += 1
                if count > max_files:
                    return
                yield full

    def glob(self, pattern: str, *, max_results: int = 500) -> list[str]:
        out: list[str] = []
        for full in self._walk():
            rel = self.rel(full)
            if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(full.name, pattern):
                out.append(rel)
                if len(out) >= max_results:
                    break
        return out

    def grep(
        self,
        pattern: str,
        *,
        path_glob: str = "*",
        max_matches: int = 200,
        regex: bool = True,
        max_file_bytes: int = 1_000_000,
    ) -> list[GrepMatch]:
        matcher = re.compile(pattern) if regex else None
        out: list[GrepMatch] = []
        for full in self._walk():
            rel = self.rel(full)
            if not (fnmatch.fnmatch(rel, path_glob) or fnmatch.fnmatch(full.name, path_glob)):
                continue
            try:
                if full.stat().st_size > max_file_bytes:
                    continue
                text = full.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if "\x00" in text[:1024]:
                continue  # binary
            for i, line in enumerate(text.splitlines(), start=1):
                hit = matcher.search(line) if matcher else (pattern in line)
                if hit:
                    out.append(GrepMatch(path=rel, line_no=i, line=line.strip()[:400]))
                    if len(out) >= max_matches:
                        return out
        return out

    # ------------------------------------------------------------------
    # write / patch
    # ------------------------------------------------------------------

    def write_file(
        self, rel_path: str, content: str, *, expected_sha256: str | None = None
    ) -> WriteResult:
        """Atomic write with optional compare-and-set on the current hash."""
        encoded = content.encode("utf-8")
        if len(encoded) > self._max_write:
            return WriteResult(
                path=rel_path,
                sha256="",
                written=False,
                reason=f"content exceeds max write size ({self._max_write} bytes)",
            )
        p = self.resolve(rel_path)
        if expected_sha256 is not None:
            current = p.read_bytes() if p.is_file() else b""
            current_sha = hashlib.sha256(current).hexdigest()
            if current_sha != expected_sha256:
                return WriteResult(
                    path=rel_path,
                    sha256=current_sha,
                    written=False,
                    reason="compare-and-set mismatch: file changed since read",
                )
        p.parent.mkdir(parents=True, exist_ok=True)
        # The parent dir itself must still be inside the root after mkdir.
        real_parent = Path(os.path.realpath(p.parent))
        if real_parent != self._root and self._root not in real_parent.parents:
            raise WorkspaceSecurityError(f"parent escapes workspace: {rel_path}")
        fd, tmp_name = tempfile.mkstemp(dir=real_parent, prefix=".tc-write-")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(encoded)
            os.replace(tmp_name, p)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
        return WriteResult(
            path=rel_path, sha256=hashlib.sha256(encoded).hexdigest(), written=True
        )

    def apply_patch(self, patch_text: str) -> list[str]:
        """Apply a minimal unified diff. Returns the list of changed paths.

        Supports multi-file unified diffs with ``---``/``+++`` headers and
        ``@@`` hunks. Context must match exactly; mismatches raise ValueError
        so a stale patch never silently corrupts a file.
        """
        changed: list[str] = []
        for file_patch in _split_file_patches(patch_text):
            target = file_patch.target_path
            # Safety: resolve (and thereby validate) the target path.
            p = self.resolve(target)
            original = p.read_text(encoding="utf-8") if p.is_file() else ""
            patched = _apply_hunks(original, file_patch.hunks, target)
            self.write_file(target, patched)
            changed.append(target)
        return changed

    def changed_file_digest(self, rel_path: str) -> str | None:
        try:
            p = self.resolve(rel_path, must_exist=True)
        except (FileNotFoundError, WorkspaceSecurityError):
            return None
        if not p.is_file():
            return None
        return hashlib.sha256(p.read_bytes()).hexdigest()

    def delete_file(self, rel_path: str) -> bool:
        """Delete a regular file inside the workspace (never directories,
        never through symlinks)."""
        p = self.resolve(rel_path, must_exist=True)
        if not p.is_file():
            raise WorkspaceSecurityError(f"not a regular file: {rel_path}")
        p.unlink()
        return True

    def exists(self, rel_path: str) -> bool:
        try:
            return self.resolve(rel_path).exists()
        except WorkspaceSecurityError:
            return False


# ----------------------------------------------------------------------
# unified diff parsing / application (no external deps)
# ----------------------------------------------------------------------


@dataclass
class _Hunk:
    old_start: int
    lines: list[str]


@dataclass
class _FilePatch:
    target_path: str
    hunks: list[_Hunk]


def _clean_diff_path(raw: str) -> str:
    raw = raw.strip().split("\t")[0]
    for prefix in ("a/", "b/"):
        if raw.startswith(prefix):
            return raw[len(prefix):]
    return raw


def _split_file_patches(patch_text: str) -> list[_FilePatch]:
    patches: list[_FilePatch] = []
    current: _FilePatch | None = None
    hunk: _Hunk | None = None
    for line in patch_text.splitlines():
        if line.startswith("--- "):
            continue
        if line.startswith("+++ "):
            target = _clean_diff_path(line[4:])
            if target == "/dev/null":
                raise ValueError("file deletion via patch is not supported; use git tools")
            current = _FilePatch(target_path=target, hunks=[])
            patches.append(current)
            hunk = None
            continue
        if line.startswith("@@"):
            if current is None:
                raise ValueError("hunk before file header in patch")
            m = re.match(r"@@ -(\d+)(?:,\d+)? \+\d+(?:,\d+)? @@", line)
            if not m:
                raise ValueError(f"malformed hunk header: {line}")
            hunk = _Hunk(old_start=int(m.group(1)), lines=[])
            current.hunks.append(hunk)
            continue
        if hunk is not None and (line.startswith((" ", "+", "-")) or line == ""):
            hunk.lines.append(line if line else " ")
            continue
    if not patches:
        raise ValueError("no file patches found in diff")
    return patches


def _apply_hunks(original: str, hunks: list[_Hunk], target: str) -> str:
    lines = original.splitlines()
    result: list[str] = []
    cursor = 0  # index into `lines`
    for hunk in hunks:
        start = hunk.old_start - 1 if hunk.old_start > 0 else 0
        if start < cursor:
            raise ValueError(f"overlapping hunks in patch for {target}")
        result.extend(lines[cursor:start])
        cursor = start
        for hline in hunk.lines:
            tag, body = hline[0], hline[1:]
            if tag == " ":
                if cursor >= len(lines) or lines[cursor] != body:
                    raise ValueError(
                        f"patch context mismatch in {target} at line {cursor + 1}"
                    )
                result.append(body)
                cursor += 1
            elif tag == "-":
                if cursor >= len(lines) or lines[cursor] != body:
                    raise ValueError(
                        f"patch removes non-matching line in {target} at line {cursor + 1}"
                    )
                cursor += 1
            elif tag == "+":
                result.append(body)
    result.extend(lines[cursor:])
    text = "\n".join(result)
    if original.endswith("\n") or not original:
        text += "\n"
    return text
