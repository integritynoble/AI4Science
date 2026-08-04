"""`digest` — one read across everything an agent did, instead of many.

`social` and `abraham` are marked `digest` in the roster: the owner wants one
daily read, not a running commentary. Nothing compiled one, so the choice
existed in the registry and nowhere else.

The thing a digest must not become is a second inbox. It reports **what
happened**; what is still *waiting* on the owner belongs to `attention`, and
duplicating it here would give the same obligation two homes and let each look
like the other's copy. So the digest points at what is waiting and does not
restate it.

Three rules beyond that:

  * **the span is stated, not implied.** "Today" read at 2am covers a different
    stretch than the same word at 6pm. It says *since when*.
  * **nothing to report and nothing readable are different answers.** A quiet
    day and an unreadable ledger both produce a short digest, and only one of
    them means the agent was quiet.
  * **delivering moves the line; reading does not.** Otherwise the first person
    to glance at it consumes it for everyone.
"""
import pytest

from ai4science.harness.agents.sarsi import (digest as dg, ledger,
                                             registry as reg)


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


def _report(config, agent, state, *, task="tsk_1", evidence="…"):
    ledger.append(config, "reports",
                  {"agent": agent.id, "task": task, "state": state,
                   "ceiling": "A2", "evidence": [evidence]})


def _outward(config, agent, kind="post", outcome="sent"):
    ledger.append(config, "outward",
                  {"agent": agent.id, "task": "tsk_1", "kind": kind,
                   "destination": "x", "digest": "d1", "chars": 40,
                   "outcome": outcome})


# ── what it reports ───────────────────────────────────────────────────

def test_it_counts_what_was_verified(config, agent):
    _report(config, agent, "verified", evidence="the thread reads correctly")
    got = dg.compile(config, agent)
    assert got.verified == 1


def test_it_counts_what_the_agent_decided_alone(config, agent):
    _report(config, agent, "answered")
    _report(config, agent, "submitted")
    assert dg.compile(config, agent).decided == 2


def test_it_counts_what_left_the_machine(config, agent):
    _outward(config, agent)
    assert dg.compile(config, agent).outward == 1


def test_a_refused_outward_act_did_not_leave(config, agent):
    _outward(config, agent, outcome="refused")
    assert dg.compile(config, agent).outward == 0


def test_it_names_the_agent(config, agent):
    assert dg.compile(config, agent).agent_id == "social"


def test_another_agents_work_is_not_in_this_digest(config, agent):
    _report(config, config.agents["work"], "verified")
    assert dg.compile(config, agent).verified == 0


# ── it points at what waits, and does not restate it ──────────────────

def test_it_says_how_many_things_wait_on_the_owner(config, agent):
    _report(config, agent, "question",
            evidence="Q: which account should I post from?")
    got = dg.compile(config, agent)
    assert got.waiting == 1


def test_it_does_not_restate_them(config, agent):
    """Two homes for one obligation, each looking like the other's copy."""
    _report(config, agent, "question",
            evidence="Q: which account should I post from?")
    assert "which account should I post from?" not in dg.compile(config, agent).text


def test_it_points_at_where_they_are(config, agent):
    _report(config, agent, "question", evidence="Q: which account?")
    assert "attention" in dg.compile(config, agent).text


# ── the span ──────────────────────────────────────────────────────────

def test_the_span_is_stated(config, agent):
    """'Today' read at 2am covers a different stretch than at 6pm."""
    _report(config, agent, "verified")
    assert "since" in dg.compile(config, agent).text.lower()


def test_only_what_happened_since_the_last_delivery_is_counted(config, agent):
    _report(config, agent, "verified")
    dg.deliver(config, agent)
    assert dg.compile(config, agent).verified == 0
    _report(config, agent, "verified")
    assert dg.compile(config, agent).verified == 1


def test_reading_does_not_move_the_line(config, agent):
    """Otherwise the first person to glance at it consumes it for everyone."""
    _report(config, agent, "verified")
    assert dg.compile(config, agent).verified == 1
    assert dg.compile(config, agent).verified == 1


# ── quiet is not unreadable ───────────────────────────────────────────

def test_a_quiet_period_says_nothing_happened(config, agent):
    got = dg.compile(config, agent)
    assert got.readable is True
    assert "nothing" in got.text.lower()


def test_an_unreadable_ledger_says_so_instead(config, agent, monkeypatch):
    """A quiet day and an unreadable ledger both produce a short digest, and
    only one of them means the agent was quiet."""
    def broken(config, name):
        raise OSError("the ledger could not be read")

    monkeypatch.setattr(ledger, "read", broken)
    got = dg.compile(config, agent)
    assert got.readable is False
    assert "could not" in got.text.lower()


# ── who gets one ──────────────────────────────────────────────────────

def test_the_roster_says_which_agents_want_one(config):
    assert config.agents["social"].digest is True
    assert config.agents["work"].digest is False


def test_one_can_still_be_compiled_for_an_agent_that_did_not_ask(config):
    """The flag says who gets it UNPROMPTED. Asking is always allowed."""
    _report(config, config.agents["work"], "verified")
    assert dg.compile(config, config.agents["work"]).verified == 1


def test_the_fleet_digest_covers_every_worker(config):
    _report(config, config.agents["work"], "verified")
    _report(config, config.agents["social"], "answered")
    rows = dg.across(config)
    assert {r.agent_id for r in rows} >= {"work", "social"}


def test_only_the_agents_that_asked_are_due(config):
    assert {a.id for a in dg.due(config)} == {"social", "abraham"}


def test_something_recorded_in_the_same_second_as_delivery_is_not_lost(
        config, agent):
    """The ledger stamps to the second. A timestamped line would swallow
    anything recorded in that same second — `decisions` learned this the hard
    way, and repeating it here would lose a whole second of every digest."""
    _report(config, agent, "verified")
    dg.deliver(config, agent)
    _report(config, agent, "verified")          # same second, in practice
    assert dg.compile(config, agent).verified == 1
