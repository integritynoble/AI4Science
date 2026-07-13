from ai4science.harness.agents.spec import AgentSpec

AGENT = AgentSpec(
    name="work",
    tier="open",
    category="core",
    title="General Work",
    description="Dual-mode general work agent (coding, data analysis, files; A1 sandbox).",
    keywords=("coding", "data analysis", "files", "work", "general"),
    supported_profiles=("I0", "I1", "I2"),
    default_profile="I1",
    approval_required_for=("publish", "deploy", "spend"),
)

from ai4science.harness.agents.work.agent import run_work_task

# Entry point the dispatcher uses to run this agent on the dual-mode runtime.
# Ships in-tree (pwm_agent.specs-discoverable shape); the standalone
# pwm-agent-work distribution wheel is the installer sub-project's job.
RUNNER = run_work_task
