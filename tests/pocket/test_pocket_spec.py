from ai4science.harness.agents.specs.pocket import AGENT, RUNNER
from ai4science.harness.agents.pocket.agent import run_pocket


def test_spec_shape():
    assert AGENT.name == "pocket"
    assert AGENT.tier == "open"
    assert AGENT.category == "core"
    assert "spend" in AGENT.approval_required_for
    assert "publish" in AGENT.approval_required_for
    assert RUNNER is run_pocket


def test_pocket_is_discoverable_without_shadowing():
    # pocket is registered exactly once in the routable fleet (no shadowing).
    from ai4science.harness.agents.manager.agent import builtin_specs
    names = [s.name for s in builtin_specs()]
    assert names.count("pocket") == 1
