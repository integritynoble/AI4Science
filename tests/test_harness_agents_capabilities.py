import pytest
from ai4science.harness.agents.spec import AgentSpec
from ai4science.harness.agents.context import BuildContext
from ai4science.harness.agents import capabilities


def _ctx(tmp_path):
    return BuildContext(workspace=tmp_path, brand_provider=lambda: ("gemini", "m"),
                        session_factory=lambda **k: None)


def test_agentspec_is_frozen():
    s = AgentSpec(name="x", tier="open", category="core", title="X", description="d")
    with pytest.raises(Exception):
        s.name = "y"


def test_pwm_actions_bundle_resolves(tmp_path):
    tools = capabilities.resolve_capability("pwm-actions", _ctx(tmp_path))
    names = {t.name for t in tools}
    assert {"pwm_status", "pwm_validate", "pwm_judge_cassi", "pwm_lookup_artifact"} <= names


def test_pwm_data_bundle_resolves(tmp_path):
    tools = capabilities.resolve_capability("pwm-data", _ctx(tmp_path))
    assert "pwm_solutions" in {t.name for t in tools}


def test_unknown_capability_raises(tmp_path):
    with pytest.raises(ValueError) as e:
        capabilities.resolve_capability("nope", _ctx(tmp_path))
    assert "nope" in str(e.value) and "pwm-data" in str(e.value)
