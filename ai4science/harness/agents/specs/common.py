from ai4science.harness.agents.spec import AgentSpec

AGENT = AgentSpec(
    name="common",
    tier="open",
    category="core",
    title="Common (Claude Code)",
    description="General coding assistant — Claude Code across brands. No PWM access.",
    keywords=("general", "code", "claude"),
    system_prompt=None,
)
