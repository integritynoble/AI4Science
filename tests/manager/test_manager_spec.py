from ai4science.harness.agents.specs.manager import AGENT, RUNNER
from ai4science.harness.agents.manager.agent import run_manager


def test_spec_shape():
    assert AGENT.name == "manager"
    assert AGENT.default_profile == "I0"          # explain/propose-first
    assert AGENT.allow_as_subagent is False       # the console is not a sub-agent
    assert "run-agent" in AGENT.approval_required_for
    assert "promote" in AGENT.approval_required_for
    assert RUNNER is run_manager
