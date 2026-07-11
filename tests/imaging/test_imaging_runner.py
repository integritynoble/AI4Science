def test_imaging_spec_exposes_runner():
    from ai4science.harness.agents.specs import imaging as spec
    from ai4science.harness.agents.imaging.agent import run_imaging_task
    assert spec.RUNNER is run_imaging_task
    assert spec.AGENT.name == "imaging"
