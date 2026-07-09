from ai4science.harness.agents import registry
from ai4science.harness.agents.spec import AgentSpec
from ai4science.harness.agents.context import BuildContext


def _ctx(tmp_path):
    return BuildContext(workspace=tmp_path,
                        brand_provider=lambda: ("gemini", "m"),
                        session_factory=lambda **k: None)


def test_every_agent_gets_compute_tools_even_without_listing_it(tmp_path):
    spec = AgentSpec(name="nogpu-listed", tier="open", category="specific",
                     title="t", description="d", capabilities=())  # no compute in caps
    reg = registry.build_registry_for(spec, is_subagent=True, ctx=_ctx(tmp_path))
    names = reg.names()
    assert any(n.startswith("compute_") for n in names), names


def test_spec_that_already_lists_compute_still_builds_and_has_compute_tools(tmp_path):
    spec = AgentSpec(name="gpu-listed", tier="open", category="specific",
                     title="t", description="d", capabilities=("compute-providers",))
    reg = registry.build_registry_for(spec, is_subagent=True, ctx=_ctx(tmp_path))
    names = reg.names()
    assert any(n.startswith("compute_") for n in names), names
