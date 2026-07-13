from ai4science.harness.agents.spec import AgentSpec

AGENT = AgentSpec(
    name="process-learning",
    tier="open",
    category="core",
    title="Work-Process Learning",
    description="Governed trace-explainer: grounded tutorial/postmortem of a verified agent trace (A1).",
    keywords=("process", "trace", "explanation", "tutorial", "postmortem", "transparency"),
    supported_profiles=("I0", "I1", "I2"),
    default_profile="I1",
    approval_required_for=("publish", "deploy", "spend"),
)

from ai4science.harness.agents.process_learning.agent import run_process_learning_task

RUNNER = run_process_learning_task
