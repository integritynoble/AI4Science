from ai4science.harness.agents.spec import AgentSpec

AGENT = AgentSpec(
    name="physics-reviewer",
    tier="open",
    category="hidden",
    title="Physics reviewer",
    description="Reviews a PWM submission for physical consistency.",
    system_prompt=("You are a physics reviewer. Inspect the workspace and report "
                   "concerns about physical consistency. You cannot override the "
                   "deterministic Physics Judge."),
)
