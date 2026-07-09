def test_missing_target_returns_hint():
    from ai4science.harness.agents import registry
    assert registry.install_hint("drug-design") == \
        "drug-design agent not installed — run: pip install pwm-agent-drug"


def test_research_is_dispatch_target_when_installed():
    from ai4science.harness.agents import registry
    registry.reload()
    assert registry.get("research") is not None
    # research is tier=science; a science main can dispatch to it
    assert "research" in registry.dispatchable_targets(registry.get("research"))
