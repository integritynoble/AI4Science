from ai4science.harness.agents.specs.learning import AGENT, RUNNER
from ai4science.harness.agents.learning.agent import run_learning_task

def test_spec_shape():
    assert AGENT.name == "learning"
    assert AGENT.supported_profiles == ("I0", "I1", "I2")
    assert AGENT.default_profile == "I1"
    assert RUNNER is run_learning_task
