from ai4science.harness.agents import registry
from ai4science.harness.agents.registry import build_registry_for
from ai4science.harness.agents.context import BuildContext


def _ctx(tmp_path):
    def factory(*, spec, ctx):
        class _S:  # minimal fake child session; should never be reached in these tests
            def run_turn(self, text, images=None):
                return f"child[{spec.name}] ran"
        return _S()
    return BuildContext(workspace=tmp_path, brand_provider=lambda: ("gemini", "m"),
                        session_factory=factory)


def test_install_hint_format():
    assert registry.install_hint("research") == \
        "research agent not installed — run: pip install pwm-agent-research"


def test_install_hint_uses_distribution_name_map_not_naive_formula():
    # spec name != dist name for several agents; naive f"pwm-agent-{name}" is wrong.
    assert registry.install_hint("drug-design") == \
        "drug-design agent not installed — run: pip install pwm-agent-drug"
    assert registry.install_hint("computational-imaging") == \
        "computational-imaging agent not installed — run: pip install pwm-agent-imaging"


def test_install_hint_falls_back_for_unmapped_name():
    assert registry.install_hint("some-plugin") == \
        "some-plugin agent not installed — run: pip install pwm-agent-some-plugin"


def test_task_tool_returns_install_hint_for_known_uninstalled_agent(tmp_path, monkeypatch):
    registry.reload()
    # Simulate a first-party splittable agent name whose package is not
    # installed (claude-code/codex are both installed as specs in this dev
    # environment, so we synthesize a stand-in rather than assert on those).
    fake_name = "claude-gpu-not-installed"
    monkeypatch.setattr(registry, "_SPLITTABLE_AGENTS",
                         registry._SPLITTABLE_AGENTS | {fake_name})
    assert registry.AGENT_REGISTRY.get(fake_name) is None
    assert fake_name in registry._SPLITTABLE_AGENTS
    reg = build_registry_for(registry.get("research"), is_subagent=False, ctx=_ctx(tmp_path))
    out = reg.get("task").func(tmp_path, subagent_type=fake_name, prompt="hi")
    assert out == registry.install_hint(fake_name)


def test_install_hint_gpu_agents_use_gpu_dist_names():
    from ai4science.harness.agents import registry
    assert registry.install_hint("claude-code") == \
        "claude-code agent not installed — run: pip install pwm-agent-claude-gpu"
    assert registry.install_hint("codex") == \
        "codex agent not installed — run: pip install pwm-agent-codex-gpu"


def test_task_tool_still_reports_unknown_for_unrecognized_name(tmp_path):
    registry.reload()
    reg = build_registry_for(registry.get("research"), is_subagent=False, ctx=_ctx(tmp_path))
    out = reg.get("task").func(tmp_path, subagent_type="totally-bogus", prompt="hi")
    assert "unknown subagent_type" in out and "available" in out.lower()
