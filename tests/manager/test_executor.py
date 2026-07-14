from ai4science.harness.agents.manager.executor import execute_demand, GovernedExecutor


class FakeClient:
    """A stand-in control-plane client (its presence just means 'governed runtime up')."""


def _fake_foundry(**kw):
    _fake_foundry.calls.append(kw)
    return {"ok": True, "agent_id": kw["agent_id"], "ceiling": "A1",
            "result": {"status": "done", "echo": kw.get("demand")}}
_fake_foundry.calls = []


def test_execute_demand_fail_closed_without_client():
    _fake_foundry.calls.clear()
    out = execute_demand(agent_id="A1", demand="do it", client=None, run_foundry=_fake_foundry)
    assert out["ok"] is False and "control plane" in out["reason"]
    assert _fake_foundry.calls == []            # no run attempted


def test_execute_demand_delegates_to_foundry_and_forwards_demand():
    _fake_foundry.calls.clear()
    out = execute_demand(agent_id="A9", demand="reconstruct", client=FakeClient(),
                         run_foundry=_fake_foundry)
    assert out["ok"] is True and out["agent_id"] == "A9"
    call = _fake_foundry.calls[0]
    assert call["agent_id"] == "A9" and call["demand"] == {"intent": "reconstruct"}


def test_governed_executor_refuses_unregistered_agent():
    ex = GovernedExecutor(client=FakeClient(), agent_ids={"imaging": "A9"},
                          run_foundry=_fake_foundry)
    out = ex.run("work", "do coding")
    assert out["ok"] is False and "not enabled for execution" in out["reason"]


def test_governed_executor_runs_registered_agent():
    _fake_foundry.calls.clear()
    ex = GovernedExecutor(client=FakeClient(), agent_ids={"imaging": "A9"},
                          run_foundry=_fake_foundry)
    out = ex.run("imaging", "reconstruct the cassi scene")
    assert out["ok"] is True and out["result"]["status"] == "done"
    assert _fake_foundry.calls[0]["agent_id"] == "A9"


def test_governed_executor_fail_closed_without_client():
    ex = GovernedExecutor(client=None, agent_ids={"imaging": "A9"})
    assert ex.run("imaging", "x")["ok"] is False
