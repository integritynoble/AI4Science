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


def test_bash_blocks_chained_no_space_escape(tmp_path):
    """Separators ;|& directly before ../ or a protected dir (no space) must block."""
    g = _gate(tmp_path)
    for bad in ["cat /etc/fstab;../../etc/shadow", "ls|cat judge/x", "true&&hidden_tests/t"]:
        ok, reason = g.allow("bash", {"cmd": bad})
        assert ok is False and "sandbox" in reason.lower(), bad


def test_bash_still_allows_normal_chains(tmp_path):
    """Normal chained commands (no protected/parent refs) still pass."""
    g = _gate(tmp_path)
    for good in ["ls && pytest -q", "echo hi | cat", "git add . && git commit -m x"]:
        ok, _ = g.allow("bash", {"cmd": good})
        assert ok is True, good
