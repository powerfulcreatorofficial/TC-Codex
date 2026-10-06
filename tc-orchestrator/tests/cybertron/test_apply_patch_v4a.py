"""Codex V4A apply_patch format: add/update/delete/move, fuzz, safety."""

from __future__ import annotations

import pytest

from tc_orchestrator.cybertron.apply_patch import (
    PatchError,
    apply_any_patch,
    apply_v4a_patch,
    is_v4a_patch,
)
from tc_orchestrator.cybertron.workspace import WorkspaceSecurityError


def test_format_detection():
    assert is_v4a_patch("*** Begin Patch\n*** End Patch")
    assert not is_v4a_patch("--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b\n")


def test_add_file(workspace):
    patch = (
        "*** Begin Patch\n"
        "*** Add File: pkg/new_module.py\n"
        "+def hello():\n"
        "+    return 'hi'\n"
        "*** End Patch\n"
    )
    changed = apply_v4a_patch(workspace, patch)
    assert changed == ["pkg/new_module.py"]
    assert "def hello()" in workspace.read_file("pkg/new_module.py").text


def test_add_existing_file_rejected(workspace):
    patch = (
        "*** Begin Patch\n"
        "*** Add File: README.md\n"
        "+clobber\n"
        "*** End Patch\n"
    )
    with pytest.raises(PatchError, match="already exists"):
        apply_v4a_patch(workspace, patch)


def test_update_file_with_context(workspace):
    patch = (
        "*** Begin Patch\n"
        "*** Update File: src/app.py\n"
        "@@ def add(a, b):\n"
        "-    return a + b\n"
        "+    return a + b  # updated\n"
        "*** End Patch\n"
    )
    apply_v4a_patch(workspace, patch)
    assert "# updated" in workspace.read_file("src/app.py").text


def test_whitespace_fuzz_matching(workspace):
    # Patch context has trailing whitespace differences; Codex-style fuzz
    # should still match.
    patch = (
        "*** Begin Patch\n"
        "*** Update File: src/app.py\n"
        " def add(a, b):   \n"
        "-    return a + b  \n"
        "+    return b + a\n"
        "*** End Patch\n"
    )
    apply_v4a_patch(workspace, patch)
    assert "return b + a" in workspace.read_file("src/app.py").text


def test_delete_file(workspace):
    patch = "*** Begin Patch\n*** Delete File: README.md\n*** End Patch\n"
    changed = apply_v4a_patch(workspace, patch)
    assert changed == ["README.md"]
    assert not (workspace.root / "README.md").exists()


def test_move_file(workspace):
    patch = (
        "*** Begin Patch\n"
        "*** Update File: src/app.py\n"
        "*** Move to: src/calc.py\n"
        "@@ def add(a, b):\n"
        "-    return a + b\n"
        "+    return a + b\n"
        "*** End Patch\n"
    )
    changed = apply_v4a_patch(workspace, patch)
    assert set(changed) == {"src/app.py", "src/calc.py"}
    assert not (workspace.root / "src" / "app.py").exists()
    assert "def add" in workspace.read_file("src/calc.py").text


def test_end_of_file_marker(workspace):
    workspace.write_file("f.txt", "alpha\nbeta\nalpha\n")
    patch = (
        "*** Begin Patch\n"
        "*** Update File: f.txt\n"
        "@@\n"
        "-alpha\n"
        "+omega\n"
        "*** End of File\n"
        "*** End Patch\n"
    )
    apply_v4a_patch(workspace, patch)
    # Only the FINAL "alpha" replaced.
    assert workspace.read_file("f.txt").text == "alpha\nbeta\nomega\n"


def test_context_mismatch_leaves_files_untouched(workspace):
    original = workspace.read_file("src/app.py").text
    patch = (
        "*** Begin Patch\n"
        "*** Update File: src/app.py\n"
        "@@\n"
        "-THIS LINE DOES NOT EXIST\n"
        "+whatever\n"
        "*** End Patch\n"
    )
    with pytest.raises(PatchError, match="context not found"):
        apply_v4a_patch(workspace, patch)
    assert workspace.read_file("src/app.py").text == original


def test_multi_file_patch_is_all_or_nothing(workspace):
    original = workspace.read_file("src/app.py").text
    patch = (
        "*** Begin Patch\n"
        "*** Update File: src/app.py\n"
        "@@ def add(a, b):\n"
        "-    return a + b\n"
        "+    return 0\n"
        "*** Update File: src/app.py\n"
        "@@\n"
        "-NO SUCH CONTEXT\n"
        "+x\n"
        "*** End Patch\n"
    )
    with pytest.raises(PatchError):
        apply_v4a_patch(workspace, patch)
    # Planning failed before any write: first hunk also not applied.
    assert workspace.read_file("src/app.py").text == original


def test_traversal_rejected(workspace):
    patch = (
        "*** Begin Patch\n"
        "*** Add File: ../outside.txt\n"
        "+evil\n"
        "*** End Patch\n"
    )
    with pytest.raises(WorkspaceSecurityError):
        apply_v4a_patch(workspace, patch)


def test_dispatch_handles_both_formats(workspace):
    unified = (
        "--- a/src/app.py\n"
        "+++ b/src/app.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def add(a, b):\n"
        "-    return a + b\n"
        "+    return a + b + 0\n"
    )
    assert apply_any_patch(workspace, unified) == ["src/app.py"]
    v4a = (
        "*** Begin Patch\n"
        "*** Update File: src/app.py\n"
        "-    return a + b + 0\n"
        "+    return a + b\n"
        "*** End Patch\n"
    )
    assert apply_any_patch(workspace, v4a) == ["src/app.py"]
