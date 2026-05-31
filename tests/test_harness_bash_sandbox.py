from ai4science.harness.permissions import PermissionGate


def _gate(tmp_path, **kw):
    return PermissionGate(workspace=tmp_path, read_only=False, auto_yes=True, **kw)


def test_bash_blocks_protected_dir(tmp_path):
    g = _gate(tmp_path)
    ok, reason = g.allow("bash", {"cmd": "cat judge/secret.py"})
    assert ok is False and "sandbox" in reason.lower()


def test_bash_blocks_hidden_tests(tmp_path):
    ok, reason = _gate(tmp_path).allow("bash", {"cmd": "ls hidden_tests/"})
    assert ok is False and "sandbox" in reason.lower()


def test_bash_blocks_parent_escape(tmp_path):
    ok, reason = _gate(tmp_path).allow("bash", {"cmd": "cat ../../etc/passwd"})
    assert ok is False and "sandbox" in reason.lower()


def test_bash_allows_normal_command(tmp_path):
    ok, _ = _gate(tmp_path).allow("bash", {"cmd": "pytest -q && ls src"})
    assert ok is True
