from tc_orchestrator.repository_intelligence import build_repository_snapshot, _safe_project_path


class FakeRead:
    def __init__(self, text, size=None, sha256="hash"):
        self.text = text
        self.total_size = size if size is not None else len(text)
        self.sha256 = sha256


class FakeStatus:
    branch = "main"
    clean = False
    entries = [
        ("app/main.py", "modified"),
        ("app/test_main.py", "untracked"),
        ("outside/secret.txt", "modified"),
    ]


class FakeClient:
    def git_status(self):
        return FakeStatus()

    def read_file(self, path, **kwargs):
        if path.endswith("package.json"):
            return FakeRead('{"name":"tc-app"}')
        if path.startswith("app/"):
            return FakeRead("print('ok')", size=12, sha256="abc")
        raise FileNotFoundError(path)


def test_snapshot_is_project_scoped_bounded_and_deterministic():
    snapshot = build_repository_snapshot(FakeClient(), "app", max_changed=1)
    assert snapshot.branch == "main"
    assert [x.path for x in snapshot.changed_files] == ["main.py"]
    assert [x.path for x in snapshot.manifests] == []
    assert "outside/secret.txt" not in snapshot.context_text


def test_manifest_discovery_for_project_root():
    class RootClient(FakeClient):
        def read_file(self, path, **kwargs):
            if path == "package.json":
                return FakeRead('{"name":"tc"}')
            return super().read_file(path, **kwargs)

    snapshot = build_repository_snapshot(RootClient(), "")
    assert any(x.path == "package.json" for x in snapshot.manifests)


def test_project_path_rejects_escape():
    try:
        _safe_project_path("a/../../etc")
    except ValueError:
        pass
    else:
        raise AssertionError("expected path escape rejection")
