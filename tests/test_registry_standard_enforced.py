"""The science agents must carry the mandatory registry-standard instruction."""
from __future__ import annotations


def _prompt_text(agent) -> str:
    # The AgentSpec's instruction text — adapt the attribute to the real field
    # name found in STEP 0 (e.g. agent.prompt / agent.system / agent.instructions).
    for attr in ("prompt", "system", "instructions", "system_prompt"):
        v = getattr(agent, attr, None)
        if isinstance(v, str) and v:
            return v
    raise AssertionError("could not find the agent's prompt text field")


def test_ci_agent_enforces_standard():
    # computational-imaging is now sourced from the pwm-agent-imaging package
    # via entry point (no local specs/computational_imaging.py file to
    # import) — fetch it through the registry instead.
    from ai4science.harness.agents import registry
    registry.reload()
    AGENT = registry.get("computational-imaging")
    t = _prompt_text(AGENT).lower()
    assert "pwm_standard_check" in t
    assert "registry standard" in t
    assert "meets-or-beats" in t or "meet-or-beat" in t


def test_research_agent_enforces_standard():
    # research is now sourced from the pwm-agent-research package via entry
    # point (no local specs/research.py file to import) — fetch it through
    # the registry instead.
    from ai4science.harness.agents import registry
    registry.reload()
    AGENT = registry.get("research")
    t = _prompt_text(AGENT).lower()
    assert "pwm_standard_check" in t
    assert "registry standard" in t


def test_both_have_science_router_capability():
    # computational-imaging is now sourced from the pwm-agent-imaging package
    # via entry point (no local specs/computational_imaging.py file to
    # import) — fetch it through the registry instead.
    from ai4science.harness.agents import registry
    registry.reload()
    CI = registry.get("computational-imaging")
    R = registry.get("research")
    assert "science-router" in CI.capabilities
    assert "science-router" in R.capabilities
