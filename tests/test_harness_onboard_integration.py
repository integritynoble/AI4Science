from ai4science.harness.agents import registry, capabilities
from ai4science.harness.agents.context import BuildContext
from ai4science.harness.agents.registry import build_registry_for

_ONB = {"onboard_guide", "onboard_submit", "onboard_status", "onboard_balance"}


def _ctx(tmp_path):
    return BuildContext(workspace=tmp_path, brand_provider=lambda: ("gemini", "m"),
                        session_factory=lambda **k: None)


def test_bundle_registered(tmp_path):
    assert "onboarding" in capabilities.CAPABILITY_BUNDLES
    tools = capabilities.resolve_capability("onboarding", _ctx(tmp_path))
    assert _ONB <= {t.name for t in tools}


def test_research_has_onboarding_common_does_not(tmp_path):
    registry.reload()
    research = registry.get("research")
    assert "onboarding" in research.capabilities
    rreg = build_registry_for(research, is_subagent=False, ctx=_ctx(tmp_path))
    assert _ONB <= set(rreg.names())
    common = build_registry_for(registry.get("common"), is_subagent=False, ctx=_ctx(tmp_path))
    assert not (_ONB & set(common.names()))   # moat
