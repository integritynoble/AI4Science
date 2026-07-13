"""Appendix B sub-project 3b (Task 3): run_foundry_agent maps an ACTIVE foundry
record's owner-attested domain to a domain AgentSpec and runs it bound to the
agent. It refuses any record that is inactive, has no/unknown domain, or whose
ceiling is below the domain's floor -- no run is opened in those cases."""
from ai4science.harness.agents import foundry_runner as fr


class _RecClient:
    def __init__(self, rec): self._rec = rec
    def foundry_agent(self, agent_id): return self._rec


def _install_fake_imaging(monkeypatch):
    """Swap the imaging domain entry's runner for a spy so the unit test does
    not touch podman."""
    calls = []
    def _spy(*, client, store, agent_id, task_id, **kw):
        calls.append({"agent_id": agent_id, "task_id": task_id, "kw": kw})
        return {"status": "delivered"}
    monkeypatch.setitem(fr.DOMAIN_SPECS, "imaging", fr.DomainEntry(min_profile="A1", run=_spy))
    return calls


def test_active_imaging_agent_dispatches_bound(tmp_path, monkeypatch):
    calls = _install_fake_imaging(monkeypatch)
    client = _RecClient({"activation_state": "active", "ceiling": "A1", "domain": "imaging"})
    out = fr.run_foundry_agent(client=client, store=object(), agent_id="A", task_id="t",
                               workspace=tmp_path / "ws")
    assert out["ok"] is True
    assert out["agent_id"] == "A" and out["ceiling"] == "A1"
    assert out["result"]["status"] == "delivered"
    assert calls[0]["agent_id"] == "A"                 # ran bound to the record identity


def test_inactive_agent_refused(monkeypatch):
    _install_fake_imaging(monkeypatch)
    client = _RecClient({"activation_state": "quarantined", "ceiling": "A1", "domain": "imaging"})
    out = fr.run_foundry_agent(client=client, store=object(), agent_id="A", task_id="t")
    assert out["ok"] is False and "active" in out["reason"].lower()


def test_no_domain_refused(monkeypatch):
    _install_fake_imaging(monkeypatch)
    client = _RecClient({"activation_state": "active", "ceiling": "A1", "domain": ""})
    out = fr.run_foundry_agent(client=client, store=object(), agent_id="A", task_id="t")
    assert out["ok"] is False and "domain" in out["reason"].lower()


def test_unknown_domain_refused(monkeypatch):
    _install_fake_imaging(monkeypatch)
    client = _RecClient({"activation_state": "active", "ceiling": "A2", "domain": "bogus"})
    out = fr.run_foundry_agent(client=client, store=object(), agent_id="A", task_id="t")
    assert out["ok"] is False and "domain" in out["reason"].lower()


def test_below_floor_ceiling_refused(monkeypatch):
    _install_fake_imaging(monkeypatch)
    client = _RecClient({"activation_state": "active", "ceiling": "A0", "domain": "imaging"})
    out = fr.run_foundry_agent(client=client, store=object(), agent_id="A", task_id="t")
    assert out["ok"] is False and "ceiling" in out["reason"].lower()


def test_missing_record_refused(monkeypatch):
    _install_fake_imaging(monkeypatch)
    client = _RecClient({})                             # foundry_agent returned {} (fail-closed)
    out = fr.run_foundry_agent(client=client, store=object(), agent_id="A", task_id="t")
    assert out["ok"] is False
