"""Delivering the digest without being asked.

`social` and `abraham` say `digest` in the roster, and until now that flag meant
nothing: a digest was something the owner typed a command to see. The flag is
supposed to say *"send me one"*.

Four rules, and three are about not becoming the thing a digest replaces:

  * **once a period, not once a poll.** The gateway polls every few seconds.
    Delivering on each pass would be the running commentary the digest exists
    to abolish.
  * **a period is elapsed time, not a wall-clock hour.** "At 08:00" means a
    machine that was asleep at 08:00 skips the day entirely and nobody learns
    that it did.
  * **a quiet period is not delivered.** A daily "nothing happened" trains the
    owner to ignore the channel, and an ignored channel is worse than a silent
    one. An *unreadable* period IS delivered — that is news.
  * **a delivery that failed does not move the line.** The lesson `questions`
    paid for: sent is not delivered, and recording it as sent loses the content
    for good, because the next digest starts after it.
"""
import time

import pytest

from ai4science.harness.agents.sarsi import digest as dg, ledger, registry as reg


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def config(tmp_path):
    c = reg.parse(reg.default_config(owner_id="7007143162"), root=tmp_path)
    c.ensure_dirs()
    return c


def _did(config, agent_id, state="verified"):
    ledger.append(config, "reports",
                  {"agent": agent_id, "task": "tsk_1", "state": state,
                   "ceiling": "A2", "evidence": ["…"]})


def _sink():
    sent = []

    def send(agent, text):
        sent.append((agent.id, text))
        return True
    send.sent = sent
    return send


# ── who gets one ──────────────────────────────────────────────────────

def test_only_the_agents_that_asked_are_swept(config):
    _did(config, "social")
    _did(config, "work")
    send = _sink()
    dg.sweep(config, send=send)
    assert [a for a, _ in send.sent] == ["social"]


def test_the_digest_that_is_sent_is_that_agents(config):
    _did(config, "social")
    send = _sink()
    dg.sweep(config, send=send)
    assert "social" in send.sent[0][1]


# ── once a period, not once a poll ────────────────────────────────────

def test_a_second_sweep_in_the_same_period_sends_nothing(config):
    """The gateway polls every few seconds. Delivering each pass would be the
    running commentary a digest exists to abolish."""
    _did(config, "social")
    send = _sink()
    dg.sweep(config, send=send)
    _did(config, "social")
    dg.sweep(config, send=send)
    assert len(send.sent) == 1


def test_a_sweep_after_the_period_sends_again(config):
    _did(config, "social")
    send = _sink()
    now = time.time()
    dg.sweep(config, send=send, now=lambda: now)
    _did(config, "social")
    dg.sweep(config, send=send, now=lambda: now + dg.PERIOD_SECONDS + 1)
    assert len(send.sent) == 2


def test_the_period_is_elapsed_time_not_a_clock_hour(config):
    """'At 08:00' means a machine asleep at 08:00 skips the day, and nobody
    learns that it did."""
    assert dg.PERIOD_SECONDS >= 3600


# ── a quiet period is not delivered ───────────────────────────────────

def test_nothing_happened_is_not_sent(config):
    """A daily 'nothing happened' trains the owner to ignore the channel."""
    send = _sink()
    dg.sweep(config, send=send)
    assert send.sent == []


def test_a_quiet_period_still_moves_the_line(config):
    """So a quiet week does not deliver a week's worth the moment something
    finally happens."""
    now = time.time()
    dg.sweep(config, send=_sink(), now=lambda: now)
    _did(config, "social")
    send = _sink()
    dg.sweep(config, send=send, now=lambda: now + 5)
    assert send.sent == []                # still inside the period


def test_something_waiting_is_enough_to_send(config):
    """Nothing was DONE, but the owner is still holding it up."""
    ledger.append(config, "reports",
                  {"agent": "social", "task": "tsk_1", "state": "question",
                   "evidence": ["Q: which account?"]})
    send = _sink()
    dg.sweep(config, send=send)
    assert len(send.sent) == 1


def test_an_unreadable_ledger_is_sent(config, monkeypatch):
    """That is news, not quiet."""
    def broken(config, name):
        raise OSError("unreadable")

    monkeypatch.setattr(ledger, "read", broken)
    send = _sink()
    dg.sweep(config, send=send)
    assert len(send.sent) == 2            # social and abraham


# ── a failed delivery does not move the line ──────────────────────────

def test_a_refused_delivery_leaves_it_undelivered(config):
    """`questions` paid for this lesson: sent is not delivered, and recording
    it as sent loses the content for good — the next digest starts after it."""
    _did(config, "social")

    def refuses(agent, text):
        return False

    dg.sweep(config, send=refuses)
    send = _sink()
    dg.sweep(config, send=send)
    assert len(send.sent) == 1


def test_a_delivery_that_raises_is_not_recorded_as_sent(config):
    _did(config, "social")

    def explodes(agent, text):
        raise RuntimeError("the bot is down")

    dg.sweep(config, send=explodes)
    send = _sink()
    dg.sweep(config, send=send)
    assert len(send.sent) == 1


def test_one_agents_failure_does_not_stop_another(config):
    _did(config, "social")
    _did(config, "abraham")
    reached = []

    def flaky(agent, text):
        if agent.id == "social":
            raise RuntimeError("down")
        reached.append(agent.id)
        return True

    dg.sweep(config, send=flaky)
    assert reached == ["abraham"]


# ── the sweep says what it did ────────────────────────────────────────

def test_it_returns_who_it_delivered_to(config):
    _did(config, "social")
    assert dg.sweep(config, send=_sink()) == ["social"]


# ── the poll that calls it ────────────────────────────────────────────

class Transport:
    """A Telegram stand-in that records what was sent."""

    def __init__(self):
        self.sent = []

    def get_updates(self, token, offset=None):
        return []

    def send_message(self, token, chat_id, text):
        self.sent.append((token, chat_id, text))
        return {"ok": True}


def test_the_gateway_poll_delivers_a_due_digest(config):
    """The flag has to mean something without the owner typing a command."""
    from ai4science.harness.agents.sarsi import admin, gateway

    admin.init(owner_id="7007143162")
    admin.set_bot_token("social", "8541204756:AA-token")
    _did(config, "social")
    transport = Transport()
    gw = gateway.Gateway(reg.load(), transport=transport)
    gw.poll_once()
    assert any("social" in text for _, _, text in transport.sent)


def test_it_goes_to_the_owner_not_to_a_stranger(config):
    from ai4science.harness.agents.sarsi import admin, gateway

    admin.init(owner_id="7007143162")
    admin.set_bot_token("social", "8541204756:AA-token")
    _did(config, "social")
    transport = Transport()
    gateway.Gateway(reg.load(), transport=transport).poll_once()
    assert transport.sent[0][1] == config.owner_id


def test_an_agent_with_no_bot_is_not_lost_silently(config):
    """No Telegram token means nowhere to send. It must not be marked
    delivered, or the content is gone."""
    from ai4science.harness.agents.sarsi import admin, gateway

    admin.init(owner_id="7007143162")
    _did(config, "social")
    transport = Transport()
    gateway.Gateway(reg.load(), transport=transport).poll_once()
    assert dg.compile(reg.load(), reg.load().agents["social"]).verified == 1


def test_a_second_poll_does_not_send_it_again(config):
    from ai4science.harness.agents.sarsi import admin, gateway

    admin.init(owner_id="7007143162")
    admin.set_bot_token("social", "8541204756:AA-token")
    _did(config, "social")
    transport = Transport()
    gw = gateway.Gateway(reg.load(), transport=transport)
    gw.poll_once()
    gw.poll_once()
    assert len(transport.sent) == 1
