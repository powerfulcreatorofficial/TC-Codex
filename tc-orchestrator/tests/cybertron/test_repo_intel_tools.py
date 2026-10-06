"""Repository intelligence and the capability-levelled toolset."""

from __future__ import annotations

from tc_orchestrator.cybertron.gitsafe import SafeGit
from tc_orchestrator.cybertron.models import CapabilityLevel
from tc_orchestrator.cybertron.repo_intel import RepoIntelligence
from tc_orchestrator.cybertron.sandbox import LocalProcessSandbox
from tc_orchestrator.cybertron.tools import CybertronToolset
from tc_orchestrator.cybertron.workspace import SafeWorkspace


def make_intel(root) -> RepoIntelligence:
    sandbox = LocalProcessSandbox(root)
    return RepoIntelligence(SafeWorkspace(root), SafeGit(sandbox))


def make_toolset(root, audit=None) -> CybertronToolset:
    ws = SafeWorkspace(root)
    sandbox = LocalProcessSandbox(root)
    git = SafeGit(sandbox)
    return CybertronToolset(ws, sandbox, git, RepoIntelligence(ws, git), audit_hook=audit)


def test_repo_model_detects_stack(git_ws):
    model = make_intel(git_ws).build_model()
    assert model.languages.get("python", 0) >= 2
    assert "pyproject.toml" in model.manifests
    assert "python" in model.build_systems
    assert any("pytest" in c for c in model.test_commands)
    assert model.git_branch == "main"
    assert model.git_clean is True
    text = model.context_text()
    assert "UNTRUSTED DATA" in text


def test_find_symbols(ws_root):
    intel = make_intel(ws_root)
    syms = intel.find_symbols("add")
    assert any(s.name == "add" and s.path == "src/app.py" for s in syms)


def test_discover_tests_for_changed_file(ws_root):
    intel = make_intel(ws_root)
    tests = intel.discover_tests_for(["src/app.py"])
    assert "tests/test_app.py" in tests


def test_toolset_levels_and_audit(git_ws):
    audits = []
    ts = make_toolset(git_ws, audit=lambda n, lv, a, o: audits.append((n, lv, o.ok)))
    assert ts.level_of("read_file") == CapabilityLevel.L0
    assert ts.level_of("grep") == CapabilityLevel.L1
    assert ts.level_of("apply_patch") == CapabilityLevel.L2
    assert ts.level_of("run_check") == CapabilityLevel.L3
    assert ts.level_of("run_command") == CapabilityLevel.L4
    assert ts.level_of("git_commit") == CapabilityLevel.L5

    out = ts.execute("read_file", {"path": "src/app.py"})
    assert out.ok and "def add" in out.output
    assert audits and audits[-1][0] == "read_file"


def test_toolset_structured_failure(git_ws):
    ts = make_toolset(git_ws)
    out = ts.execute("run_check", {"argv": ["false"]})
    assert not out.ok
    assert out.exit_code == 1
    out2 = ts.execute("read_file", {"path": "../etc/passwd"})
    assert not out2.ok and "security rejection" in (out2.error or "")
    out3 = ts.execute("no_such_tool", {})
    assert not out3.ok and "unknown tool" in (out3.error or "")


def test_toolset_audit_never_logs_content(git_ws):
    audits = []
    ts = make_toolset(git_ws, audit=lambda n, lv, a, o: audits.append(a))
    ts.execute("write_file", {"path": "x.txt", "content": "SECRET-CONTENT"})
    assert all("SECRET-CONTENT" not in str(a) for a in audits)
    assert audits[-1]["content_bytes"] == len("SECRET-CONTENT")


def test_git_tools_work(git_ws):
    ts = make_toolset(git_ws)
    st = ts.execute("git_state", {})
    assert st.ok and st.data["is_repo"] is True
    br = ts.execute("git_create_branch", {"name": "cybertron/test"})
    assert br.ok
    (git_ws / "f.txt").write_text("x\n")
    cm = ts.execute("git_commit", {"message": "add f", "paths": ["f.txt"]})
    assert cm.ok
    diff = ts.execute("git_diff", {})
    assert diff.ok
