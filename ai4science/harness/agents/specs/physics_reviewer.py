from ai4science.harness.agents.spec import AgentSpec

AGENT = AgentSpec(
    name="physics-reviewer",
    tier="science",
    category="hidden",
    title="Physics reviewer",
    description="Reviews a PWM submission for physical consistency.",
    capabilities=("pwm-data",),
    system_prompt=("You are a physics reviewer. Inspect the workspace and report "
                   "concerns about physical consistency. Ground your review in the "
                   "registry: use pwm_principle / pwm_spec (the digital-twin "
                   "forward model — six_tuple, protocol_fields, d_spec) and "
                   "pwm_benchmark to check the submission against the registered "
                   "forward model and protocol. You cannot override the "
                   "deterministic Physics Judge."),
)
