from ai4science.harness.agents.spec import AgentSpec

AGENT = AgentSpec(
    name="openclaw",
    tier="open",
    category="core",
    title="OpenClaw",
    description="OpenClaw ACP bridge agent — drives the openclaw binary via ACP stdio JSON-RPC to the Gateway.",
    keywords=("openclaw", "acp", "gateway", "bridge"),
    system_prompt="You are an OpenClaw session. Complete the task given to you and report a concise result.",
)
