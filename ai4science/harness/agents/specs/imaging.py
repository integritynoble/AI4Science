from ai4science.harness.agents.spec import AgentSpec

AGENT = AgentSpec(
    name="imaging",
    tier="science",
    category="specific",
    title="Computational Imaging",
    description="Dual-mode computational-imaging agent (CASSI reconstruction, A1).",
    keywords=("cassi", "reconstruction", "computational imaging", "optics"),
    supported_profiles=("I0", "I1", "I2"),
    default_profile="I1",
    approval_required_for=("publish", "deploy", "spend"),
)

from ai4science.harness.agents.imaging.agent import run_imaging_task

# Entry point the dispatcher uses to run this agent on the dual-mode runtime.
RUNNER = run_imaging_task
