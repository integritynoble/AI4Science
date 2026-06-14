from ai4science.harness.agents.spec import AgentSpec

AGENT = AgentSpec(
    name="claude-code",
    tier="open",
    category="core",
    title="Claude Code",
    description="The official Claude Code agent — Anthropic backend, full coding toolset. Compute via providers.",
    keywords=("claude", "code", "anthropic", "coding", "agent", "claude code"),
    system_prompt=None,
    capabilities=("compute-providers",),
    # Base coding agent (the original Claude Code): main agent only — never a
    # sub-agent. Domain agents are the contributable/composable ones.
    allow_as_subagent=False,
    aliases=("claude code", "cc"),
    default_backend="anthropic",
    order=4,
)
