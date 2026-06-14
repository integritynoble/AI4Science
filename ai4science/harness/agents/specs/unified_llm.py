from ai4science.harness.agents.spec import AgentSpec

AGENT = AgentSpec(
    name="unified-LLM",
    tier="open",
    category="core",
    title="Unified LLM",
    description="General coding assistant — one harness across Claude / ChatGPT / Gemini. No PWM data.",
    keywords=("general", "code", "claude", "chatgpt", "gemini", "common", "unified"),
    system_prompt=None,
    capabilities=("compute-providers",),
    # Base coding agent (one harness over Claude/ChatGPT/Gemini): main agent
    # only — never a sub-agent.
    allow_as_subagent=False,
    aliases=("common",),
    order=1,
)
