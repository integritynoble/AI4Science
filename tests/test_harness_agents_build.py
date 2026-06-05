from ai4science.harness.agents.spec import AgentSpec
from ai4science.harness.agents.context import BuildContext
from ai4science.harness.agents.registry import build_registry_for


def _ctx(tmp_path):
    return BuildContext(workspace=tmp_path, brand_provider=lambda: ("gemini", "m"),
                        session_factory=lambda **k: None)


def test_base_tools_present_for_every_agent(tmp_path):
    spec = AgentSpec(name="x", tier="open", category="core", title="X", description="d")
    reg = build_registry_for(spec, is_subagent=False, ctx=_ctx(tmp_path))
    names = set(reg.names())
    assert {"read", "write", "edit", "grep", "glob", "bash"} <= names  # Claude Code first


def test_open_agent_has_no_pwm_tools(tmp_path):
    spec = AgentSpec(name="common", tier="open", category="core", title="C", description="d")
    reg = build_registry_for(spec, is_subagent=False, ctx=_ctx(tmp_path))
    assert not any(n.startswith("pwm_") for n in reg.names())


def test_science_capabilities_add_tools(tmp_path):
    spec = AgentSpec(name="research", tier="science", category="core", title="R",
                     description="d", capabilities=("pwm-actions", "pwm-data"))
    reg = build_registry_for(spec, is_subagent=False, ctx=_ctx(tmp_path))
    names = set(reg.names())
    assert "pwm_solutions" in names and "pwm_status" in names


def test_extra_tools_honored(tmp_path):
    from ai4science.harness.tools.base import Tool
    marker = Tool("marker", "d", {"type": "object", "properties": {}}, lambda ws: "ok")
    spec = AgentSpec(name="x", tier="open", category="core", title="X", description="d",
                     extra_tools=lambda ctx: [marker])
    reg = build_registry_for(spec, is_subagent=False, ctx=_ctx(tmp_path))
    assert "marker" in reg.names()
