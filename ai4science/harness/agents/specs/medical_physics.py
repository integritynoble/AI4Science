from ai4science.harness.agents.spec import AgentSpec

AGENT = AgentSpec(
    name="medical-physics",
    tier="science",
    category="specific",
    title="Medical physics",
    description="Radiotherapy physics: planning, dose calculation, adaptive RT, QA. Produces candidates; a physicist signs.",
    keywords=("radiotherapy", "treatment planning", "dose", "imrt", "vmat",
              "adaptive", "proton", "flash", "brachytherapy", "qa", "dosimetry"),
    capabilities=("pwm-actions", "pwm-data", "compute-providers", "science-router"),
    aliases=("radiotherapy", "medphys", "rt-physics"),
    supported_profiles=("I0", "I1", "I2"),
    default_profile="I1",
    # Everything that could reach a patient is an approval, at every ceiling.
    approval_required_for=("publish", "deploy", "spend", "submit", "plan-export"),
    order=7,
)
