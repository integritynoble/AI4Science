from ai4science.harness.agents.spec import AgentSpec
from ai4science.harness.agents.specs.imaging import AGENT


def test_agentspec_has_profile_defaults():
    s = AgentSpec(name="x", tier="science", category="specific", title="X", description="d")
    assert s.supported_profiles == ("I0", "I1", "I2")
    assert s.default_profile == "I1"
    assert s.approval_required_for == ()


def test_imaging_agent_manifest():
    assert AGENT.name == "imaging"
    assert AGENT.default_profile == "I1"
    assert set(AGENT.supported_profiles) == {"I0", "I1", "I2"}
