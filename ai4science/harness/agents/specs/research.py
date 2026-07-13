from ai4science.harness.agents.spec import AgentSpec

AGENT = AgentSpec(
    name="research2",
    tier="science",
    category="core",
    title="Research (governed)",
    description="Governed research agent: grounded synthesis over staged sources (A1).",
    keywords=("research", "synthesis", "citations", "sources", "grounding"),
    supported_profiles=("I0", "I1", "I2"),
    default_profile="I1",
    approval_required_for=("publish", "deploy", "spend"),
)

from ai4science.harness.agents.research.agent import run_research_task

RUNNER = run_research_task
