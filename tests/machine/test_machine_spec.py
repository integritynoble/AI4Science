from ai4science.harness.agents.specs.machine import AGENT, RUNNER
from ai4science.harness.agents.machine.agent import run_machine


def test_spec_shape():
    assert AGENT.name == "machine"
    assert AGENT.tier == "open" and AGENT.category == "core"
    assert "install" in AGENT.approval_required_for
    assert "login" in AGENT.approval_required_for
    assert "grant-permission" in AGENT.approval_required_for
    assert RUNNER is run_machine


def test_machine_is_discoverable_once_in_the_fleet():
    from ai4science.harness.agents.manager.agent import builtin_specs
    names = [s.name for s in builtin_specs()]
    assert names.count("machine") == 1
