"""SafeWorkspace: confinement, symlink escapes, CAS writes, patches."""

from __future__ import annotations

import os

import pytest

from tc_orchestrator.cybertron.workspace import SafeWorkspace, WorkspaceSecurityError


def test_read_and_ranged_read(workspace):
    res = workspace.read_file("src/app.py")
    assert "def add" in res.text
    ranged = workspace.read_file("src/app.py", start_line=2, max_lines=1)
    assert ranged.text.strip() == "return a + b"
    assert ranged.truncated


def test_path_traversal_rejected(workspace):
    for bad in ("../outside.txt", "src/../../etc/passwd", "/etc/passwd", "~/x", ".."):
        with pytest.raises(WorkspaceSecurityError):
            workspace.resolve(bad)


def test_symlink_escape_rejected(workspace, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside")
    secret = outside / "secret.txt"
    secret.write_text("host secret")
    link = workspace.root / "sneaky"
    os.symlink(secret, link)
    with pytest.raises(WorkspaceSecurityError):
        workspace.read_file("sneaky")


def test_symlinked_dir_escape_rejected(workspace, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside2")
    link = workspace.root / "ldir"
    os.symlink(outside, link, target_is_directory=True)
    # Writing THROUGH the symlinked dir must be rejected, even though the
    # final file does not exist yet.
    with pytest.raises(WorkspaceSecurityError):
        workspace.resolve("ldir/new.txt")


def test_cas_write_detects_concurrent_change(workspace):
    first = workspace.read_file("README.md")
    # Simulate concurrent modification.
    (workspace.root / "README.md").write_text("# changed\n")
    res = workspace.write_file("README.md", "clobber", expected_sha256=first.sha256)
    assert not res.written
    assert "compare-and-set" in (res.reason or "")
    assert (workspace.root / "README.md").read_text() == "# changed\n"


def test_atomic_write_and_mkdir(workspace):
    res = workspace.write_file("new/dir/file.txt", "hello")
    assert res.written
    assert (workspace.root / "new" / "dir" / "file.txt").read_text() == "hello"


def test_oversized_read_is_truncated(tmp_path):
    big = tmp_path / "big.txt"
    big.write_text("x" * 500)
    ws = SafeWorkspace(tmp_path, max_read_bytes=100)
    res = ws.read_file("big.txt")
    assert res.truncated
    assert res.total_size == 500
    assert len(res.text) == 100


def test_oversized_write_refused(tmp_path):
    ws = SafeWorkspace(tmp_path, max_write_bytes=10)
    res = ws.write_file("f.txt", "x" * 11)
    assert not res.written


def test_glob_and_grep(workspace):
    assert "src/app.py" in workspace.glob("*.py")
    hits = workspace.grep(r"def add", path_glob="*.py")
    assert any(h.path == "src/app.py" for h in hits)


def test_apply_patch_roundtrip(workspace):
    patch = (
        "--- a/src/app.py\n"
        "+++ b/src/app.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def add(a, b):\n"
        "-    return a + b\n"
        "+    return a + b + 0\n"
    )
    changed = workspace.apply_patch(patch)
    assert changed == ["src/app.py"]
    assert "a + b + 0" in workspace.read_file("src/app.py").text


def test_stale_patch_rejected(workspace):
    patch = (
        "--- a/src/app.py\n"
        "+++ b/src/app.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def add(a, b):\n"
        "-    return WRONG CONTEXT\n"
        "+    return 42\n"
    )
    with pytest.raises(ValueError, match="non-matching|context mismatch"):
        workspace.apply_patch(patch)
    # File untouched.
    assert "return a + b" in workspace.read_file("src/app.py").text


def test_patch_cannot_target_outside(workspace):
    patch = "--- a/../evil.txt\n+++ b/../evil.txt\n@@ -0,0 +1 @@\n+evil\n"
    with pytest.raises(WorkspaceSecurityError):
        workspace.apply_patch(patch)
