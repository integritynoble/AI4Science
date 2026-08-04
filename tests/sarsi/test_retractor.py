"""Taking a post down — the call `undo` had nothing to make.

The handle says *which* post. This is the part that acts on it. Everything here
is shaped by one asymmetry: **failing to delete leaves a post up, which the
owner can see and retry; deleting the wrong thing cannot be undone at all.** So
every ambiguity resolves toward doing nothing.

  * a platform with **no delete endpoint** is refused by name, not attempted;
  * a **non-2xx** answer means it is still published, and says so;
  * a **404** is not called success. "Already gone" and "wrong id" look
    identical from here, and one of them means this retraction deleted nothing
    while reporting that it did;
  * the token comes from the **vault**, so a refused secret stops it.
"""
import pytest

from ai4science.harness.agents.sarsi import (outward, registry as reg,
                                             transmit, undo as ud, vault)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def config(tmp_path):
    c = reg.parse(reg.default_config(owner_id="7007143162"), root=tmp_path)
    c.ensure_dirs()
    return c


@pytest.fixture
def agent(config):
    return config.agents["social"]


def _act(handle="110045", destination="x"):
    return ud.Act(kind="post", destination=destination, digest="d1", chars=12,
                  task_id="tsk_1", handle=handle)


def _http(status, answer=None, seen=None):
    def call(*, url, token, timeout):
        if seen is not None:
            seen.append({"url": url, "token": token})
        return status, (answer or {})
    return call


# ── every platform says how to delete, or says it cannot ──────────────

def test_each_platform_declares_a_delete_endpoint_or_none():
    for name, spec in transmit.PLATFORMS.items():
        assert "delete_url" in spec, f"{name} says nothing about deleting"


# ── taking one down ───────────────────────────────────────────────────

def test_it_calls_the_platform_with_the_handle(config, agent):
    vault.put(config, "x.token", "t0ken")
    seen = []
    pull = transmit.retractor(config, agent, platform="x", secret="x.token",
                              prompt=lambda **kw: "yes",
                              http=_http(200, seen=seen))
    pull(_act("110045"))
    assert "110045" in seen[0]["url"]


def test_it_uses_the_token_the_vault_released(config, agent):
    vault.put(config, "x.token", "t0ken")
    seen = []
    pull = transmit.retractor(config, agent, platform="x", secret="x.token",
                              prompt=lambda **kw: "yes",
                              http=_http(200, seen=seen))
    pull(_act())
    assert seen[0]["token"] == "t0ken"


def test_a_refused_secret_stops_it(config, agent):
    vault.put(config, "x.token", "t0ken")
    seen = []
    pull = transmit.retractor(config, agent, platform="x", secret="x.token",
                              prompt=lambda **kw: "no", http=_http(200, seen=seen))
    with pytest.raises(transmit.TransmitFailed):
        pull(_act())
    assert seen == []


# ── every ambiguity resolves toward doing nothing ─────────────────────

def test_a_platform_that_cannot_delete_is_refused_by_name(config, agent):
    vault.put(config, "x.token", "t0ken")
    transmit.PLATFORMS["nodelete"] = {"url": "u", "limit": None, "field": "text",
                                      "id_field": "id", "delete_url": None}
    try:
        with pytest.raises(transmit.NoTransmitter, match="nodelete"):
            transmit.retractor(config, agent, platform="nodelete",
                               secret="x.token", prompt=lambda **kw: "yes",
                               http=_http(200))
    finally:
        transmit.PLATFORMS.pop("nodelete")


def test_a_non_2xx_says_it_is_still_published(config, agent):
    vault.put(config, "x.token", "t0ken")
    pull = transmit.retractor(config, agent, platform="x", secret="x.token",
                              prompt=lambda **kw: "yes",
                              http=_http(500, {"error": "boom"}))
    with pytest.raises(transmit.TransmitFailed) as e:
        pull(_act())
    assert "still" in str(e.value).lower()


def test_a_404_is_not_called_success(config, agent):
    """'Already gone' and 'wrong id' look identical from here, and one of them
    means this deleted nothing while reporting that it did."""
    vault.put(config, "x.token", "t0ken")
    pull = transmit.retractor(config, agent, platform="x", secret="x.token",
                              prompt=lambda **kw: "yes", http=_http(404))
    with pytest.raises(transmit.TransmitFailed) as e:
        pull(_act())
    assert "404" in str(e.value) or "no such" in str(e.value).lower()


def test_an_act_with_no_handle_is_refused_before_any_call(config, agent):
    vault.put(config, "x.token", "t0ken")
    seen = []
    pull = transmit.retractor(config, agent, platform="x", secret="x.token",
                              prompt=lambda **kw: "yes",
                              http=_http(200, seen=seen))
    with pytest.raises(transmit.TransmitFailed):
        pull(_act(handle=""))
    assert seen == []


def test_a_transport_error_leaves_it_published(config, agent):
    vault.put(config, "x.token", "t0ken")

    def broken(*, url, token, timeout):
        raise OSError("network down")

    pull = transmit.retractor(config, agent, platform="x", secret="x.token",
                              prompt=lambda **kw: "yes", http=broken)
    with pytest.raises(transmit.TransmitFailed):
        pull(_act())


# ── through undo ──────────────────────────────────────────────────────

def test_undo_retracts_a_real_post_through_it(config, agent):
    vault.put(config, "x.token", "t0ken")

    def publishes(act, *, body):
        publishes.handle = "110045"
        return body

    outward.request(config, agent,
                    outward.Act(agent_id=agent.id, kind="post", destination="x",
                                body="a short post", task_id="tsk_1"),
                    transmit=publishes, approve=lambda **kw: "yes")
    seen = []
    pull = transmit.retractor(config, agent, platform="x", secret="x.token",
                              prompt=lambda **kw: "yes",
                              http=_http(200, seen=seen))
    ud.retract(config, agent, retractor=pull)
    assert "110045" in seen[0]["url"]
    assert ud.last(config, agent) is None


def test_a_failed_takedown_leaves_the_act_outstanding(config, agent):
    """It is still published, so it is still the thing `undo` would take back."""
    vault.put(config, "x.token", "t0ken")

    def publishes(act, *, body):
        publishes.handle = "110045"
        return body

    outward.request(config, agent,
                    outward.Act(agent_id=agent.id, kind="post", destination="x",
                                body="a short post", task_id="tsk_1"),
                    transmit=publishes, approve=lambda **kw: "yes")
    pull = transmit.retractor(config, agent, platform="x", secret="x.token",
                              prompt=lambda **kw: "yes", http=_http(500))
    with pytest.raises(ud.Failed):
        ud.retract(config, agent, retractor=pull)
    assert ud.last(config, agent) is not None
