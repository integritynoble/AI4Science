from ai4science.harness.agents.spec import AgentSpec

AGENT = AgentSpec(
    name="claude-code",
    tier="open",
    category="core",
    title="Claude Code",
    description="The official Claude Code agent — same as Anthropic's, full coding toolset. GPU via providers.",
    keywords=("claude", "code", "anthropic", "coding", "agent", "claude code"),
    system_prompt=None,
    # Same as Anthropic's Claude Code: NO PWM registry/moat (no pwm_search), but
    # CAN use GPU directly via compute-providers.
    capabilities=("compute-providers",),
    # Base coding agent (the original Claude Code): main agent only — never a
    # sub-agent. Domain agents are the contributable/composable ones.
    allow_as_subagent=False,
    aliases=("claude code", "cc"),
    default_backend="anthropic",
    order=4,
)
