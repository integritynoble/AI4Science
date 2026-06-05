from ai4science.harness.agents import registry, capabilities
from ai4science.harness.agents.context import BuildContext
from ai4science.harness.agents.registry import build_registry_for

_CASSI = {"cassi_solutions", "cassi_forward_check", "cassi_dispatch", "cassi_result"}


def _ctx(tmp_path):
    return BuildContext(workspace=tmp_path, brand_provider=lambda: ("gemini", "m"),
                        session_factory=lambda **k: None)


def test_bundle_registered(tmp_path):
    assert "computational-imaging" in capabilities.CAPABILITY_BUNDLES
    tools = capabilities.resolve_capability("computational-imaging", _ctx(tmp_path))
    assert _CASSI <= {t.name for t in tools}


def test_ci_agent_has_cassi_tools_common_does_not(tmp_path):
    registry.reload()
    spec = registry.get("computational-imaging")
    assert "computational-imaging" in spec.capabilities
    creg = build_registry_for(spec, is_subagent=False, ctx=_ctx(tmp_path))
    assert _CASSI <= set(creg.names())
    common = build_registry_for(registry.get("common"), is_subagent=False, ctx=_ctx(tmp_path))
    assert not (_CASSI & set(common.names()))   # moat: common has none of them
