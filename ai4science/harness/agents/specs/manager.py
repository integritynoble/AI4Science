from ai4science.harness.agents.spec import AgentSpec

AGENT = AgentSpec(
    name="manager",
    tier="open",
    category="core",
    title="Manager",
    description="Owner console: scope-routes demands, monitors the fleet read-only, and proposes owner-gated actions. No authority.",
    keywords=("manager", "console", "route", "monitor", "coordinate", "propose"),
    supported_profiles=("I0", "I1", "I2"),
    default_profile="I0",
    approval_required_for=("create-agent", "run-agent", "promote", "publish", "deploy", "spend"),
    allow_as_subagent=False,
)

from ai4science.harness.agents.manager.agent import run_manager

RUNNER = run_manager
