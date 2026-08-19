import pytest


@pytest.mark.xfail(strict=True, reason=(
    "DIRECTOR CALL, open — the f7632a6 contract sources `research` from "
    "pwm-agent-research; 7e5beeb put specs/research.py back on disk. Not a "
    "session's to decide: see singularity "
    "docs/plans/2026-08-08-director-calls-open.md. strict=True so the day "
    "the local file goes (the contract stands) this marker MUST come off "
    "in the commit that cites the decision."))
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
