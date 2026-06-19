from pathlib import Path
from ai4science.harness.permissions import PermissionGate, SandboxError, _preview


def test_write_preview_is_clean_listing_not_diff():
    """A new-file WRITE renders as a numbered listing (Claude Code parity), NOT
    a unified diff with '+' on every line."""
    content = "\n".join(f"line {i}" for i in range(1, 249))
    out = _preview("write", {"path": "code/x.py", "content": content})
    assert "--- a/" not in out and "+++ b/" not in out and "@@" not in out
    assert out.startswith("Write code/x.py  (248 lines)")
    assert "+208 more lines" in out
    assert "\x1b[" in out  # syntax-highlighted listing (Claude-Code-style), not plain


def test_edit_preview_still_shows_diff():
    out = _preview("edit", {"path": "x.py", "old": "alpha", "new": "beta"})
    assert "-alpha" in out and "+beta" in out


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
