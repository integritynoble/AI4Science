"""Who is allowed to speak, and which agent hears it.

Every inbound turn passes through one decision. Two properties matter more than
anything else here: a message from anyone but the owner is **dropped and
counted, never answered**, and an unmatched account resolves to **nothing**
rather than to a default agent.
"""
import json

import pytest

from ai4science.harness.agents.sarsi import registry as reg, router


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def config(tmp_path):
    raw = reg.default_config(owner_id="7007143162")
    c = reg.parse(raw, root=tmp_path, path=tmp_path / "sarsi.json")
    (tmp_path / "sarsi.json").write_text(json.dumps(raw))
    c.ensure_dirs()
    return c


# ── the owner lock ────────────────────────────────────────────────────

def test_owner_reaches_the_bound_agent(config):
    d = router.decide(config, channel="telegram", account_id="work",
                      sender_id="7007143162")
    assert d.accepted is True and d.agent_id == "work"


def test_a_stranger_is_dropped_not_answered(config):
    d = router.decide(config, channel="telegram", account_id="work",
                      sender_id="99999")
    assert d.accepted is False
    assert d.reason == "not-owner"
    assert d.agent_id is None          # nothing downstream may act on it


def test_the_owner_check_is_exact_not_prefix(config):
    """`7007143162x` is a different account, not the owner with a typo."""
    d = router.decide(config, channel="telegram", account_id="work",
                      sender_id="7007143162x")
    assert d.accepted is False


def test_a_missing_sender_id_is_not_the_owner(config):
    d = router.decide(config, channel="telegram", account_id="work", sender_id=None)
    assert d.accepted is False and d.reason == "not-owner"


# ── the routing table ─────────────────────────────────────────────────

def test_each_bot_reaches_exactly_its_own_agent(config):
    for agent_id in ("sarsi-machine", "sarsi-worker", "work", "social",
                     "funding", "jobs", "abraham"):
        d = router.decide(config, channel="telegram", account_id=agent_id,
                          sender_id="7007143162")
        assert d.agent_id == agent_id


def test_an_unbound_account_is_dropped_never_defaulted(config):
    d = router.decide(config, channel="telegram", account_id="stranger-bot",
                      sender_id="7007143162")
    assert d.accepted is False and d.reason == "no-binding"
    assert d.agent_id is None


# ── the CLI surface ───────────────────────────────────────────────────

def test_the_cli_reaches_the_same_agent_without_a_telegram_id(config):
    """The CLI is trusted to the OS user who owns ~/.sarsi; it carries no
    telegram sender id, and must not be refused for lacking one."""
    d = router.decide(config, channel="cli", account_id="work", sender_id=None)
    assert d.accepted is True and d.agent_id == "work"


def test_cli_and_telegram_resolve_to_one_agent(config):
    a = router.decide(config, channel="cli", account_id="abraham", sender_id=None)
    b = router.decide(config, channel="telegram", account_id="abraham",
                      sender_id="7007143162")
    assert a.agent_id == b.agent_id == "abraham"


# ── what the decision carries ─────────────────────────────────────────

def test_an_accepted_decision_carries_the_agent_record(config):
    d = router.decide(config, channel="telegram", account_id="social",
                      sender_id="7007143162")
    assert d.agent is not None and d.agent.digest is True


def test_a_dropped_decision_carries_no_agent_record(config):
    d = router.decide(config, channel="telegram", account_id="social", sender_id="1")
    assert d.agent is None
