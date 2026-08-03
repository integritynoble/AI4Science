"""`OWN` — the only way out of the machine.

> **Drafting is not sending.** An agent may compose anything. Every act that
> leaves the machine and reaches a person requires an owner grant naming *that
> act*.

The rules with teeth:

  * the owner is shown **exactly** what would go out, and **the approved bytes
    are the transmitted bytes** — no silent reformatting between approval and
    publication;
  * a timeout, an error, or a shrug is a **denial**;
  * a refusal is an **outcome**, not an error;
  * one approval covers **one act** — it is never carried to a second;
  * the four reserved classes (money, consent, publishing, legal) cannot be
    authorised by any grant, so an agent that holds no standing authority
    **abstains** rather than asking — asking would imply a grant would help.
"""
import json

import pytest

from ai4science.harness.agents.sarsi import ledger, outward, registry as reg


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


def _act(**kw):
    base = dict(agent_id="work", task_id="tsk_1", kind="mail",
                destination="bob@example.com",
                body="Hi Bob — the export is done. Best, C.")
    base.update(kw)
    return outward.Act(**base)


def _approver(answers, record=None):
    def approve(*, act, shown, reversibility):
        (record if record is not None else []).append(shown)
        approve.shown.append(shown)
        approve.reversibility.append(reversibility)
        return answers.pop(0) if answers else None
    approve.shown, approve.reversibility = [], []
    return approve


def _transmitter(sent, *, alter=None):
    def transmit(act, *, body):
        actually = alter(body) if alter else body
        sent.append(actually)
        return actually            # what was ACTUALLY sent, for comparison
    return transmit


# ── drafting is not sending ───────────────────────────────────────────

def test_a_draft_is_recorded_and_never_transmitted(config, agent):
    sent = []
    outward.draft(config, agent, _act())
    assert sent == []
    assert ledger.count(config, "outward", outcome="drafted") == 1


def test_nothing_transmits_without_going_through_the_gate(config, agent):
    """There is no send() to call by mistake."""
    assert not hasattr(outward, "send")


# ── the owner sees exactly what would go out ──────────────────────────

def test_the_owner_is_shown_the_destination_and_the_whole_body(config, agent):
    approve = _approver(["yes"])
    outward.request(config, agent, _act(), approve=approve,
                    transmit=_transmitter([]))
    assert "bob@example.com" in approve.shown[0]
    assert "Hi Bob — the export is done. Best, C." in approve.shown[0]


def test_the_approved_bytes_are_the_transmitted_bytes(config, agent):
    sent = []
    out = outward.request(config, agent, _act(), approve=_approver(["yes"]),
                          transmit=_transmitter(sent))
    assert sent == ["Hi Bob — the export is done. Best, C."]
    assert out.transmitted is True


def test_a_transmitter_that_reformats_is_caught(config, agent):
    """No silent reformatting between approval and publication."""
    sent = []
    with pytest.raises(outward.NotWhatWasApproved):
        outward.request(config, agent, _act(), approve=_approver(["yes"]),
                        transmit=_transmitter(sent, alter=lambda b: b.replace("—", "-")))


def test_a_reformatting_transmitter_is_recorded_as_a_mismatch(config, agent):
    try:
        outward.request(config, agent, _act(), approve=_approver(["yes"]),
                        transmit=_transmitter([], alter=lambda b: b + " "))
    except outward.NotWhatWasApproved:
        pass
    assert ledger.count(config, "outward", outcome="mismatch") == 1


# ── refusal, timeout, error ───────────────────────────────────────────

def test_a_refusal_is_an_outcome_not_an_error(config, agent):
    out = outward.request(config, agent, _act(), approve=_approver(["no"]),
                          transmit=_transmitter([]))
    assert out.approved is False and out.transmitted is False
    assert ledger.count(config, "outward", outcome="refused") == 1


def test_no_answer_denies(config, agent):
    out = outward.request(config, agent, _act(), approve=_approver([None]),
                          transmit=_transmitter([]))
    assert out.approved is False


def test_an_approver_that_raises_denies(config, agent):
    def boom(**_):
        raise RuntimeError("telegram is down")

    out = outward.request(config, agent, _act(), approve=boom,
                          transmit=_transmitter([]))
    assert out.approved is False and "telegram is down" in out.reason


# ── one approval, one act ─────────────────────────────────────────────

def test_an_approval_is_not_carried_to_a_second_act(config, agent):
    sent = []
    approve = _approver(["yes"])          # one answer, two acts
    outward.request(config, agent, _act(), approve=approve, transmit=_transmitter(sent))
    second = outward.request(config, agent, _act(destination="carol@example.com"),
                             approve=approve, transmit=_transmitter(sent))
    assert second.approved is False
    assert len(sent) == 1


def test_unrelated_acts_cannot_be_batched_into_one_approval(config, agent):
    with pytest.raises(TypeError):
        outward.request(config, agent, [_act(), _act()], approve=_approver(["yes"]),
                        transmit=_transmitter([]))


# ── standing grants are bounded and spent ─────────────────────────────

def test_a_standing_grant_covers_the_act_without_asking(config):
    """For an act that is not the agent's own stopping point."""
    base = config.agents["sarsi-worker"]
    outward.grant(config, agent_id="sarsi-worker", kind="mail", uses=2)
    approve = _approver([])
    out = outward.request(config, base, _act(agent_id="sarsi-worker"),
                          approve=approve, transmit=_transmitter([]))
    assert out.approved is True and approve.shown == []


def test_each_use_spends_one(config):
    """A three-use grant really is three. Uses an agent whose act is not its own
    stopping point, so the grant is genuinely being spent."""
    base = config.agents["sarsi-worker"]
    outward.grant(config, agent_id="sarsi-worker", kind="mail", uses=2)
    for _ in range(2):
        outward.request(config, base, _act(agent_id="sarsi-worker"),
                        approve=_approver([]), transmit=_transmitter([]))
    approve = _approver([None])
    out = outward.request(config, base, _act(agent_id="sarsi-worker"),
                          approve=approve, transmit=_transmitter([]))
    assert out.approved is False and approve.shown != []      # asked again


def test_an_approval_never_creates_a_standing_grant(config, agent):
    for _ in range(5):
        outward.request(config, agent, _act(), approve=_approver(["yes"]),
                        transmit=_transmitter([]))
    assert outward.grants(config, "work") == []


# ── the reserved classes ──────────────────────────────────────────────

def test_an_agent_with_no_standing_authority_abstains_on_a_reserved_class(config):
    """abraham may prepare all four and complete none. Asking would imply a
    grant would help."""
    abraham = config.agents["abraham"]
    approve = _approver(["yes"])
    out = outward.request(config, abraham, _act(agent_id="abraham", kind="pay",
                                                destination="the shop"),
                          approve=approve, transmit=_transmitter([]))
    assert out.approved is False and out.abstained is True
    assert approve.shown == []                       # the owner was not asked
    assert "no grant" in out.reason


def test_money_cannot_be_granted_by_a_bare_use_count(config, agent):
    """A money grant needs the vault's grammar — limit, counterparty, rate — not
    "five payments, to anyone"."""
    with pytest.raises(outward.Reserved, match="vault"):
        outward.grant(config, agent_id="abraham", kind="pay", uses=5)


def test_consent_and_signing_are_never_granted_in_bulk(config, agent):
    """Agreeing on someone's behalf is not a class you pre-authorise."""
    for kind in ("consent", "sign"):
        with pytest.raises(outward.Reserved):
            outward.grant(config, agent_id="work", kind=kind, uses=5)


def test_publishing_may_be_granted_bounded(config, agent):
    """The guide's own example: "post to Substack", spent by use."""
    outward.grant(config, agent_id="social", kind="post", uses=5)
    assert outward.grants(config, "social")[0]["uses"] == 5


def test_a_bounded_publishing_grant_really_runs_out(config, config_social=None):
    social = config.agents["social"]
    outward.grant(config, agent_id="social", kind="post", uses=1)
    first = outward.request(config, social,
                            _act(agent_id="social", kind="post",
                                 destination="substack"),
                            approve=_approver([]), transmit=_transmitter([]))
    approve = _approver([None])
    second = outward.request(config, social,
                             _act(agent_id="social", kind="post",
                                  destination="substack"),
                             approve=approve, transmit=_transmitter([]))
    assert first.approved is True
    assert second.approved is False and approve.shown != []


def test_an_ordinary_class_still_asks(config, agent):
    approve = _approver(["yes"])
    outward.request(config, agent, _act(), approve=approve, transmit=_transmitter([]))
    assert approve.shown != []


# ── the agent's own rules reach the gate ──────────────────────────────

def test_work_is_asked_every_time_even_with_a_standing_grant(config, agent):
    """Sending is `work`'s act that stops at the owner — *every* time. A
    standing grant may not turn "never sends by itself" into "sends by
    default"."""
    outward.grant(config, agent_id="work", kind="mail", uses=5)
    approve = _approver(["yes"])
    out = outward.request(config, agent, _act(), approve=approve,
                          transmit=_transmitter([]))
    assert approve.shown != []                 # asked, not waved through
    assert out.approved is True                # and still possible, with a yes


def test_a_refused_send_stays_refused_despite_the_grant(config, agent):
    outward.grant(config, agent_id="work", kind="mail", uses=5)
    out = outward.request(config, agent, _act(), approve=_approver(["no"]),
                          transmit=_transmitter([]))
    assert out.approved is False


def test_a_grant_still_works_for_an_act_the_agent_may_do(config):
    social = config.agents["social"]
    outward.grant(config, agent_id="social", kind="post", uses=1)
    out = outward.request(config, social,
                          _act(agent_id="social", kind="post", destination="substack"),
                          approve=_approver([]), transmit=_transmitter([]))
    assert out.approved is True


# ── what undoing costs ────────────────────────────────────────────────

def test_the_approval_shows_what_undoing_costs(config, agent):
    approve = _approver(["yes"])
    outward.request(config, agent,
                    _act(reversibility={"cost": "£180", "until": "Tue 09:00"}),
                    approve=approve, transmit=_transmitter([]))
    assert "£180" in approve.reversibility[0] and "Tue 09:00" in approve.reversibility[0]


def test_unknown_reversibility_reads_as_unknown_never_as_free(config, agent):
    approve = _approver(["yes"])
    outward.request(config, agent, _act(), approve=approve, transmit=_transmitter([]))
    assert "unknown" in approve.reversibility[0].lower()
    assert "free" not in approve.reversibility[0].lower()


# ── the record ────────────────────────────────────────────────────────

def test_every_act_that_asked_to_leave_is_recorded(config, agent):
    outward.request(config, agent, _act(), approve=_approver(["yes"]),
                    transmit=_transmitter([]))
    outward.request(config, agent, _act(), approve=_approver(["no"]),
                    transmit=_transmitter([]))
    assert ledger.count(config, "outward") == 2


def test_the_record_holds_a_digest_rather_than_the_whole_body(config, agent):
    """An outward body can hold anything the agent drafted, including things the
    owner would not want copied into a second file."""
    outward.request(config, agent, _act(body="the salary expectation is £X"),
                    approve=_approver(["yes"]), transmit=_transmitter([]))
    text = json.dumps(ledger.read(config, "outward"))
    assert "the salary expectation is £X" not in text
    assert "digest" in text
