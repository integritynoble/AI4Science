import pwm_agent_core as core


def test_contract_is_v1():
    # Guard: bump this assertion AND core.CONTRACT_VERSION together when the
    # runtime contract surface (AgentSpec, registry/discovery API, dispatch,
    # login/wallet, compute client) changes. A silent change fails here.
    assert core.CONTRACT_VERSION == 1
