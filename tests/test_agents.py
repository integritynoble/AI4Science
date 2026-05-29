"""Tests for the agent provider abstraction + prompt-first → agent handoff.

These tests NEVER make real LLM calls. ClaudeAgent.run_task is patched
to return a fixture response, exercising the dispatch / context-building
/ output-rendering code paths without touching the network.
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from ai4science.agents import (
    BaseAgent, NoneAgent, ClaudeAgent, CodexAgent, get_agent,
)
from ai4science.agents.base import AgentResult
from ai4science.cli import app, main, _rule_route

runner = CliRunner()


# ─── BaseAgent / dispatch ─────────────────────────────────────────────


def test_none_agent_is_always_available():
    a = NoneAgent()
    assert a.is_available() is True


def test_get_agent_dispatches_by_name():
    assert isinstance(get_agent("none"), NoneAgent)
    assert isinstance(get_agent("claude"), ClaudeAgent)
    assert isinstance(get_agent("codex"), CodexAgent)


def test_get_agent_rejects_unknown_name():
    with pytest.raises(ValueError, match="unknown agent"):
        get_agent("not_a_provider")


def test_none_agent_run_task_returns_instructions(tmp_path: Path):
    r = NoneAgent().run_task("draft principle", tmp_path, [])
    assert r.status == "ok"
    assert "NoneAgent" in r.message


# ─── ClaudeAgent availability ────────────────────────────────────────


def test_claude_agent_is_unavailable_without_cli(monkeypatch):
    """No `claude` binary on PATH → not available, no matter what env says."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake")
    monkeypatch.setattr("ai4science.agents.claude_agent.shutil.which",
                        lambda _name: None)
    assert ClaudeAgent().is_available() is False


def test_claude_agent_unavailable_reason_mentions_subscription(monkeypatch):
    """When ANTHROPIC_API_KEY is unset, the reason should NOT block on it —
    it should mention `claude login` (subscription auth) as a valid path."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr("ai4science.agents.claude_agent.shutil.which",
                        lambda _name: "/usr/bin/claude")
    reason = ClaudeAgent().unavailable_reason()
    # We DO mention that the key is unset, but only as a note — not as a blocker.
    assert "claude login" in reason.lower() or "subscription" in reason.lower()


def test_claude_agent_run_task_when_unavailable(monkeypatch):
    monkeypatch.setattr("ai4science.agents.claude_agent.shutil.which",
                        lambda _name: None)
    r = ClaudeAgent().run_task("draft", Path("."), [])
    assert r.status == "not_available"
    assert "not available" in r.message.lower()


# ─── CodexAgent availability ─────────────────────────────────────────


def test_codex_agent_is_unavailable_without_cli(monkeypatch):
    monkeypatch.setattr("ai4science.agents.codex_agent.shutil.which",
                        lambda _name: None)
    assert CodexAgent().is_available() is False


def test_codex_agent_unavailable_reason_mentions_subscription(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("ai4science.agents.codex_agent.shutil.which",
                        lambda _name: "/usr/bin/codex")
    reason = CodexAgent().unavailable_reason()
    assert "codex login" in reason.lower() or "subscription" in reason.lower()


# ─── Rule-based intent precedence (the v0.1 bug we just fixed) ───────


def test_intent_draft_principle_beats_cassi_domain():
    """v0.1 bug: 'draft a CASSI principle' matched 'cassi' → judge_cassi.
    v0.2 fix: 'draft' + 'principle' must win → contribute principle."""
    assert _rule_route("Help me draft a CASSI principle for FRET imaging") == "principle"


def test_intent_create_spec_routes_correctly():
    assert _rule_route("create a spec for hyperspectral reconstruction") == "spec"


def test_intent_validate_still_matches():
    assert _rule_route("validate my submission and tell me what is missing") == "validate"


def test_intent_judge_still_matches_when_unambiguous():
    assert _rule_route("run the cassi judge") == "judge_cassi"


def test_intent_plain_cassi_is_lowest_precedence():
    """A bare 'cassi' (no verb, no artifact noun) routes to judge_cassi."""
    assert _rule_route("cassi") == "judge_cassi"


def test_intent_returns_none_for_unrelated_prompt():
    assert _rule_route("what time is it") is None


# ─── Prompt-first → agent fallback (the new behavior) ────────────────


def test_prompt_first_with_none_agent_falls_back_to_help_message(tmp_path, monkeypatch):
    """If --agent is 'none' and no rule matches, print help, exit 2."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "sys.argv",
        ["ai4science", "--agent", "none", "explain quantum tunneling"],
    )
    with pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code == 2


def test_prompt_first_with_claude_unavailable_says_so(tmp_path, monkeypatch, capsys):
    """If --agent claude and it isn't available, surface the reason and exit 2."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "ai4science.agents.claude_agent.shutil.which", lambda _name: None,
    )
    monkeypatch.setattr(
        "sys.argv", ["ai4science", "--agent", "claude", "explain quantum tunneling"],
    )
    with pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code == 2


def test_prompt_first_with_mocked_claude_returns_ok(tmp_path, monkeypatch, capsys):
    """Mock ClaudeAgent.run_task and verify the prompt-first path renders its output."""
    monkeypatch.chdir(tmp_path)

    fake_result = AgentResult(
        status="ok",
        message="Here is a draft principle.md for FRET imaging:\n\n---\n...",
    )

    # Mock both is_available (so the dispatcher doesn't bail early) AND run_task.
    def _fake_run_task(self, prompt, workspace, context_files):
        return fake_result

    monkeypatch.setattr(ClaudeAgent, "is_available", lambda self: True)
    monkeypatch.setattr(ClaudeAgent, "run_task", _fake_run_task)
    monkeypatch.setattr(
        "sys.argv", ["ai4science", "--agent", "claude", "explain quantum tunneling to me"],
    )

    with pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code == 0

    captured = capsys.readouterr()
    assert "draft principle.md" in captured.out


def test_agents_command_lists_providers():
    """`ai4science agents` should list all three providers + their availability."""
    result = runner.invoke(app, ["agents"])
    assert result.exit_code == 0
    assert "none" in result.output
    assert "claude" in result.output
    assert "codex" in result.output


# ─── --agent flag plumbing ───────────────────────────────────────────


def test_agent_flag_env_default(monkeypatch):
    """AI4SCIENCE_AGENT env var sets the default."""
    from ai4science.cli import _pop_agent_flag
    monkeypatch.setenv("AI4SCIENCE_AGENT", "claude")
    cleaned, agent, ro, yes, _, _ = _pop_agent_flag(["some", "prompt"])
    assert cleaned == ["some", "prompt"]
    assert agent == "claude"
    assert ro is False and yes is False


def test_agent_flag_long_form_overrides_env(monkeypatch):
    from ai4science.cli import _pop_agent_flag
    monkeypatch.setenv("AI4SCIENCE_AGENT", "none")
    cleaned, agent, _, _, _, _ = _pop_agent_flag(["--agent", "claude", "some", "prompt"])
    assert cleaned == ["some", "prompt"]
    assert agent == "claude"


def test_agent_flag_equals_form_works(monkeypatch):
    from ai4science.cli import _pop_agent_flag
    monkeypatch.delenv("AI4SCIENCE_AGENT", raising=False)
    cleaned, agent, _, _, _, _ = _pop_agent_flag(["--agent=claude", "draft", "a", "principle"])
    assert cleaned == ["draft", "a", "principle"]
    assert agent == "claude"


def test_agent_flag_unknown_falls_back_to_auto(monkeypatch, capsys):
    from ai4science.cli import _pop_agent_flag
    monkeypatch.delenv("AI4SCIENCE_AGENT", raising=False)
    cleaned, agent, _, _, _, _ = _pop_agent_flag(["--agent", "gemini", "prompt"])
    # An explicit (but unknown) --agent value signals the user wants an agent,
    # so we fall back to 'auto' (pick best available real agent) rather than
    # 'none'. 'auto' resolves to claude → codex → none at dispatch time.
    assert agent == "auto"


def test_agent_flag_default_is_auto(monkeypatch):
    """With no --agent and no env override, the default is 'auto'."""
    from ai4science.cli import _pop_agent_flag
    monkeypatch.delenv("AI4SCIENCE_AGENT", raising=False)
    cleaned, agent, _, _, _, _ = _pop_agent_flag(["some prompt"])
    assert agent == "auto"


def test_resolve_agent_passthrough_for_explicit_names():
    """_resolve_agent only rewrites the 'auto' sentinel; explicit names pass through."""
    from ai4science.cli import _resolve_agent
    assert _resolve_agent("none") == "none"
    assert _resolve_agent("claude") == "claude"
    assert _resolve_agent("codex") == "codex"


def test_resolve_agent_auto_picks_available(monkeypatch):
    """'auto' resolves to the first available agent in claude → codex → none order."""
    import ai4science.cli as cli_mod

    class _Stub:
        def __init__(self, ok):
            self._ok = ok
        def is_available(self):
            return self._ok

    # claude available → auto picks claude
    monkeypatch.setattr(cli_mod, "get_agent",
                        lambda n, **k: _Stub(n == "claude"))
    assert cli_mod._resolve_agent("auto") == "claude"

    # only codex available → auto picks codex
    monkeypatch.setattr(cli_mod, "get_agent",
                        lambda n, **k: _Stub(n == "codex"))
    assert cli_mod._resolve_agent("auto") == "codex"

    # nothing available → auto falls back to none
    monkeypatch.setattr(cli_mod, "get_agent",
                        lambda n, **k: _Stub(False))
    assert cli_mod._resolve_agent("auto") == "none"


def test_read_only_flag_parsed(monkeypatch):
    """--read-only and --readonly both work; default is False."""
    from ai4science.cli import _pop_agent_flag
    monkeypatch.delenv("AI4SCIENCE_READ_ONLY", raising=False)
    _, _, ro, _, _, _ = _pop_agent_flag(["--agent", "claude", "--read-only", "draft a spec"])
    assert ro is True

    _, _, ro2, _, _, _ = _pop_agent_flag(["--agent", "claude", "--readonly", "draft"])
    assert ro2 is True


def test_yes_flag_parsed(monkeypatch):
    """--yes / -y both work."""
    from ai4science.cli import _pop_agent_flag
    monkeypatch.delenv("AI4SCIENCE_AUTO_YES", raising=False)
    _, _, _, yes, _, _ = _pop_agent_flag(["--agent", "claude", "--yes", "draft a spec"])
    assert yes is True
    _, _, _, yes2, _, _ = _pop_agent_flag(["--agent", "claude", "-y", "draft"])
    assert yes2 is True


def test_read_only_env_default(monkeypatch):
    from ai4science.cli import _pop_agent_flag
    monkeypatch.setenv("AI4SCIENCE_READ_ONLY", "1")
    _, _, ro, _, _, _ = _pop_agent_flag(["--agent", "claude", "draft"])
    assert ro is True


def test_get_agent_forwards_kwargs_to_claude():
    """get_agent('claude', read_only=True) should pass through to ClaudeAgent."""
    a = get_agent("claude", read_only=True, auto_yes=True)
    assert isinstance(a, ClaudeAgent)
    assert a.read_only is True
    assert a.auto_yes is True


def test_get_agent_default_claude_is_tool_use_mode():
    """No kwargs → ClaudeAgent in tool-use mode (the v0.3 default)."""
    a = get_agent("claude")
    assert isinstance(a, ClaudeAgent)
    assert a.read_only is False
    assert a.auto_yes is False
    assert a.plan_mode is False


# ─── --plan flag plumbing (v0.6) ─────────────────────────────────────


def test_plan_flag_parsed(monkeypatch):
    from ai4science.cli import _pop_agent_flag
    monkeypatch.delenv("AI4SCIENCE_PLAN", raising=False)
    _, _, _, _, plan, _ = _pop_agent_flag(["--agent", "claude", "--plan", "draft something"])
    assert plan is True


def test_plan_env_default(monkeypatch):
    from ai4science.cli import _pop_agent_flag
    monkeypatch.setenv("AI4SCIENCE_PLAN", "1")
    _, _, _, _, plan, _ = _pop_agent_flag(["--agent", "claude", "draft"])
    assert plan is True


def test_plan_default_is_false(monkeypatch):
    from ai4science.cli import _pop_agent_flag
    monkeypatch.delenv("AI4SCIENCE_PLAN", raising=False)
    _, _, _, _, plan, _ = _pop_agent_flag(["--agent", "claude", "draft"])
    assert plan is False


def test_model_flag_parsed(monkeypatch):
    """--model / -m / --model= set the session model; default None."""
    from ai4science.cli import _pop_agent_flag
    monkeypatch.delenv("AI4SCIENCE_MODEL", raising=False)
    cleaned, _, _, _, _, model = _pop_agent_flag(["--model", "opus", "draft"])
    assert model == "opus" and cleaned == ["draft"]
    _, _, _, _, _, m2 = _pop_agent_flag(["-m", "sonnet", "draft"])
    assert m2 == "sonnet"
    _, _, _, _, _, m3 = _pop_agent_flag(["--model=haiku", "draft"])
    assert m3 == "haiku"
    _, _, _, _, _, m4 = _pop_agent_flag(["draft"])
    assert m4 is None


def test_model_env_default(monkeypatch):
    from ai4science.cli import _pop_agent_flag
    monkeypatch.setenv("AI4SCIENCE_MODEL", "opus")
    _, _, _, _, _, model = _pop_agent_flag(["--agent", "claude", "draft"])
    assert model == "opus"


def test_session_flags_continue_and_resume(monkeypatch):
    """--continue/-c and --resume <id> are stripped for the bare-launch path."""
    from ai4science.cli import _pop_session_flags
    monkeypatch.delenv("AI4SCIENCE_RESUME", raising=False)
    cleaned, cont, resume = _pop_session_flags(["--continue"])
    assert cleaned == [] and cont is True and resume is None
    cleaned, cont, _ = _pop_session_flags(["-c", "draft"])
    assert cleaned == ["draft"] and cont is True
    cleaned, cont, resume = _pop_session_flags(["--resume", "sess-42", "x"])
    assert cleaned == ["x"] and cont is False and resume == "sess-42"
    _, _, r2 = _pop_session_flags(["--resume=sess-7"])
    assert r2 == "sess-7"
    cleaned, cont, resume = _pop_session_flags(["draft", "a", "spec"])
    assert cleaned == ["draft", "a", "spec"] and cont is False and resume is None


def test_get_agent_forwards_plan_mode():
    a = get_agent("claude", plan_mode=True)
    assert isinstance(a, ClaudeAgent)
    assert a.plan_mode is True


def test_get_agent_plan_mode_independent_of_read_only_and_auto_yes():
    a = get_agent("claude", plan_mode=True, read_only=False, auto_yes=True)
    assert a.plan_mode is True
    assert a.read_only is False
    assert a.auto_yes is True


def test_resolve_cli_path_prefers_env_override(monkeypatch):
    """AI4SCIENCE_CLAUDE_CLI_PATH wins over PATH lookup."""
    from ai4science.agents.claude_agent import _resolve_cli_path
    monkeypatch.setenv("AI4SCIENCE_CLAUDE_CLI_PATH", "/custom/claude")
    assert _resolve_cli_path() == "/custom/claude"


def test_resolve_cli_path_falls_back_to_path(monkeypatch):
    """With no env override, returns the `claude` on PATH (the system CLI),
    NOT the SDK's bundled binary — which on Windows hangs the initialize
    handshake and isn't tied to the user's `claude login` auth."""
    import ai4science.agents.claude_agent as ca
    monkeypatch.delenv("AI4SCIENCE_CLAUDE_CLI_PATH", raising=False)
    monkeypatch.setattr(ca.shutil, "which",
                        lambda name: "/usr/bin/claude" if name == "claude" else None)
    assert ca._resolve_cli_path() == "/usr/bin/claude"


def test_resolve_cli_path_none_when_no_system_cli(monkeypatch):
    """No env override and no `claude` on PATH → None (SDK falls back to bundled)."""
    import ai4science.agents.claude_agent as ca
    monkeypatch.delenv("AI4SCIENCE_CLAUDE_CLI_PATH", raising=False)
    monkeypatch.setattr(ca.shutil, "which", lambda name: None)
    assert ca._resolve_cli_path() is None
