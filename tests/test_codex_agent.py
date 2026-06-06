"""CodexAgent tests with mocked subprocess (no real codex CLI required)."""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

import ai4science.agents.codex_agent as ca
from ai4science.agents.codex_agent import CodexAgent, _build_codex_command, _codex_executable


# ─── Command construction ────────────────────────────────────────────


def test_default_codex_command_uses_exec_with_cd(tmp_path):
    cmd = _build_codex_command(tmp_path)
    assert cmd[0] == _codex_executable()   # resolved binary (codex.cmd on Windows)
    assert cmd[1] == "exec"
    assert "--cd" in cmd
    cd_index = cmd.index("--cd")
    assert Path(cmd[cd_index + 1]).resolve() == tmp_path.resolve()


def test_env_override_replaces_default(monkeypatch, tmp_path):
    monkeypatch.setenv("AI4SCIENCE_CODEX_CMD", "codex --quiet")
    cmd = _build_codex_command(tmp_path)
    # leading bare `codex` is resolved to the real executable (Windows-safe)
    assert cmd == [_codex_executable(), "--quiet"]


def test_codex_executable_prefers_cmd_on_windows(monkeypatch):
    """WinError 193 fix: on Windows resolve codex.cmd, not the bare npm shim."""
    monkeypatch.setattr(ca.os, "name", "nt")
    monkeypatch.setattr(ca.shutil, "which",
                        lambda n: r"C:\npm\codex.cmd" if n == "codex.cmd" else r"C:\npm\codex")
    assert _codex_executable() == r"C:\npm\codex.cmd"


def test_codex_executable_plain_on_posix(monkeypatch):
    monkeypatch.setattr(ca.os, "name", "posix")
    monkeypatch.setattr(ca.shutil, "which",
                        lambda n: "/usr/bin/codex" if n == "codex" else None)
    assert _codex_executable() == "/usr/bin/codex"


def test_env_override_with_trailing_cd_flag_appends_workspace(monkeypatch, tmp_path):
    monkeypatch.setenv("AI4SCIENCE_CODEX_CMD", "codex exec -C")
    cmd = _build_codex_command(tmp_path)
    assert cmd[-1] == str(tmp_path.resolve())


# ─── Subprocess wiring ───────────────────────────────────────────────


def _make_completed(returncode: int, stdout: str = "", stderr: str = ""):
    """Helper to build a CompletedProcess result for monkeypatch."""
    m = MagicMock(spec=subprocess.CompletedProcess)
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = stderr
    return m


def test_codex_returns_ok_on_clean_success(monkeypatch, tmp_path):
    monkeypatch.setattr("ai4science.agents.codex_agent.shutil.which",
                        lambda _name: "/usr/bin/codex")
    monkeypatch.setattr(
        "ai4science.agents.codex_agent.subprocess.run",
        lambda *a, **k: _make_completed(0,
            stdout="Here is your draft principle.md:\n---\nartifact_type: principle\n..."),
    )
    r = CodexAgent().run_task("draft a CT principle", tmp_path, [])
    assert r.status == "ok"
    assert "principle" in r.message.lower()


def test_codex_returns_error_on_nonzero_exit(monkeypatch, tmp_path):
    monkeypatch.setattr("ai4science.agents.codex_agent.shutil.which",
                        lambda _name: "/usr/bin/codex")
    monkeypatch.setattr(
        "ai4science.agents.codex_agent.subprocess.run",
        lambda *a, **k: _make_completed(1, stderr="auth required: run `codex login`"),
    )
    r = CodexAgent().run_task("draft", tmp_path, [])
    assert r.status == "error"
    assert "auth required" in r.message
    assert "exited with code 1" in r.message


def test_codex_returns_error_on_empty_stdout(monkeypatch, tmp_path):
    """Empty stdout (with zero return code) is suspicious — surface it."""
    monkeypatch.setattr("ai4science.agents.codex_agent.shutil.which",
                        lambda _name: "/usr/bin/codex")
    monkeypatch.setattr(
        "ai4science.agents.codex_agent.subprocess.run",
        lambda *a, **k: _make_completed(0, stdout=""),
    )
    r = CodexAgent().run_task("draft", tmp_path, [])
    assert r.status == "error"
    assert "empty stdout" in r.message.lower()


def test_codex_returns_error_on_timeout(monkeypatch, tmp_path):
    monkeypatch.setattr("ai4science.agents.codex_agent.shutil.which",
                        lambda _name: "/usr/bin/codex")
    def _raise_timeout(*a, **k):
        raise subprocess.TimeoutExpired(cmd="codex", timeout=180)
    monkeypatch.setattr("ai4science.agents.codex_agent.subprocess.run", _raise_timeout)
    r = CodexAgent().run_task("draft", tmp_path, [])
    assert r.status == "error"
    assert "timed out" in r.message.lower()


def test_codex_returns_error_on_oserror(monkeypatch, tmp_path):
    """Simulates a broken codex binary that fails to exec at all."""
    monkeypatch.setattr("ai4science.agents.codex_agent.shutil.which",
                        lambda _name: "/usr/bin/codex")
    def _raise_oserror(*a, **k):
        raise OSError("exec format error")
    monkeypatch.setattr("ai4science.agents.codex_agent.subprocess.run", _raise_oserror)
    r = CodexAgent().run_task("draft", tmp_path, [])
    assert r.status == "error"
    assert "subprocess error" in r.message.lower()


def test_codex_does_not_run_when_unavailable(monkeypatch, tmp_path):
    """No `codex` binary → run_task short-circuits to not_available WITHOUT
    invoking subprocess (a key safety property)."""
    monkeypatch.setattr("ai4science.agents.codex_agent.shutil.which",
                        lambda _name: None)

    called = {"n": 0}
    def _bomb(*a, **k):
        called["n"] += 1
        raise AssertionError("subprocess.run must NOT be called when unavailable")
    monkeypatch.setattr("ai4science.agents.codex_agent.subprocess.run", _bomb)

    r = CodexAgent().run_task("draft", tmp_path, [])
    assert r.status == "not_available"
    assert called["n"] == 0


# ─── Context inlining ─────────────────────────────────────────────────


def test_codex_passes_workspace_context_in_stdin(monkeypatch, tmp_path):
    """Verify that file contents reach the subprocess via stdin (read-only)."""
    monkeypatch.setattr("ai4science.agents.codex_agent.shutil.which",
                        lambda _name: "/usr/bin/codex")

    # Workspace with a single artifact file that should be inlined.
    (tmp_path / "spec.md").write_text(
        "---\nartifact_type: spec\nname: test spec\n---\n# body\n", encoding="utf-8")

    captured = {}
    def _capture(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["stdin"] = kwargs.get("input", "")
        return _make_completed(0, stdout="ok response")
    monkeypatch.setattr("ai4science.agents.codex_agent.subprocess.run", _capture)

    r = CodexAgent().run_task("review this spec", tmp_path, [tmp_path / "spec.md"])
    assert r.status == "ok"
    assert "spec.md" in captured["stdin"]
    assert "test spec" in captured["stdin"]
    # System prompt must be embedded (Codex CLI has no separate --system flag).
    assert "AI4Science system context" in captured["stdin"]
