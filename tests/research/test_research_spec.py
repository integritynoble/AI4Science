from ai4science.harness.agents.specs.research import AGENT, RUNNER
from ai4science.harness.agents.research.agent import run_research_task

def test_spec_shape():
    assert AGENT.name == "research"
    assert AGENT.supported_profiles == ("I0", "I1", "I2")
    assert AGENT.default_profile == "I1"
    assert RUNNER is run_research_task
