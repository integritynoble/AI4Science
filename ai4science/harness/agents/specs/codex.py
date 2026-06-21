from ai4science.harness.agents.spec import AgentSpec

AGENT = AgentSpec(
    name="codex",
    tier="open",
    category="core",
    title="Codex",
    description="The official OpenAI Codex agent — ChatGPT/codex backend, full coding toolset. Compute via providers.",
    keywords=("codex", "openai", "chatgpt", "coding", "agent"),
    system_prompt=None,
    capabilities=("compute-providers",),
    # Base coding agent (the original Codex): main agent only — never a sub-agent.
    allow_as_subagent=False,
    default_backend="openai",
    order=3,
)
