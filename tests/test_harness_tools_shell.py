import time

from ai4science.harness.tools import shell, default_registry


def test_bash_runs_and_captures(tmp_path):
    (tmp_path / "f.txt").write_text("hi")
    out = shell.bash(tmp_path, cmd="cat f.txt")
    assert "hi" in out


def test_bash_stdin_is_isolated_from_parent_tty(tmp_path):
    """A bash subprocess must NOT inherit the parent's stdin: otherwise a
    `read` (or any isatty()-probing tool) inside the command would either hang
    forever or race the TUI's prompt_toolkit reader for the user's keystrokes,
    eating them and corrupting the TTY mode on exit (the symptom that
    backspace echoes ^R and Ctrl+C echoes literal ^C).

    We assert by running a `read` and proving it returns FAST with EOF — only
    possible when stdin is /dev/null. Without the fix this would hang until
    the bash timeout (120 s default), so a generous 5 s ceiling here is still
    >20x faster than the broken case."""
    t0 = time.monotonic()
    # `read` returns non-zero on EOF (no input). Echoing afterwards proves the
    # script ran, didn't block, and saw EOF on stdin.
    out = shell.bash(tmp_path, cmd="read x; echo done:$?")
    elapsed = time.monotonic() - t0
    assert elapsed < 5.0, f"bash blocked on stdin for {elapsed:.1f}s (stdin not isolated)"
    assert "done:" in out, out


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
