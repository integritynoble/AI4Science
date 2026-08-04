"""House rules — the host facts every session would otherwise rediscover.

A live session ran `python demo.py`, hit `/bin/sh: 1: python: not found`, and
retried with `python3`. Cheap once, and paid again by every session that starts
here. *"Use python3 on this host"* is a fact about this machine, and it belongs
somewhere a session is told rather than somewhere it has to bump into.

Where matters as much as what. They live in **`W_host`**, the per-agent host
workspace, because the standing rule is that a host-local fact never travels: a
path that exists here means nothing on another machine, and copying one upward
is how a fleet convinces itself it can do something it cannot.

Three rules:

  * **the owner writes them.** An agent that can write its own standing
    instructions can widen its own instructions, which is the one thing the
    whole permission design exists to prevent.
  * **bounded.** A rules file that grows forever becomes a second prompt nobody
    reads, and an unread rule is worse than an absent one — it looks like
    coverage.
  * **no secret.** Same refusal as everywhere else: a rule may name a
    credential, never carry one.
"""
import pytest

from ai4science.harness.agents.sarsi import (plan as pl, registry as reg,
                                             rules, session as ses, task as tsk,
                                             worker)


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
    return config.agents["work"]


def _task(config, agent):
    d = worker.Directive(agent_id=agent.id, goal="run the demo")
    return tsk.attach_plan(config, agent, tsk.create(config, agent, d),
                           pl.draft(d))


# ── keeping them ──────────────────────────────────────────────────────

def test_an_agent_starts_with_none(config, agent):
    assert rules.read(config, agent) == []


def test_a_rule_can_be_added_and_read_back(config, agent):
    rules.add(config, agent, "use python3 on this host, never python")
    assert rules.read(config, agent) == ["use python3 on this host, never python"]


def test_they_keep_the_order_they_were_written_in(config, agent):
    rules.add(config, agent, "first")
    rules.add(config, agent, "second")
    assert rules.read(config, agent) == ["first", "second"]


def test_the_same_rule_twice_is_kept_once(config, agent):
    """A rules file that accumulates duplicates is a rules file nobody reads."""
    rules.add(config, agent, "use python3")
    rules.add(config, agent, "use python3")
    assert rules.read(config, agent) == ["use python3"]


def test_one_can_be_removed(config, agent):
    rules.add(config, agent, "use python3")
    rules.add(config, agent, "never touch prod")
    rules.remove(config, agent, "use python3")
    assert rules.read(config, agent) == ["never touch prod"]


def test_removing_one_that_is_not_there_says_so(config, agent):
    with pytest.raises(rules.NoSuchRule):
        rules.remove(config, agent, "a rule nobody wrote")


# ── they are host-local ───────────────────────────────────────────────

def test_they_live_in_the_agents_host_workspace(config, agent):
    """`W_host`, not `W_name`: a path that exists here means nothing on
    another machine."""
    rules.add(config, agent, "use python3")
    assert rules.path(agent).parent == agent.host


def test_one_agents_rules_are_not_another_agents(config, agent):
    rules.add(config, agent, "use python3")
    assert rules.read(config, config.agents["social"]) == []


# ── the refusals ──────────────────────────────────────────────────────

def test_an_empty_rule_is_refused(config, agent):
    with pytest.raises(ValueError):
        rules.add(config, agent, "   ")


def test_a_rule_carrying_a_secret_is_refused(config, agent):
    """It may NAME a credential; it may not carry one."""
    with pytest.raises(rules.LooksLikeASecret):
        rules.add(config, agent, "the smtp password is hunter2")


def test_naming_a_secret_is_still_allowed(config, agent):
    rules.add(config, agent, "mail needs the mail.smtp secret — ask for it")
    assert rules.read(config, agent)


def test_they_are_bounded(config, agent):
    """An unread rule is worse than an absent one: it looks like coverage."""
    for i in range(rules.MAX_RULES + 5):
        try:
            rules.add(config, agent, f"rule {i}")
        except rules.TooMany:
            break
    assert len(rules.read(config, agent)) == rules.MAX_RULES


def test_the_limit_says_what_to_do_about_it(config, agent):
    for i in range(rules.MAX_RULES):
        rules.add(config, agent, f"rule {i}")
    with pytest.raises(rules.TooMany, match="remove"):
        rules.add(config, agent, "one more")


# ── every session is told ─────────────────────────────────────────────

def test_the_kickoff_carries_them(config, agent):
    rules.add(config, agent, "use python3 on this host, never python")
    t = _task(config, agent)
    text = ses.kickoff(t, tsk.read_plan(config, agent, t), agent)
    assert "use python3 on this host, never python" in text


def test_a_kickoff_with_no_rules_says_nothing_about_them(config, agent):
    t = _task(config, agent)
    text = ses.kickoff(t, tsk.read_plan(config, agent, t), agent)
    assert "house rules" not in text.lower()


def test_they_are_marked_as_the_owners_word(config, agent):
    """So a session weighs them against its own guesses correctly."""
    rules.add(config, agent, "use python3")
    t = _task(config, agent)
    text = ses.kickoff(t, tsk.read_plan(config, agent, t), agent).lower()
    assert "this machine" in text or "host" in text
