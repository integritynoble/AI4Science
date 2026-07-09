from ai4science.harness.agents import capabilities as cap


def _one_tool_provider(ctx):
    from ai4science.harness.tools.base import Tool
    return [Tool(name="xdemo", description="d", parameters={"type": "object", "properties": {}},
                 func=lambda workspace: "ok", mutating=False)]


def test_agent_bundle_survives_plugin_clear():
    cap.register_agent_bundle("x-demo", _one_tool_provider)
    assert "x-demo" in cap.CAPABILITY_BUNDLES
    cap.clear_plugin_bundles()                       # reload clears PLUGIN, not AGENT
    assert "x-demo" in cap.CAPABILITY_BUNDLES
    cap.clear_agent_bundles()
    assert "x-demo" not in cap.CAPABILITY_BUNDLES
