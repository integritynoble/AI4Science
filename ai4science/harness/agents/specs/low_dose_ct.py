from ai4science.harness.agents.spec import AgentSpec

AGENT = AgentSpec(
    name="low-dose-ct",
    tier="science",
    category="specific",
    title="Low-dose CT",
    description="Diagnostic CT from fewer photons: reconstruction, dose equivalence, task-based image quality.",
    keywords=("low-dose", "sparse-view", "limited-angle", "photon-counting",
              "dual-energy", "ct", "reconstruction", "denoising", "detectability"),
    capabilities=("pwm-actions", "pwm-data", "ci-algorithms", "forward-model",
                  "compute-providers", "science-router"),
    aliases=("ldct", "low dose ct"),
    supported_profiles=("I0", "I1", "I2"),
    default_profile="I1",
    approval_required_for=("publish", "deploy", "spend", "submit"),
    order=6,
)
