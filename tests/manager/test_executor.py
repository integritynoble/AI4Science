from ai4science.harness.agents.manager.executor import execute_demand, GovernedExecutor


class FakeClient:
    """Stand-in control-plane client (its presence means 'governed runtime up')."""


def _fake_foundry(**kw):
    _fake_foundry.calls.append(kw)
    return {"ok": True, "agent_id": kw["agent_id"], "ceiling": "A1",
            "result": {"status": "done", "kw": kw}}
_fake_foundry.calls = []


def test_execute_demand_fail_closed_without_client():
    _fake_foundry.calls.clear()
    out = execute_demand(agent_id="A1", client=None, run_kwargs={"demand": {"intent": "x"}},
                         run_foundry=_fake_foundry)
    assert out["ok"] is False and "control plane" in out["reason"]
    assert _fake_foundry.calls == []            # no run attempted


def test_execute_demand_forwards_run_kwargs():
    _fake_foundry.calls.clear()
    execute_demand(agent_id="A9", client=FakeClient(), run_kwargs={"workspace": "/tmp/ws"},
                   run_foundry=_fake_foundry)
    call = _fake_foundry.calls[0]
    assert call["agent_id"] == "A9" and call["workspace"] == "/tmp/ws"


def test_executor_refuses_unregistered_agent():
    ex = GovernedExecutor(client=FakeClient(), agent_ids={"imaging": "A9"}, run_foundry=_fake_foundry)
    out = ex.run("work", "do coding")
    assert out["ok"] is False and "not enabled for execution" in out["reason"]


def test_executor_advisory_agent_runs_with_demand_kwargs():
    _fake_foundry.calls.clear()
    ex = GovernedExecutor(client=FakeClient(), agent_ids={"manager": "M1"}, run_foundry=_fake_foundry)
    out = ex.run("manager", "route this demand")
    assert out["ok"] is True
    assert _fake_foundry.calls[0]["demand"] == {"intent": "route this demand"}


def test_executor_input_agent_needs_input_without_sources():
    _fake_foundry.calls.clear()
    ex = GovernedExecutor(client=FakeClient(), agent_ids={"imaging": "I1"}, run_foundry=_fake_foundry)
    out = ex.run("imaging", "reconstruct the cassi scene")     # no sources
    assert out["ok"] is False and "needs input" in out["reason"] and out["missing"] == ["workspace"]
    assert _fake_foundry.calls == []            # fail-closed: no run


def test_executor_input_agent_runs_with_workspace():
    _fake_foundry.calls.clear()
    ex = GovernedExecutor(client=FakeClient(), agent_ids={"imaging": "I1"}, run_foundry=_fake_foundry)
    out = ex.run("imaging", "reconstruct", sources={"workspace": "/data/scene1"})
    assert out["ok"] is True
    assert _fake_foundry.calls[0]["workspace"] == "/data/scene1"


def test_executor_fail_closed_without_client():
    ex = GovernedExecutor(client=None, agent_ids={"imaging": "I1"})
    assert ex.run("imaging", "x", sources={"workspace": "/w"})["ok"] is False


def test_executor_default_sources_enable_input_agent_from_chat():
    # owner pre-configures imaging's workspace so a source-less chat demand can run
    _fake_foundry.calls.clear()
    ex = GovernedExecutor(client=FakeClient(), agent_ids={"imaging": "I1"},
                          default_sources={"imaging": {"workspace": "/scene/current"}},
                          run_foundry=_fake_foundry)
    out = ex.run("imaging", "reconstruct")            # no explicit sources
    assert out["ok"] is True and _fake_foundry.calls[0]["workspace"] == "/scene/current"


def test_explicit_sources_override_defaults():
    _fake_foundry.calls.clear()
    ex = GovernedExecutor(client=FakeClient(), agent_ids={"imaging": "I1"},
                          default_sources={"imaging": {"workspace": "/scene/default"}},
                          run_foundry=_fake_foundry)
    ex.run("imaging", "reconstruct", sources={"workspace": "/scene/override"})
    assert _fake_foundry.calls[0]["workspace"] == "/scene/override"
