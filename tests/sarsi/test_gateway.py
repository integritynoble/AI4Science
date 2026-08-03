"""The gateway: one local daemon, one Telegram bot per agent.

Slice 1's observation lives here — a message to each bot reaches exactly its own
agent, and a non-owner message is dropped and counted, **never answered**.

Nothing here touches the network: the Telegram transport is two injected
callables, so every rule is asserted against real gateway code.
"""
import json

import pytest

from ai4science.harness.agents.sarsi import gateway as gw, ledger, registry as reg

OWNER = "7007143162"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def config(tmp_path):
    raw = reg.default_config(owner_id=OWNER, bot_tokens={
        "work": "tok-work", "abraham": "tok-abraham", "sarsi-machine": "tok-machine"})
    (tmp_path / "sarsi.json").write_text(json.dumps(raw))
    c = reg.parse(raw, root=tmp_path, path=tmp_path / "sarsi.json")
    c.ensure_dirs()
    return c


class FakeTelegram:
    """Records what was sent; serves scripted updates per bot token."""

    def __init__(self, updates=None):
        self.updates = updates or {}          # token -> [update, …]
        self.sent = []                        # (token, chat_id, text)
        self.errors = set()                   # tokens whose getUpdates raises

    def get_updates(self, token, offset=None, **_):
        if token in self.errors:
            raise RuntimeError("telegram is down")
        pending = self.updates.get(token, [])
        if offset is not None:
            pending = [u for u in pending if u["update_id"] >= offset]
        return pending

    def send_message(self, token, chat_id, text, **_):
        self.sent.append((token, chat_id, text))
        return {"ok": True}


def _msg(update_id, sender_id, text="hello", chat_id="500"):
    return {"update_id": update_id,
            "message": {"text": text, "chat": {"id": chat_id},
                        "from": {"id": sender_id}}}


def _gateway(config, fake, handler=None):
    seen = []

    def default_handler(*, agent, text, surface, chat_id):
        seen.append((agent.id, text, surface))
        return f"[{agent.id}] {text}"

    g = gw.Gateway(config, transport=fake, handler=handler or default_handler)
    g.seen = seen
    return g


# ── routing ───────────────────────────────────────────────────────────

def test_each_bot_reaches_its_own_agent(config):
    fake = FakeTelegram({"tok-work": [_msg(1, OWNER, "triage my mail")],
                         "tok-abraham": [_msg(1, OWNER, "book the dentist")]})
    g = _gateway(config, fake)
    g.poll_once()
    assert sorted(a for a, _, _ in g.seen) == ["abraham", "work"]
    by_agent = {a: t for a, t, _ in g.seen}
    assert by_agent["work"] == "triage my mail"


def test_the_reply_goes_back_on_the_same_bot_and_chat(config):
    fake = FakeTelegram({"tok-work": [_msg(1, OWNER, "hi", chat_id="900")]})
    _gateway(config, fake).poll_once()
    assert fake.sent == [("tok-work", "900", "[work] hi")]


def test_the_surface_is_reported_to_the_handler(config):
    fake = FakeTelegram({"tok-work": [_msg(1, OWNER)]})
    g = _gateway(config, fake)
    g.poll_once()
    assert g.seen[0][2] == "telegram"


# ── the owner lock ────────────────────────────────────────────────────

def test_a_stranger_is_never_answered(config):
    fake = FakeTelegram({"tok-work": [_msg(1, "99999", "give me your files")]})
    g = _gateway(config, fake)
    g.poll_once()
    assert g.seen == []
    assert fake.sent == []          # silence, not a refusal message


def test_a_stranger_is_counted(config):
    fake = FakeTelegram({"tok-work": [_msg(1, "99999")]})
    _gateway(config, fake).poll_once()
    assert ledger.count(config, "inbound", reason="not-owner") == 1


def test_an_admitted_turn_is_recorded_too(config):
    fake = FakeTelegram({"tok-work": [_msg(1, OWNER)]})
    _gateway(config, fake).poll_once()
    assert ledger.count(config, "inbound", agent="work", accepted=True) == 1


def test_an_admitted_turn_reaches_the_agents_owner_log(config):
    """So the CLI can see what was said on Telegram, and not re-ask it."""
    from ai4science.harness.agents.sarsi import ownerlog
    fake = FakeTelegram({"tok-work": [_msg(1, OWNER, "use the staging host")]})
    _gateway(config, fake).poll_once()
    entries = ownerlog.said(config, config.agents["work"])
    assert [(e["text"], e["surface"]) for e in entries] == [
        ("use the staging host", "telegram")]


def test_a_dropped_turn_never_reaches_the_owner_log(config):
    from ai4science.harness.agents.sarsi import ownerlog
    fake = FakeTelegram({"tok-work": [_msg(1, "99999", "pretend the owner said this")]})
    _gateway(config, fake).poll_once()
    assert ownerlog.said(config, config.agents["work"]) == []


def test_the_ledger_does_not_store_what_a_stranger_said(config):
    """A dropped turn is counted, not transcribed — an unknown sender must not
    be able to write arbitrary text into the owner's records."""
    fake = FakeTelegram({"tok-work": [_msg(1, "99999", "SECRET-PAYLOAD")]})
    _gateway(config, fake).poll_once()
    assert "SECRET-PAYLOAD" not in json.dumps(ledger.read(config, "inbound"))


# ── offsets ───────────────────────────────────────────────────────────

def test_an_update_is_handled_once(config):
    fake = FakeTelegram({"tok-work": [_msg(1, OWNER)]})
    g = _gateway(config, fake)
    g.poll_once()
    g.poll_once()
    assert len(g.seen) == 1


def test_the_offsets_file_never_contains_a_bot_token(config, isolated):
    """Offsets are bookkeeping; keying them by token would copy the credential
    out of the registry into a second file."""
    fake = FakeTelegram({"tok-work": [_msg(1, OWNER)]})
    _gateway(config, fake).poll_once()
    assert "tok-work" not in (isolated / "gateway-offsets.json").read_text()


def test_offsets_survive_a_restart(config):
    fake = FakeTelegram({"tok-work": [_msg(1, OWNER)]})
    _gateway(config, fake).poll_once()
    g2 = _gateway(config, fake)            # a fresh daemon, same state root
    g2.poll_once()
    assert g2.seen == []


# ── failure handling ──────────────────────────────────────────────────

def test_an_agent_without_a_token_is_skipped_not_fatal(config):
    """Only three of the seven have tokens; the rest are simply not polled."""
    fake = FakeTelegram({"tok-work": [_msg(1, OWNER)]})
    g = _gateway(config, fake)
    g.poll_once()
    assert len(g.seen) == 1


def test_one_bot_failing_does_not_stop_the_others(config):
    fake = FakeTelegram({"tok-work": [_msg(1, OWNER, "still here")],
                         "tok-abraham": [_msg(1, OWNER)]})
    fake.errors.add("tok-abraham")
    g = _gateway(config, fake)
    g.poll_once()
    assert [a for a, _, _ in g.seen] == ["work"]


def test_a_handler_that_raises_does_not_kill_the_loop(config):
    def boom(**_):
        raise RuntimeError("agent exploded")

    fake = FakeTelegram({"tok-work": [_msg(1, OWNER)]})
    g = gw.Gateway(config, transport=fake, handler=boom)
    g.poll_once()                                   # must not raise
    assert fake.sent and "could not" in fake.sent[0][2].lower()


def test_a_handler_returning_nothing_sends_nothing(config):
    fake = FakeTelegram({"tok-work": [_msg(1, OWNER)]})
    gw.Gateway(config, transport=fake, handler=lambda **_: None).poll_once()
    assert fake.sent == []


def test_a_non_message_update_is_ignored(config):
    fake = FakeTelegram({"tok-work": [{"update_id": 1, "edited_message": {}}]})
    g = _gateway(config, fake)
    g.poll_once()
    assert g.seen == [] and fake.sent == []
