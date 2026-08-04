"""Recording what the platform called it, so a post can actually be taken back.

`undo` can retract a post only if something identifies **which** post. Nothing
recorded one: the `post` transmitter returns the published text — for the
approved-bytes check — and threw the platform's id away. So the single genuinely
retractable outward act reported itself unavailable.

The hazard in fixing this is attribution. The handle arrives out-of-band from the
transmitter, so a stale one from the previous post could be recorded against the
next, and a retraction would then delete **the wrong thing** — worse than the
gap it was meant to close. So the handle is cleared before every transmission
and only a handle set during *this* one is kept.

And the ledger still stores no body: a handle identifies, it does not reproduce.
"""
import pytest

from ai4science.harness.agents.sarsi import (ledger, outward, registry as reg,
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


def _act(agent, body="a short post"):
    return outward.Act(agent_id=agent.id, kind="post", destination="x",
                       body=body, task_id="tsk_1")


def _http(answer):
    def call(*, url, token, payload, timeout):
        return 200, dict(answer, text=payload["text"])
    return call


# ── the platform's id is read ─────────────────────────────────────────

def test_every_platform_says_which_field_carries_its_id():
    for name, spec in transmit.PLATFORMS.items():
        assert "id_field" in spec, f"{name} names no id field"


def test_the_transmitter_keeps_the_handle_the_platform_returned(config, agent):
    vault.put(config, "x.token", "t0ken")
    send = transmit.post(config, agent, platform="x", secret="x.token",
                         prompt=lambda **kw: "yes", http=_http({"id": "110045"}))
    send(_act(agent), body="a short post")
    assert send.handle == "110045"


def test_a_platform_that_returns_no_id_leaves_no_handle(config, agent):
    """Absent is absent. A blank handle is what stops `undo` from guessing."""
    vault.put(config, "x.token", "t0ken")
    send = transmit.post(config, agent, platform="x", secret="x.token",
                         prompt=lambda **kw: "yes", http=_http({}))
    send(_act(agent), body="a short post")
    assert not send.handle


# ── it reaches the ledger ─────────────────────────────────────────────

def test_a_sent_post_records_its_handle(config, agent):
    def transmitter(act, *, body):
        transmitter.handle = "110045"
        return body

    outward.request(config, agent, _act(agent), transmit=transmitter,
                    approve=lambda **kw: "yes")
    entry = [e for e in ledger.read(config, "outward")
             if e.get("outcome") == "sent"][-1]
    assert entry["handle"] == "110045"


def test_a_stale_handle_is_never_attributed_to_the_next_post(config, agent):
    """The hazard: retracting the WRONG post is worse than the gap this closes."""
    def transmitter(act, *, body):
        return body                       # sets no handle at all

    transmitter.handle = "110045"         # left over from an earlier send
    outward.request(config, agent, _act(agent, "a different post"),
                    transmit=transmitter, approve=lambda **kw: "yes")
    entry = [e for e in ledger.read(config, "outward")
             if e.get("outcome") == "sent"][-1]
    assert not entry.get("handle")


def test_the_ledger_still_holds_no_body(config, agent):
    """A handle identifies. It does not reproduce."""
    def transmitter(act, *, body):
        transmitter.handle = "110045"
        return body

    outward.request(config, agent, _act(agent, "something private"),
                    transmit=transmitter, approve=lambda **kw: "yes")
    text = (config.ledger_dir / "outward.jsonl").read_text()
    assert "something private" not in text


# ── and undo can finally use it ───────────────────────────────────────

def test_a_post_with_a_recorded_handle_can_be_retracted(config, agent):
    def transmitter(act, *, body):
        transmitter.handle = "110045"
        return body

    outward.request(config, agent, _act(agent), transmit=transmitter,
                    approve=lambda **kw: "yes")
    pulled = []
    ud.retract(config, agent,
               retractor=lambda act: pulled.append(act.handle) or "deleted")
    assert pulled == ["110045"]


def test_a_post_recorded_without_one_still_refuses(config, agent):
    def transmitter(act, *, body):
        return body

    outward.request(config, agent, _act(agent), transmit=transmitter,
                    approve=lambda **kw: "yes")
    with pytest.raises(ud.Irreversible):
        ud.retract(config, agent, retractor=lambda act: "deleted")
