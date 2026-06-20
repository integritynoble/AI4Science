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
    from ai4science.harness.agents.specs.computational_imaging import AGENT
    t = _prompt_text(AGENT).lower()
    assert "pwm_standard_check" in t
    assert "registry standard" in t
    assert "meets-or-beats" in t or "meet-or-beat" in t


def test_research_agent_enforces_standard():
    from ai4science.harness.agents.specs.research import AGENT
    t = _prompt_text(AGENT).lower()
    assert "pwm_standard_check" in t
    assert "registry standard" in t


def test_both_have_science_router_capability():
    from ai4science.harness.agents.specs.computational_imaging import AGENT as CI
    from ai4science.harness.agents.specs.research import AGENT as R
    assert "science-router" in CI.capabilities
    assert "science-router" in R.capabilities
