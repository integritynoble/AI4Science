"""Tests for the chat REPL.

The full async REPL is hard to drive in pytest, so we test:
  - The slash-command parser (handles /help, /exit, etc. without an SDK call)
  - The workspace-artifact discovery helper
  - The chat command's startup gates (agent availability, --agent != claude)

A full end-to-end REPL test would require mocking ClaudeSDKClient
extensively; it's deferred until either (a) the SDK ships a TestClient
or (b) we add a `NoneAgentChat` for offline use.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from ai4science.cli import app

runner = CliRunner()


# ─── Workspace artifact discovery ────────────────────────────────────


def test_workspace_artifacts_empty_dir(tmp_path):
    from ai4science.commands.chat import _workspace_artifacts
    assert _workspace_artifacts(tmp_path) == []


def test_workspace_artifacts_picks_up_present_files(tmp_path):
    from ai4science.commands.chat import _workspace_artifacts
    (tmp_path / "principle.md").write_text("---\nartifact_type: principle\n---\n")
    (tmp_path / "spec.md").write_text("---\nartifact_type: spec\n---\n")
    files = _workspace_artifacts(tmp_path)
    names = [f.name for f in files]
    assert "principle.md" in names
    assert "spec.md" in names
    assert "benchmark.md" not in names   # not present
    assert "solution.md" not in names


def test_workspace_artifacts_returns_them_in_canonical_order(tmp_path):
    """principle → spec → benchmark → solution."""
    from ai4science.commands.chat import _workspace_artifacts
    for fname in ("solution.md", "benchmark.md", "spec.md", "principle.md"):
        (tmp_path / fname).write_text("hi")
    files = _workspace_artifacts(tmp_path)
    assert [f.name for f in files] == ["principle.md", "spec.md", "benchmark.md", "solution.md"]


# ─── Format-for-context helper ───────────────────────────────────────


def test_format_files_for_context_includes_filename_and_body(tmp_path):
    from ai4science.commands.chat import _format_files_for_context
    f = tmp_path / "spec.md"
    f.write_text("---\nname: test\n---\n# body")
    blob = _format_files_for_context([f], tmp_path)
    assert "spec.md" in blob
    assert "name: test" in blob
    assert "```" in blob   # fenced code block


def test_format_files_truncates_long_files(tmp_path):
    from ai4science.commands.chat import _format_files_for_context
    f = tmp_path / "spec.md"
    f.write_text("x" * 20_000)
    blob = _format_files_for_context([f], tmp_path)
    assert "truncated" in blob.lower()


# ─── Slash command parser ────────────────────────────────────────────


def _make_dummy_client():
    """Cheap stand-in for ClaudeSDKClient.get_context_usage()."""
    class _C:
        def get_context_usage(self):
            return "(dummy)"
    return _C()


def test_slash_help_handled(tmp_path):
    from ai4science.commands.chat import _handle_slash
    handled, should_exit, _plan = _handle_slash("/help", tmp_path,
                                          auto_yes=False, read_only=False,
                                          client=_make_dummy_client())
    assert handled is True
    assert should_exit is False


def test_slash_exit_signals_termination(tmp_path):
    from ai4science.commands.chat import _handle_slash
    for variant in ("/exit", "/quit", "/q"):
        _, should_exit, _ = _handle_slash(variant, tmp_path,
                                          auto_yes=False, read_only=False,
                                          client=_make_dummy_client())
        assert should_exit is True


# ─── /plan slash command ─────────────────────────────────────────────


def test_slash_plan_with_no_args_prints_help(tmp_path):
    """/plan alone explains how to use it; doesn't forward anything."""
    from ai4science.commands.chat import _handle_slash
    handled, exit_, plan_prompt = _handle_slash(
        "/plan", tmp_path, auto_yes=False, read_only=False,
        client=_make_dummy_client(),
    )
    assert handled is True
    assert exit_ is False
    assert plan_prompt is None   # no prompt to forward


def test_slash_plan_with_prompt_returns_prompt_to_forward(tmp_path):
    """`/plan refactor the solver` returns the bare prompt for the caller
    to forward under plan-mode framing."""
    from ai4science.commands.chat import _handle_slash
    handled, exit_, plan_prompt = _handle_slash(
        "/plan refactor the solver to use ADMM", tmp_path,
        auto_yes=False, read_only=False, client=_make_dummy_client(),
    )
    assert handled is True
    assert exit_ is False
    assert plan_prompt == "refactor the solver to use ADMM"


def test_slash_plan_in_already_restricted_mode_still_forwards(tmp_path):
    """When the session is already plan/read-only, /plan <p> should still
    forward the prompt (so the user isn't blocked) — just with a hint."""
    from ai4science.commands.chat import _handle_slash
    _, _, plan_prompt = _handle_slash(
        "/plan show me the plan for adding a CT spec", tmp_path,
        auto_yes=False, read_only=True, plan_mode_active=False,
        client=_make_dummy_client(),
    )
    assert plan_prompt == "show me the plan for adding a CT spec"


def test_slash_files_lists_workspace_artifacts(tmp_path):
    from ai4science.commands.chat import _handle_slash
    (tmp_path / "principle.md").write_text("hi")
    handled, should_exit, _plan = _handle_slash("/files", tmp_path,
                                          auto_yes=False, read_only=False,
                                          client=_make_dummy_client())
    assert handled is True
    assert should_exit is False


def test_slash_unknown_is_handled_but_does_not_exit(tmp_path):
    from ai4science.commands.chat import _handle_slash
    handled, should_exit, _plan = _handle_slash("/bogus", tmp_path,
                                          auto_yes=False, read_only=False,
                                          client=_make_dummy_client())
    assert handled is True   # we "handled" it by printing a hint
    assert should_exit is False


def test_slash_cost_is_handled_gracefully_when_unavailable(tmp_path):
    """get_context_usage might not exist — should not crash."""
    from ai4science.commands.chat import _handle_slash
    class _Bad:
        def get_context_usage(self):
            raise RuntimeError("not yet wired")
    handled, _, _ = _handle_slash("/cost", tmp_path,
                                   auto_yes=False, read_only=False, client=_Bad())
    assert handled is True


def test_slash_validate_runs_in_repl(tmp_path):
    """Calling /validate from the REPL must NOT exit; it runs the command
    and returns (handled=True, exit=False) even if validate itself raises
    typer.Exit non-zero."""
    from ai4science.commands.chat import _handle_slash
    # Empty workspace → validate exits 2; the REPL must swallow that.
    handled, should_exit, _plan = _handle_slash("/validate", tmp_path,
                                          auto_yes=False, read_only=False,
                                          client=_make_dummy_client())
    assert handled is True
    assert should_exit is False


# ─── Top-level chat command gating ────────────────────────────────────


def test_chat_rejects_non_claude_agent(tmp_path, monkeypatch):
    """Only --agent claude is supported in v0.4 chat mode."""
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["chat", "--agent", "codex"])
    assert result.exit_code == 2
    assert "chat mode only supports" in result.output.lower()


def test_chat_rejects_when_claude_unavailable(tmp_path, monkeypatch):
    """If `claude` CLI not on PATH → exit 2 cleanly, don't try to connect."""
    monkeypatch.chdir(tmp_path)
    # Force ClaudeAgent.is_available to False.
    monkeypatch.setattr("ai4science.agents.claude_agent.shutil.which",
                        lambda _: None)
    result = runner.invoke(app, ["chat"])
    assert result.exit_code == 2
    assert "not available" in result.output.lower()
