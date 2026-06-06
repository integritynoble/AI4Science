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
    aliases=("common",),
)
