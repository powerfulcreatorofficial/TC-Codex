"""Codex-compatible ``apply_patch`` (V4A) patch format for Cybertron.

Implements the envelope format used by Codex's apply_patch tool:

    *** Begin Patch
    *** Add File: path/new.py
    +line one
    *** Update File: path/existing.py
    *** Move to: path/renamed.py          (optional)
    @@ optional locator context
     context line
    -removed line
    +added line
    *** Delete File: path/old.py
    *** End Patch

Matching semantics follow Codex: hunk context is located by exact match
first, then with trailing-whitespace-stripped lines, then fully stripped
lines (whitespace fuzz). ``*** End of File`` pins a hunk to the file end.

All paths are validated through :class:`SafeWorkspace` (relative only, no
traversal, no symlink escapes). A context mismatch raises and leaves every
file untouched — application is two-phase (parse+plan, then write).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .workspace import SafeWorkspace

BEGIN = "*** Begin Patch"
END = "*** End Patch"
ADD = "*** Add File: "
UPDATE = "*** Update File: "
DELETE = "*** Delete File: "
MOVE = "*** Move to: "
EOF_MARK = "*** End of File"


class PatchError(ValueError):
    """Malformed patch or context that does not match the file."""


def is_v4a_patch(text: str) -> bool:
    return text.lstrip().startswith(BEGIN)


@dataclass
class _Chunk:
    """One contiguous replacement inside an Update section."""

    context: str  # the '@@' locator text, may be empty
    old_lines: list[str] = field(default_factory=list)  # context + '-' lines
    new_lines: list[str] = field(default_factory=list)  # context + '+' lines
    is_eof: bool = False


@dataclass
class _Op:
    kind: str  # add | update | delete
    path: str
    move_to: str | None = None
    content: str | None = None  # for add
    chunks: list[_Chunk] = field(default_factory=list)


def _parse(text: str) -> list[_Op]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != BEGIN:
        raise PatchError("patch must start with '*** Begin Patch'")
    if not any(line.strip() == END for line in lines):
        raise PatchError("patch must end with '*** End Patch'")

    ops: list[_Op] = []
    op: _Op | None = None
    chunk: _Chunk | None = None
    i = 1
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped == END:
            break
        if line.startswith(ADD):
            op = _Op(kind="add", path=line[len(ADD):].strip(), content="")
            ops.append(op)
            chunk = None
        elif line.startswith(DELETE):
            op = _Op(kind="delete", path=line[len(DELETE):].strip())
            ops.append(op)
            chunk = None
        elif line.startswith(UPDATE):
            op = _Op(kind="update", path=line[len(UPDATE):].strip())
            ops.append(op)
            chunk = None
        elif line.startswith(MOVE):
            if op is None or op.kind != "update":
                raise PatchError("'*** Move to:' outside an Update section")
            op.move_to = line[len(MOVE):].strip()
        elif stripped == EOF_MARK:
            if chunk is None:
                raise PatchError("'*** End of File' outside a hunk")
            chunk.is_eof = True
        elif line.startswith("@@"):
            if op is None or op.kind != "update":
                raise PatchError("hunk outside an Update section")
            chunk = _Chunk(context=line[2:].strip())
            op.chunks.append(chunk)
        elif op is not None and op.kind == "add":
            if not line.startswith("+"):
                raise PatchError(f"Add File lines must start with '+': {line!r}")
            op.content = (op.content or "") + line[1:] + "\n"
        elif op is not None and op.kind == "update":
            if chunk is None:
                # Codex allows hunk bodies to start without an explicit '@@'.
                chunk = _Chunk(context="")
                op.chunks.append(chunk)
            if line.startswith("+"):
                chunk.new_lines.append(line[1:])
            elif line.startswith("-"):
                chunk.old_lines.append(line[1:])
            elif line.startswith(" ") or line == "":
                body = line[1:] if line.startswith(" ") else ""
                chunk.old_lines.append(body)
                chunk.new_lines.append(body)
            else:
                raise PatchError(f"unexpected line in Update section: {line!r}")
        else:
            raise PatchError(f"unexpected line outside any section: {line!r}")
        i += 1

    if not ops:
        raise PatchError("patch contains no file operations")
    return ops


def _find(haystack: list[str], needle: list[str], start: int, *, eof: bool) -> int:
    """Locate ``needle`` in ``haystack`` with Codex-style whitespace fuzz.

    Returns the match index or -1. ``eof`` pins the search to the file end.
    """
    if not needle:
        return start
    canon_funcs = (
        lambda s: s,
        lambda s: s.rstrip(),
        lambda s: s.strip(),
    )
    for canon in canon_funcs:
        hay = [canon(x) for x in haystack]
        ndl = [canon(x) for x in needle]
        if eof:
            idx = len(haystack) - len(needle)
            if idx >= start and hay[idx: idx + len(ndl)] == ndl:
                return idx
            continue
        for idx in range(start, len(hay) - len(ndl) + 1):
            if hay[idx: idx + len(ndl)] == ndl:
                return idx
    return -1


def _apply_update(original: str, op: _Op) -> str:
    lines = original.splitlines()
    cursor = 0
    for chunk in op.chunks:
        # Optional '@@' locator narrows the search start.
        if chunk.context:
            loc = _find(lines, [chunk.context], cursor, eof=False)
            if loc >= 0:
                cursor = loc + 1
        idx = _find(lines, chunk.old_lines, cursor, eof=chunk.is_eof)
        if idx < 0:
            preview = "\n".join(chunk.old_lines[:3])
            raise PatchError(
                f"context not found in {op.path} (hunk near {chunk.context!r}):\n{preview}"
            )
        lines[idx: idx + len(chunk.old_lines)] = chunk.new_lines
        cursor = idx + len(chunk.new_lines)
    text = "\n".join(lines)
    if original.endswith("\n") or not original:
        text += "\n"
    return text


def apply_v4a_patch(workspace: SafeWorkspace, patch_text: str) -> list[str]:
    """Apply a V4A patch atomically-ish: fully planned before any write.

    Returns the list of affected paths (including deletions/moves).
    """
    ops = _parse(patch_text)

    # Phase 1: plan every write with validation; nothing touched on error.
    planned_writes: list[tuple[str, str]] = []
    planned_deletes: list[str] = []
    affected: list[str] = []
    for op in ops:
        if op.kind == "add":
            if workspace.exists(op.path) and workspace.resolve(op.path).is_file():
                raise PatchError(f"Add File target already exists: {op.path}")
            workspace.resolve(op.path)  # validates confinement
            planned_writes.append((op.path, op.content or ""))
            affected.append(op.path)
        elif op.kind == "delete":
            p = workspace.resolve(op.path, must_exist=True)
            if not p.is_file():
                raise PatchError(f"Delete File target is not a file: {op.path}")
            planned_deletes.append(op.path)
            affected.append(op.path)
        elif op.kind == "update":
            original = workspace.read_file(op.path).text
            updated = _apply_update(original, op)
            target = op.move_to or op.path
            workspace.resolve(target)  # validates confinement (move target too)
            planned_writes.append((target, updated))
            if op.move_to:
                planned_deletes.append(op.path)
                affected.extend([op.path, op.move_to])
            else:
                affected.append(op.path)

    # Phase 2: perform the writes.
    for path, content in planned_writes:
        res = workspace.write_file(path, content)
        if not res.written:
            raise PatchError(f"write refused for {path}: {res.reason}")
    for path in planned_deletes:
        workspace.delete_file(path)

    seen: set[str] = set()
    return [p for p in affected if not (p in seen or seen.add(p))]


def apply_any_patch(workspace: SafeWorkspace, patch_text: str) -> list[str]:
    """Dispatch between Codex V4A format and classic unified diff."""
    if is_v4a_patch(patch_text):
        return apply_v4a_patch(workspace, patch_text)
    return workspace.apply_patch(patch_text)
