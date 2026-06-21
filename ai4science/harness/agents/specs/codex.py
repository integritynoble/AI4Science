from ai4science.harness.agents.spec import AgentSpec

AGENT = AgentSpec(
    name="codex",
    tier="open",
    category="core",
    title="Codex",
    description="The official OpenAI Codex agent — same as OpenAI's, full coding toolset. GPU via providers.",
    keywords=("codex", "openai", "chatgpt", "coding", "agent"),
    system_prompt=None,
    # Same as OpenAI's Codex: NO PWM registry/moat (no pwm_search), but CAN use
    # GPU directly via compute-providers.
    capabilities=("compute-providers",),
    # Base coding agent (the original Codex): main agent only — never a sub-agent.
    allow_as_subagent=False,
    default_backend="openai",
    order=4,
)
