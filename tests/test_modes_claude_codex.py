"""Modes #4 claude-code and #5 codex: registration, ordering, backend binding."""
import pytest

from ai4science.harness.agents import registry


def test_claude_code_and_codex_registered():
    registry.reload()
    cc = registry.get("claude-code")
    cx = registry.get("codex")
    assert cc is not None and cx is not None
    assert cc.category == "core" and cx.category == "core"
    # both are coding agents with compute providers
    assert "compute-providers" in cc.capabilities
    assert "compute-providers" in cx.capabilities


def test_codex_binds_codex_backend_claude_binds_anthropic():
    registry.reload()
    assert registry.get("codex").default_backend == "openai"
    assert registry.get("claude-code").default_backend == "anthropic"


def test_aliases_resolve():
    registry.reload()
    assert registry.get("claude code").name == "claude-code"   # spaced alias
    assert registry.get("cc").name == "claude-code"


@pytest.mark.xfail(strict=True, reason=(
    "DIRECTOR CALL, open — the 2026-06-06 directive says the core menu is "
    "exactly these 5; the work-family/governed agents registered core and "
    "made it 12. Not a session's to decide: see "
    "singularity docs/plans/2026-08-08-director-calls-open.md. strict=True "
    "so the day the menu returns to 5 (the directive stands) this marker "
    "MUST come off in the commit that cites the decision."))
def test_core_menu_order_is_1_to_5():
    registry.reload()
    names = [s.name for s in registry.core_agents()]
    assert names == ["unified-LLM", "research", "paper", "claude-code", "codex"]
