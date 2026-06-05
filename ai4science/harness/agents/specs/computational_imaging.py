from ai4science.harness.agents.spec import AgentSpec

AGENT = AgentSpec(
    name="computational-imaging",
    tier="science",
    category="specific",
    title="Computational imaging",
    description="Snapshot/compressive spectral imaging (CASSI), reconstruction, optics.",
    keywords=("cassi", "spectral", "optics", "reconstruction", "hyperspectral",
              "snapshot", "imaging", "inverse problem"),
    system_prompt=(
        "You are AI4Science specialized in computational imaging (snapshot "
        "compressive / spectral imaging such as CASSI, reconstruction, optical "
        "encoding). You have the generic coding tools AND read-only access to the "
        "PWM registry (pwm_principles/benchmarks/solutions/overview). Ground every "
        "design in the registered imaging principles, benchmarks and best solutions "
        "(consult pwm_solutions before proposing a new approach)."),
    capabilities=("pwm-actions", "pwm-data"),
)
