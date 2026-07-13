from ai4science.harness.agents.specs.work import AGENT, RUNNER
from ai4science.harness.agents.work.agent import run_work_task

def test_spec_shape():
    assert AGENT.name == "work"
    assert AGENT.supported_profiles == ("I0", "I1", "I2")
    assert AGENT.default_profile == "I1"
    assert "spend" in AGENT.approval_required_for
    assert RUNNER is run_work_task
