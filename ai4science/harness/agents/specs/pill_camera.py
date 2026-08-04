from ai4science.harness.agents.spec import AgentSpec

AGENT = AgentSpec(
    name="pill-camera",
    tier="science",
    category="specific",
    title="Pill camera",
    description="Wireless capsule endoscopy: lesion detection, reading-time reduction, cross-vendor evaluation.",
    keywords=("capsule endoscopy", "pillcam", "wireless capsule", "gi",
              "bleeding", "polyp", "kvasir", "cross-vendor"),
    capabilities=("pwm-actions", "pwm-data", "compute-providers", "science-router"),
    aliases=("capsule", "capsule-endoscopy", "pillcam"),
    supported_profiles=("I0", "I1", "I2"),
    default_profile="I1",
    approval_required_for=("publish", "deploy", "spend", "submit"),
    order=8,
)
