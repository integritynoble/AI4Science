from pathlib import Path
from ai4science.harness.permissions import PermissionGate, SandboxError


def test_read_only_blocks_mutating(tmp_path):
    gate = PermissionGate(workspace=tmp_path, read_only=True, auto_yes=False)
    ok, reason = gate.allow("edit", {"path": "a.py", "old": "x", "new": "y"})
    assert ok is False and "read-only" in reason.lower()


def test_read_only_allows_read(tmp_path):
    gate = PermissionGate(workspace=tmp_path, read_only=True, auto_yes=False)
    ok, _ = gate.allow("read", {"path": "a.py"})
    assert ok is True


def test_auto_yes_allows_mutating(tmp_path):
    gate = PermissionGate(workspace=tmp_path, read_only=False, auto_yes=True)
    ok, _ = gate.allow("write", {"path": "a.py", "content": "x"})
    assert ok is True


def test_prompt_uses_confirm_callback(tmp_path):
    answers = iter([True, False])
    gate = PermissionGate(workspace=tmp_path, read_only=False, auto_yes=False,
                          confirm=lambda name, args, preview: next(answers))
    ok1, _ = gate.allow("write", {"path": "a.py", "content": "x"})
    ok2, _ = gate.allow("bash", {"cmd": "rm -rf /"})
    assert ok1 is True and ok2 is False


def test_sandbox_blocks_protected_paths(tmp_path):
    gate = PermissionGate(workspace=tmp_path, read_only=False, auto_yes=True)
    for bad in ["judge/x.py", "hidden_tests/t.py", "../escape.py"]:
        ok, reason = gate.allow("write", {"path": bad, "content": "x"})
        assert ok is False and "sandbox" in reason.lower()
