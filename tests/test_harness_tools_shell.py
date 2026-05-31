from ai4science.harness.tools import shell, default_registry


def test_bash_runs_and_captures(tmp_path):
    (tmp_path / "f.txt").write_text("hi")
    out = shell.bash(tmp_path, cmd="cat f.txt")
    assert "hi" in out


def test_bash_reports_nonzero(tmp_path):
    out = shell.bash(tmp_path, cmd="exit 3")
    assert "exit code 3" in out.lower()


def test_default_registry_has_core_tools():
    reg = default_registry()
    assert set(["read", "write", "edit", "bash", "grep", "glob"]).issubset(set(reg.names()))
    assert reg.get("read").mutating is False
    assert reg.get("write").mutating is True
    assert reg.get("edit").mutating is True
    assert reg.get("bash").mutating is True
