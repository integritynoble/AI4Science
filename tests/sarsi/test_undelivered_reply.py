"""An answer that did not arrive is not the same as an answer.

    ownerlog.reply(...)            # logged before the send, deliberately
    try:
        self.transport.send_message(token, chat_id, reply)
    except Exception:
        pass

Logging before the send is right, and the comment beside it says why: the record
is what the agent *answered*, not what the transport managed to deliver. What is
missing is the other half. The owner on Telegram sees nothing and cannot tell it
from an agent that had nothing to say; the owner reading `/history` sees the
reply and has no reason to think it never left the machine. The two most likely
readers both come away with a wrong picture, in opposite directions.

**Refusing is not available here.** The gateway is a poll loop serving every
agent — raising would take the whole door down because one message could not be
delivered, which is a worse failure than an undelivered message. So it is
recorded: the reply keeps its place in the log, and carries whether it landed.

Sending is not retried. A transport that just failed is not more likely to work
on an immediate second attempt, and a retry loop inside a poll loop is how one
unreachable chat stops every other agent being served.
"""
import pytest

from ai4science.harness.agents.sarsi import (gateway as gw, ledger,
                                             ownerlog, registry as reg)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def config(tmp_path):
    raw = reg.default_config(owner_id="7007143162")
    for entry in raw["agents"]["list"]:
        entry["botToken"] = "t"
    raw["channels"]["telegram"]["accounts"] = {
        a["id"]: {"botToken": "t"} for a in raw["agents"]["list"]}
    c = reg.parse(raw, root=tmp_path)
    c.ensure_dirs()
    return c


class Transport:
    def __init__(self, *, fails=False):
        self.fails = fails
        self.sent = []

    def get_updates(self, token, offset=None):
        return []

    def send_message(self, token, chat_id, text):
        if self.fails:
            raise OSError("telegram unreachable")
        self.sent.append((chat_id, text))
        return True


def _deliver(config, transport):
    g = gw.Gateway(config=config, transport=transport,
                   handler=lambda **kw: "here is your answer")
    # `from.id` is what the router checks — it is the OWNER check, and without
    # it every message is from a stranger and is dropped unanswered.
    update = {"message": {"chat": {"id": "7007143162"}, "text": "hello",
                          "from": {"id": 7007143162}}}
    return g._dispatch("sarsi-worker", "t", update)


# ── the reply keeps its place either way ──────────────────────────────

def test_a_delivered_reply_is_recorded(config):
    t = Transport()
    _deliver(config, t)
    said = ownerlog.transcript(config, config.agents["sarsi-worker"])
    assert any("here is your answer" in (r.get("text") or "") for r in said)
    assert t.sent


def test_an_undelivered_reply_is_still_recorded(config):
    """Unchanged, and the reason it was written that way stands: the record is
    what the agent answered."""
    _deliver(config, Transport(fails=True))
    said = ownerlog.transcript(config, config.agents["sarsi-worker"])
    assert any("here is your answer" in (r.get("text") or "") for r in said)


# ── but it says which ─────────────────────────────────────────────────

def test_a_delivered_reply_says_so(config):
    _deliver(config, Transport())
    entry = [r for r in ownerlog.transcript(config, config.agents["sarsi-worker"])
             if "here is your answer" in (r.get("text") or "")][-1]
    assert entry.get("delivered") is True


def test_an_undelivered_one_says_so_too(config):
    _deliver(config, Transport(fails=True))
    entry = [r for r in ownerlog.transcript(config, config.agents["sarsi-worker"])
             if "here is your answer" in (r.get("text") or "")][-1]
    assert entry.get("delivered") is False


def test_and_the_ledger_carries_the_reason(config):
    """`attention` and `why` read the ledger; the owner should be able to find
    out WHY it did not arrive, not only that it did not."""
    _deliver(config, Transport(fails=True))
    rows = [r for r in ledger.read(config, "outbound")
            if r.get("delivered") is False]
    assert rows, "nothing recorded the failure"
    assert "telegram unreachable" in (rows[-1].get("error") or "")
    assert rows[-1].get("agent") == "sarsi-worker"


def test_a_delivered_one_leaves_no_failure_behind(config):
    _deliver(config, Transport())
    assert [r for r in ledger.read(config, "outbound")
            if r.get("delivered") is False] == []


# ── and the door stays open ───────────────────────────────────────────

def test_one_unreachable_chat_does_not_stop_the_dispatch(config):
    """The reason refusing is not available: this is a poll loop serving every
    agent, and taking it down over one message is the worse failure."""
    assert _deliver(config, Transport(fails=True)) == 1


def test_it_is_not_retried(config):
    """A transport that just failed is not more likely to work immediately, and
    a retry loop inside a poll loop is how one unreachable chat starves the
    rest."""
    class Counting(Transport):
        def __init__(self):
            super().__init__(fails=True)
            self.tries = 0

        def send_message(self, token, chat_id, text):
            self.tries += 1
            raise OSError("telegram unreachable")

    t = Counting()
    _deliver(config, t)
    assert t.tries == 1
