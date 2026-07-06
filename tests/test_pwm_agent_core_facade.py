import pwm_agent_core as core

def test_contract_surface_present():
    for name in ("AgentSpec", "BuildContext", "Tool", "reload", "get",
                 "dispatchable_targets", "build_registry_for",
                 "register_agent_bundle", "run_cli"):
        assert hasattr(core, name), f"missing {name}"

def test_versions_exposed():
    assert isinstance(core.CONTRACT_VERSION, int) and core.CONTRACT_VERSION >= 1
    assert isinstance(core.__version__, str) and core.__version__

def test_agentspec_is_the_real_type():
    from ai4science.harness.agents.spec import AgentSpec as Real
    assert core.AgentSpec is Real
