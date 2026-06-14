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

import asyncio
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ai4science.cli import app
from ai4science.commands import chat as _chat

runner = CliRunner()


def _handle_slash(*args, **kwargs):
    """_handle_slash is a coroutine (it awaits SDK calls); run it synchronously
    so the existing sync tests keep working."""
    return asyncio.run(_chat._handle_slash(*args, **kwargs))


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
    """Cheap stand-in for ClaudeSDKClient: records permission-mode changes.

    The real SDK's set_permission_mode/get_context_usage are coroutines, so
    these are async too — that's what _handle_slash awaits."""
    class _C:
        def __init__(self):
            self.mode = "default"
        async def get_context_usage(self):
            return "(dummy)"
        async def set_permission_mode(self, mode):
            self.mode = mode
    return _C()


def test_slash_yes_toggles_accept_edits_live(tmp_path):
    """/yes flips the live session to accept-edits (no restart needed)."""
    client = _make_dummy_client()
    handled, _, _ = _handle_slash("/yes", tmp_path, auto_yes=False,
                                  read_only=False, client=client)
    assert handled is True
    assert client.mode == "acceptEdits"


def test_slash_readonly_and_default_toggle_live(tmp_path):
    """/readonly → plan (no edits); /default → default (edits confirmed)."""
    client = _make_dummy_client()
    _handle_slash("/readonly", tmp_path, auto_yes=False, read_only=False, client=client)
    assert client.mode == "plan"
    _handle_slash("/default", tmp_path, auto_yes=False, read_only=False, client=client)
    assert client.mode == "default"


def test_slash_help_handled(tmp_path):
    handled, should_exit, _plan = _handle_slash("/help", tmp_path,
                                          auto_yes=False, read_only=False,
                                          client=_make_dummy_client())
    assert handled is True
    assert should_exit is False


def test_slash_exit_signals_termination(tmp_path):
    for variant in ("/exit", "/quit", "/q"):
        _, should_exit, _ = _handle_slash(variant, tmp_path,
                                          auto_yes=False, read_only=False,
                                          client=_make_dummy_client())
        assert should_exit is True


# ─── /plan slash command ─────────────────────────────────────────────


def test_slash_plan_with_no_args_prints_help(tmp_path):
    """/plan alone explains how to use it; doesn't forward anything."""
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
    _, _, plan_prompt = _handle_slash(
        "/plan show me the plan for adding a CT spec", tmp_path,
        auto_yes=False, read_only=True, plan_mode_active=False,
        client=_make_dummy_client(),
    )
    assert plan_prompt == "show me the plan for adding a CT spec"


def test_slash_files_lists_workspace_artifacts(tmp_path):
    (tmp_path / "principle.md").write_text("hi")
    handled, should_exit, _plan = _handle_slash("/files", tmp_path,
                                          auto_yes=False, read_only=False,
                                          client=_make_dummy_client())
    assert handled is True
    assert should_exit is False


def test_slash_unknown_is_handled_but_does_not_exit(tmp_path):
    handled, should_exit, _plan = _handle_slash("/bogus", tmp_path,
                                          auto_yes=False, read_only=False,
                                          client=_make_dummy_client())
    assert handled is True   # we "handled" it by printing a hint
    assert should_exit is False


def test_slash_cost_is_handled_gracefully_when_unavailable(tmp_path):
    """get_context_usage might not exist — should not crash."""
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
    # Empty workspace → validate exits 2; the REPL must swallow that.
    handled, should_exit, _plan = _handle_slash("/validate", tmp_path,
                                          auto_yes=False, read_only=False,
                                          client=_make_dummy_client())
    assert handled is True
    assert should_exit is False


# ─── Top-level chat command gating ────────────────────────────────────


def test_bare_ai4science_launches_chat_when_available(tmp_path, monkeypatch):
    """Bare `ai4science` (no args) should start the chat session, like `claude`."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("ai4science.cli._agent_powered", lambda: True)
    captured = {}

    def _fake_chat(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr("ai4science.commands.chat.chat", _fake_chat)
    monkeypatch.setattr("sys.argv", ["ai4science"])
    from ai4science import cli
    cli.main()                       # returns (no SystemExit) on success
    assert captured.get("agent") == "claude"     # launched chat, not help


def test_bare_ai4science_shows_panel_when_agent_unavailable(tmp_path, monkeypatch, capsys):
    """Bare `ai4science` with NO LLM credential → getting-started panel, exit 0.
    The panel leads with the Node-free `ai4science login` path."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("ai4science.cli._agent_powered", lambda: False)
    monkeypatch.setattr("sys.argv", ["ai4science"])
    from ai4science import cli
    with pytest.raises(SystemExit) as e:
        cli.main()
    assert e.value.code == 0
    out = capsys.readouterr().out
    assert "ai4science login" in out         # leads with the Node-free path
    assert "ai4science init" in out          # points at the offline commands


def test_bare_flags_carry_into_chat(tmp_path, monkeypatch):
    """`ai4science --plan` (bare + flag) launches chat in plan mode."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("ai4science.cli._agent_powered", lambda: True)
    captured = {}
    monkeypatch.setattr("ai4science.commands.chat.chat", lambda **kw: captured.update(kw))
    monkeypatch.setattr("sys.argv", ["ai4science", "--plan", "--yes"])
    from ai4science import cli
    cli.main()
    assert captured.get("plan") is True
    assert captured.get("yes") is True


def test_chat_rejects_non_claude_agent(tmp_path, monkeypatch):
    """Only --agent claude is supported in v0.4 chat mode."""
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["chat", "--agent", "codex"])
    assert result.exit_code == 2
    assert "chat mode only supports" in result.output.lower()


def test_chat_research_rejects_when_claude_unavailable(tmp_path, monkeypatch):
    """Research mode now routes to the native harness (not the SDK path), so
    it no longer requires `claude` CLI on PATH.  With run_common_repl mocked
    out the command must exit 0 even when claude is absent."""
    monkeypatch.chdir(tmp_path)
    # Make claude unavailable — harness must NOT gate on it.
    monkeypatch.setattr("ai4science.agents.claude_agent.shutil.which",
                        lambda _: None)
    import ai4science.commands.chat as chat_mod
    monkeypatch.setattr(chat_mod, "run_common_repl",
                        lambda workspace, **kw: None)
    result = runner.invoke(app, ["chat", "--mode", "research"])
    assert result.exit_code == 0


def test_chat_common_launches_harness(tmp_path, monkeypatch):
    """Common mode routes to the native harness REPL (no claude requirement);
    with no stdin (CliRunner), it reads EOF and exits cleanly."""
    monkeypatch.chdir(tmp_path)
    # Even with claude CLI absent, common mode must not gate on it.
    monkeypatch.setattr("ai4science.agents.claude_agent.shutil.which",
                        lambda _: None)
    called = {}

    def _fake_repl(workspace, **kwargs):
        called["workspace"] = workspace
        called["kwargs"] = kwargs

    import ai4science.commands.chat as chat_mod
    monkeypatch.setattr(chat_mod, "run_common_repl", _fake_repl)
    result = runner.invoke(app, ["chat", "--mode", "common"])
    assert result.exit_code == 0
    assert called, "run_common_repl was not invoked for common mode"


# ─── bucket (b): /resume + /compact ──────────────────────────────────


def test_list_sessions_prints_past_sessions(tmp_path, monkeypatch, capsys):
    """/resume (→ _list_sessions) lists the workspace's sessions with ids."""
    import ai4science.commands.chat as chat_mod

    class _S:
        def __init__(self, sid, summary):
            self.session_id = sid
            self.summary = summary
            self.last_modified = "2026-05-28"

    import claude_agent_sdk
    monkeypatch.setattr(claude_agent_sdk, "list_sessions",
                        lambda directory=None, limit=None: [
                            _S("abc123", "drafted a CASSI spec"),
                            _S("def456", "ran the judge"),
                        ], raising=False)
    chat_mod._list_sessions(tmp_path)
    out = capsys.readouterr().out
    assert "abc123" in out and "def456" in out
    assert "--resume" in out


def test_list_sessions_handles_empty(tmp_path, monkeypatch, capsys):
    import ai4science.commands.chat as chat_mod
    import claude_agent_sdk
    monkeypatch.setattr(claude_agent_sdk, "list_sessions",
                        lambda directory=None, limit=None: [], raising=False)
    chat_mod._list_sessions(tmp_path)
    assert "No past sessions" in capsys.readouterr().out


def test_do_compact_reports_usage(capsys):
    """/compact (→ _do_compact) reports context usage + the auto-compaction note."""
    import asyncio
    import ai4science.commands.chat as chat_mod

    class _Client:
        async def get_context_usage(self):
            return "12345 / 200000 tokens"

    asyncio.run(chat_mod._do_compact(_Client()))
    out = capsys.readouterr().out
    assert "12345" in out
    assert "auto-compact" in out.lower()


def test_chat_accepts_resume_option():
    """`chat --resume <id>` is a recognized option.

    Introspect the registered Click option rather than scraping `--help` text,
    which Rich width-truncates in narrow CI terminals (flaky substring match).
    """
    import typer
    from ai4science.cli import app
    chat_cmd = typer.main.get_command(app).commands["chat"]
    option_names = {name for p in chat_cmd.params for name in getattr(p, "opts", [])}
    assert "--resume" in option_names


def test_chat_research_uses_harness(tmp_path, monkeypatch):
    """--mode research now routes to the native harness research REPL (not the SDK path).

    Under the registry-driven contract, chat() resolves --mode against the agent
    registry and passes only mode_label (+ the spec's prompt as a fallback); the
    registry itself is chosen inside run_common_repl, so there's no registry_builder.
    """
    import ai4science.commands.chat as chat_mod
    monkeypatch.chdir(tmp_path)
    called = {}
    monkeypatch.setattr(chat_mod, "run_common_repl",
                        lambda workspace, **kw: called.update(kw))
    result = runner.invoke(app, ["chat", "--mode", "research"])
    assert result.exit_code == 0
    assert called.get("mode_label") == "research"         # resolved research spec
    assert called.get("system_prompt")                    # research prompt passed as fallback


def test_chat_mode_resolves_known_agent(monkeypatch, tmp_path):
    import ai4science.commands.chat as chat_mod
    captured = {}
    def fake_repl(workspace, **kw):
        captured.update(kw); captured["workspace"] = workspace
    monkeypatch.setattr(chat_mod, "run_common_repl", fake_repl)
    from typer.testing import CliRunner
    from ai4science.cli import app
    res = CliRunner().invoke(app, ["chat", "--mode", "computational-imaging",
                                   "--workspace", str(tmp_path)])
    assert res.exit_code == 0
    assert captured["mode_label"] == "computational-imaging"
    assert captured["system_prompt"]  # the spec's prompt passed as fallback


def test_chat_unknown_mode_falls_back_to_common(monkeypatch, tmp_path):
    import ai4science.commands.chat as chat_mod
    captured = {}
    monkeypatch.setattr(chat_mod, "run_common_repl",
                        lambda workspace, **kw: captured.update(kw))
    from typer.testing import CliRunner
    from ai4science.cli import app
    res = CliRunner().invoke(app, ["chat", "--mode", "nonexistent",
                                   "--workspace", str(tmp_path)])
    assert res.exit_code == 0
    assert captured["mode_label"] == "unified-LLM"
