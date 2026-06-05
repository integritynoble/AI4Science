from ai4science.harness.agents import registry
from ai4science.harness.agents.context import BuildContext
from ai4science.harness.agents.registry import build_registry_for


def _ctx(tmp_path):
    return BuildContext(workspace=tmp_path, brand_provider=lambda: ("gemini", "m"),
                        session_factory=lambda **k: None)


def test_common_is_walled_off(tmp_path):
    registry.reload()
    reg = build_registry_for(registry.get("common"), is_subagent=False, ctx=_ctx(tmp_path))
    names = set(reg.names())
    assert not any(n.startswith("pwm_") for n in names)
    assert "paper_review" not in names
    assert "task" in names
    out = reg.get("task").func(tmp_path, subagent_type="research", prompt="x")
    assert "available" in out.lower() and "research" in out


def test_science_agents_hold_the_moat(tmp_path):
    registry.reload()
    reg = build_registry_for(registry.get("research"), is_subagent=False, ctx=_ctx(tmp_path))
    assert "pwm_solutions" in reg.names()
    from ai4science.harness.agents.registry import dispatchable_targets
    assert "computational-imaging" in dispatchable_targets(registry.get("research"))
