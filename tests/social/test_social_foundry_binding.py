"""Appendix B sub-project 3c (Task 1): run_social_task binds to a foundry
agent_id (the CP derives the ceiling), and foundry_runner dispatches the
`social` domain to it. Mirrors the imaging binding from 3b."""
from ai4science.harness.agents.social import agent as social_mod
from ai4science.harness.agents import foundry_runner as fr


class _FakeClient:
    """Captures open_run; short-circuits read so the flow stops at the draft
    (approve is None -> no post), keeping this a unit test (no podman)."""
    def __init__(self):
        self.open_run_calls = []
    def open_run(self, goal, capability_profile, hard_limits, interaction_profile="I1", agent_id=None):
        self.open_run_calls.append({"capability_profile": capability_profile, "agent_id": agent_id})
        return {"run_id": "R", "capability_profile": capability_profile}
    def sandbox_execute(self, run_id, command, scope=None, net_allowlist=None):
        # Return a shape _parse_stdout turns into a non-list -> run_social_task
        # returns {"status": "error", ...} before any post. Enough to assert
        # the open_run binding without a live sandbox.
        return {"is_error": True, "stdout": ""}
    def classify(self, run_id, boundary_kind, step_summary=""):
        return {"decision": "ASK"}


def test_run_social_task_binds_agent(monkeypatch):
    client = _FakeClient()
    social_mod.run_social_task(client=client, store=object(), task_id="s1",
                               mastodon_host="h:1", agent_id="agent-S", approve=None)
    assert client.open_run_calls[0]["agent_id"] == "agent-S"      # bound


def test_run_social_task_unbound_by_default(monkeypatch):
    client = _FakeClient()
    social_mod.run_social_task(client=client, store=object(), task_id="s2",
                               mastodon_host="h:1", approve=None)
    assert client.open_run_calls[0]["agent_id"] is None            # unbound, unchanged


def test_foundry_runner_dispatches_social_bound(monkeypatch):
    calls = []
    def _spy(*, client, store, agent_id, task_id, **kw):
        calls.append({"agent_id": agent_id, "kw": kw}); return {"status": "drafted"}
    monkeypatch.setitem(fr.DOMAIN_SPECS, "social", fr.DomainEntry(min_profile="A2", run=_spy))
    class _Rec:
        def foundry_agent(self, aid): return {"activation_state": "active", "ceiling": "A2", "domain": "social"}
    out = fr.run_foundry_agent(client=_Rec(), store=object(), agent_id="S", task_id="t",
                               mastodon_host="h:1", approve=None)
    assert out["ok"] is True and out["ceiling"] == "A2"
    assert calls[0]["agent_id"] == "S"                            # ran bound
    assert calls[0]["kw"]["mastodon_host"] == "h:1"               # **kw carried the host


def test_foundry_runner_refuses_social_below_a2_floor(monkeypatch):
    calls = []
    def _spy(*, client, store, agent_id, task_id, **kw):
        calls.append(agent_id); return {"status": "drafted"}
    monkeypatch.setitem(fr.DOMAIN_SPECS, "social", fr.DomainEntry(min_profile="A2", run=_spy))
    class _Rec:
        def foundry_agent(self, aid): return {"activation_state": "active", "ceiling": "A1", "domain": "social"}
    out = fr.run_foundry_agent(client=_Rec(), store=object(), agent_id="S", task_id="t",
                               mastodon_host="h:1")
    assert out["ok"] is False and "ceiling" in out["reason"].lower()
    assert calls == []                                            # never dispatched
