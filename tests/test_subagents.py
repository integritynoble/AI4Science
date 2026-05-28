"""Tests for PWM sub-agent definitions."""
from __future__ import annotations

import pytest

# Sub-agent definitions require the real SDK type — skip if missing.
pytest.importorskip("claude_agent_sdk")

from ai4science.agents.subagents import (
    build_pwm_subagents, SUBAGENT_NAMES,
    PHYSICS_REVIEWER_PROMPT, SCHEMA_VALIDATOR_PROMPT, BENCHMARK_ARCHITECT_PROMPT,
)


def test_three_subagents_are_defined():
    agents = build_pwm_subagents()
    assert set(agents.keys()) == set(SUBAGENT_NAMES)
    assert len(agents) == 3


def test_physics_reviewer_is_read_only():
    """The physics-reviewer should have NO write tools."""
    agents = build_pwm_subagents()
    pr = agents["physics-reviewer"]
    write_tools = {"Edit", "Write", "Bash", "MultiEdit"}
    assert set(pr.tools).isdisjoint(write_tools)
    assert "Read" in pr.tools


def test_schema_validator_has_edit_but_not_bash():
    """schema-validator can Edit for fix-ups; cannot run Bash."""
    agents = build_pwm_subagents()
    sv = agents["schema-validator"]
    assert "Edit" in sv.tools
    assert "Bash" not in sv.tools
    assert "Write" not in sv.tools   # Edit-only — no full overwrites


def test_benchmark_architect_is_read_only():
    """benchmark-architect produces plans, doesn't execute them."""
    agents = build_pwm_subagents()
    ba = agents["benchmark-architect"]
    write_tools = {"Edit", "Write", "Bash", "MultiEdit"}
    assert set(ba.tools).isdisjoint(write_tools)


def test_all_subagents_have_descriptions():
    """description: text is what the main agent sees when deciding to delegate.
    Must be non-trivial."""
    agents = build_pwm_subagents()
    for name, ad in agents.items():
        assert len(ad.description) > 40, f"{name} description too short"
        assert len(ad.prompt) > 200, f"{name} system prompt too short"


def test_prompts_include_pwm_rails():
    """Each sub-agent's prompt must reaffirm the protocol rails."""
    # 'Physics Judge' must appear in physics-reviewer's prompt (it's the rule
    # against claiming verdict authority).
    assert "Physics Judge" in PHYSICS_REVIEWER_PROMPT
    # schema-validator: must list the canonical fields
    for field in ("artifact_type", "parent_principle_id", "parent_benchmark_id"):
        assert field in SCHEMA_VALIDATOR_PROMPT
    # benchmark-architect: must reference tier conventions
    assert "tier" in BENCHMARK_ARCHITECT_PROMPT.lower()
