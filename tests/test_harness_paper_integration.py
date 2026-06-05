from ai4science.harness.agents import registry
from ai4science.harness.agents.context import BuildContext
from ai4science.harness.agents.registry import build_registry_for
from ai4science.harness.agents import capabilities


def _ctx(tmp_path):
    return BuildContext(workspace=tmp_path, brand_provider=lambda: ("gemini", "m"),
                        session_factory=lambda **k: None)


def test_paper_review_bundle_registered(tmp_path):
    assert "paper-review" in capabilities.CAPABILITY_BUNDLES
    tools = capabilities.resolve_capability("paper-review", _ctx(tmp_path))
    assert "paper_review" in {t.name for t in tools}


def test_paper_spec_discovered():
    registry.reload()
    paper = registry.get("paper")
    assert paper is not None and paper.tier == "science"
    assert "paper-review" in paper.capabilities


def test_paper_in_core_menu():
    registry.reload()
    assert "paper" in {s.name for s in registry.core_agents()}


def test_paper_agent_has_review_tool_common_does_not(tmp_path):
    registry.reload()
    preg = build_registry_for(registry.get("paper"), is_subagent=False, ctx=_ctx(tmp_path))
    assert "paper_review" in preg.names()
    creg = build_registry_for(registry.get("common"), is_subagent=False, ctx=_ctx(tmp_path))
    assert "paper_review" not in creg.names()
