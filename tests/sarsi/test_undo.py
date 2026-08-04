"""`undo` — retracting the last outward act, and being straight about when it
cannot be done.

*"You approve a send, then regret it within a minute."* The outward ledger holds
enough to identify what left, so this can at least **try**. What it must never
do is imply that trying worked, or that everything is retractable.

Most outward acts are not:

  * **mail is gone.** SMTP handed it on; there is no recall. The only real
    remedy is a correction — which is a NEW outward act, needing its own
    approval, and calling that "undo" would be a lie about what happened.
  * **a submitted form cannot be withdrawn**, and `submit` already says so at
    the moment of asking.
  * **a post may be deletable**, if the platform offers it and a handle was
    kept. That is the one case where retraction is real.

Two more rules fall out of the ledger's own design: it stores a **digest and a
character count, never the body**, so `undo` can say what left and to whom and
cannot reproduce it — and a retraction is itself an act that leaves the machine,
so it goes through the same owner gate as the thing it retracts.
"""
import pytest

from ai4science.harness.agents.sarsi import (ledger, registry as reg,
                                             undo as ud)


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


def _sent(config, agent, kind="mail", destination="them@example.com",
          outcome="sent", handle=None):
    record = {"agent": agent.id, "task": "tsk_1", "kind": kind,
              "destination": destination, "digest": "abc123", "chars": 120,
              "outcome": outcome}
    if handle:
        record["handle"] = handle
    ledger.append(config, "outward", record)


# ── what left ─────────────────────────────────────────────────────────

def test_the_last_outward_act_is_named(config, agent):
    _sent(config, agent, kind="mail", destination="them@example.com")
    act = ud.last(config, agent)
    assert act.kind == "mail" and act.destination == "them@example.com"


def test_the_most_recent_one_wins(config, agent):
    _sent(config, agent, destination="first@example.com")
    _sent(config, agent, destination="second@example.com")
    assert ud.last(config, agent).destination == "second@example.com"


def test_something_that_never_left_is_not_the_last_act(config, agent):
    """A refused or drafted act did not leave the machine, so there is nothing
    to retract."""
    _sent(config, agent, outcome="refused")
    assert ud.last(config, agent) is None


def test_another_agents_act_is_not_this_ones(config, agent):
    _sent(config, config.agents["social"], kind="post")
    assert ud.last(config, agent) is None


def test_the_body_is_not_available_because_it_was_never_stored(config, agent):
    """The ledger keeps a digest and a character count on purpose. `undo` can
    say what left and to whom; it cannot show you what it said."""
    _sent(config, agent)
    act = ud.last(config, agent)
    assert not hasattr(act, "body")
    assert act.digest == "abc123" and act.chars == 120


# ── what cannot be retracted ──────────────────────────────────────────

def test_mail_cannot_be_retracted(config, agent):
    _sent(config, agent, kind="mail")
    with pytest.raises(ud.Irreversible) as e:
        ud.retract(config, agent)
    assert "recall" in str(e.value).lower() or "gone" in str(e.value).lower()


def test_the_mail_refusal_names_the_real_remedy(config, agent):
    """A correction is a NEW outward act with its own approval. Calling it undo
    would misdescribe what happened."""
    _sent(config, agent, kind="mail")
    try:
        ud.retract(config, agent)
    except ud.Irreversible as e:
        assert "sarsi send" in str(e) or "correction" in str(e).lower()


def test_a_submitted_form_cannot_be_withdrawn(config, agent):
    _sent(config, agent, kind="form")
    with pytest.raises(ud.Irreversible):
        ud.retract(config, agent)


def test_nothing_to_undo_says_so(config, agent):
    with pytest.raises(ud.NothingToUndo):
        ud.retract(config, agent)


# ── what can ──────────────────────────────────────────────────────────

def test_a_post_with_a_handle_can_be_retracted(config, agent):
    _sent(config, agent, kind="post", destination="mastodon", handle="110045")
    pulled = []
    ud.retract(config, agent,
               retractor=lambda act: pulled.append(act.handle) or "deleted")
    assert pulled == ["110045"]


def test_a_post_without_a_handle_cannot(config, agent):
    """Nothing identifies which post to delete, and deleting the wrong one is
    worse than deleting none."""
    _sent(config, agent, kind="post", destination="mastodon")
    with pytest.raises(ud.Irreversible) as e:
        ud.retract(config, agent, retractor=lambda act: "deleted")
    assert "handle" in str(e.value).lower() or "which" in str(e.value).lower()


def test_a_platform_with_no_retractor_is_refused_rather_than_pretended(config, agent):
    _sent(config, agent, kind="post", destination="mastodon", handle="110045")
    with pytest.raises(ud.Irreversible):
        ud.retract(config, agent)             # no retractor supplied


def test_a_successful_retraction_is_recorded_as_its_own_outward_act(config, agent):
    """It left the machine too. A retraction that is invisible in the ledger is
    an outward act nobody can audit."""
    _sent(config, agent, kind="post", destination="mastodon", handle="110045")
    ud.retract(config, agent, retractor=lambda act: "deleted")
    kinds = [e.get("kind") for e in ledger.read(config, "outward")]
    assert "retract" in kinds


def test_a_failed_retraction_is_not_recorded_as_success(config, agent):
    """Never 'undone' for something that was merely attempted."""
    def broken(act):
        raise RuntimeError("the platform said 404")

    _sent(config, agent, kind="post", destination="mastodon", handle="110045")
    with pytest.raises(ud.Failed):
        ud.retract(config, agent, retractor=broken)
    outcomes = [e.get("outcome") for e in ledger.read(config, "outward")]
    assert "retracted" not in outcomes


def test_the_same_act_is_not_retracted_twice(config, agent):
    _sent(config, agent, kind="post", destination="mastodon", handle="110045")
    ud.retract(config, agent, retractor=lambda act: "deleted")
    with pytest.raises(ud.NothingToUndo):
        ud.retract(config, agent, retractor=lambda act: "deleted")


def test_a_failed_attempt_does_not_hide_the_still_published_act(config, agent):
    """Otherwise the one command that could take it down stops offering to,
    and the failure reads as handled."""
    def broken(act):
        raise RuntimeError("the platform said 500")

    _sent(config, agent, kind="post", destination="mastodon", handle="110045")
    with pytest.raises(ud.Failed):
        ud.retract(config, agent, retractor=broken)
    assert ud.last(config, agent) is not None
    assert ud.last(config, agent).handle == "110045"
