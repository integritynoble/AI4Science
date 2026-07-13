from ai4science.harness.agents.specs.process_learning import AGENT, RUNNER
from ai4science.harness.agents.process_learning.agent import run_process_learning_task


def test_spec_shape():
    assert AGENT.name == "process-learning"
    assert AGENT.supported_profiles == ("I0", "I1", "I2")
    assert AGENT.default_profile == "I1"
    assert RUNNER is run_process_learning_task
