from ai4science.harness.agents.spec import AgentSpec

AGENT = AgentSpec(
    name="schema-validator",
    tier="open",
    category="hidden",
    title="Schema validator",
    description="Checks PWM artifacts against their schemas.",
    system_prompt="You validate PWM artifact schemas and report mismatches.",
)
