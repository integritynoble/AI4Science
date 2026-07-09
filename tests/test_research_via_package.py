def test_research_sourced_from_package_not_local_file():
    import os
    from ai4science.harness.agents import registry
    registry.reload()
    spec = registry.get("research")
    assert spec is not None and spec.name == "research"
    assert not os.path.exists(
        "ai4science/harness/agents/specs/research.py"), "builtin research spec should be deleted"
    assert spec.capabilities == ("pwm-actions", "pwm-data", "onboarding",
        "compute-providers", "ci-algorithms", "forward-model", "science-router")
