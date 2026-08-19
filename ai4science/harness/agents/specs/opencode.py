from ai4science.harness.agents.spec import AgentSpec

AGENT = AgentSpec(
    name="opencode",
    tier="open",
    category="core",
    title="OpenCode",
    description="OpenCode CLI agent — drives the opencode binary via tmux.",
    system_prompt="You are an OpenCode session. Complete the task given to you and report a concise result.",
)
