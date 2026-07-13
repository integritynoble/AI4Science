from ai4science.harness.agents.spec import AgentSpec

AGENT = AgentSpec(
    name="learning",
    tier="open",
    category="core",
    title="Personal Learning",
    description="Governed tutor: grounded study guide + quiz over staged material (A1).",
    keywords=("learning", "tutor", "quiz", "study", "capability"),
    supported_profiles=("I0", "I1", "I2"),
    default_profile="I1",
    approval_required_for=("publish", "deploy", "spend"),
)

from ai4science.harness.agents.learning.agent import run_learning_task

RUNNER = run_learning_task
