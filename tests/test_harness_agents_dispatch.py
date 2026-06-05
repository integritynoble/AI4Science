from ai4science.harness.agents import registry
from ai4science.harness.agents.spec import AgentSpec
from ai4science.harness.agents.context import BuildContext
from ai4science.harness.agents.registry import (
    build_registry_for, dispatchable_targets, _can_dispatch)


def _ctx(tmp_path, recorder=None):
    def factory(*, spec, ctx):
        if recorder is not None:
            recorder.append(spec.name)
        class _S:  # minimal fake child session
            def run_turn(self, text, images=None):
                return f"child[{spec.name}] ran"
        return _S()
    return BuildContext(workspace=tmp_path, brand_provider=lambda: ("gemini", "m"),
                        session_factory=factory)


def test_can_dispatch_rule():
    open_a = AgentSpec(name="o", tier="open", category="hidden", title="o", description="d")
    sci_a = AgentSpec(name="s", tier="science", category="core", title="s", description="d")
    assert _can_dispatch(open_a, open_a) is True
    assert _can_dispatch(open_a, sci_a) is False
    assert _can_dispatch(sci_a, sci_a) is True
    assert _can_dispatch(sci_a, open_a) is True


def test_common_dispatch_excludes_science():
    registry.reload()
    targets = dispatchable_targets(registry.get("common"))
    assert "general-purpose" in targets
    assert "research" not in targets and "computational-imaging" not in targets


def test_research_dispatch_includes_science():
    registry.reload()
    targets = dispatchable_targets(registry.get("research"))
    assert {"research", "computational-imaging", "general-purpose"} <= set(targets)


def test_main_has_task_tool_subagent_does_not(tmp_path):
    registry.reload()
    research = registry.get("research")
    main = build_registry_for(research, is_subagent=False, ctx=_ctx(tmp_path))
    sub = build_registry_for(research, is_subagent=True, ctx=_ctx(tmp_path))
    assert "task" in main.names()
    assert "task" not in sub.names()


def test_task_tool_runs_child(tmp_path):
    registry.reload()
    rec = []
    ctx = _ctx(tmp_path, recorder=rec)
    reg = build_registry_for(registry.get("research"), is_subagent=False, ctx=ctx)
    out = reg.get("task").func(tmp_path, subagent_type="general-purpose", prompt="hi")
    assert "child[general-purpose] ran" in out and rec == ["general-purpose"]


def test_task_tool_rejects_out_of_tier(tmp_path):
    registry.reload()
    reg = build_registry_for(registry.get("common"), is_subagent=False, ctx=_ctx(tmp_path))
    out = reg.get("task").func(tmp_path, subagent_type="research", prompt="hi")
    assert "research" in out and "available" in out.lower()


def test_task_tool_exposes_enum(tmp_path):
    registry.reload()
    reg = build_registry_for(registry.get("common"), is_subagent=False, ctx=_ctx(tmp_path))
    schema = reg.get("task").parameters
    enum = schema["properties"]["subagent_type"]["enum"]
    assert "general-purpose" in enum
    assert "research" not in enum  # science excluded for an open main
