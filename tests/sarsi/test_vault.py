"""`VLT` — the vault: policy first, then ask.

Two stages. A standing policy the owner wrote once answers alone when it
matches; otherwise the owner is asked, for this one use, naming the secret and
the purpose.

The rules that make it worth having:

  * **a per-use approval never becomes a standing one.** An agent that earned a
    standing grant by being approved five times has granted itself authority by
    persistence.
  * **the policy grammar cannot express "abraham may use the card."** For a
    money act, limit, counterparty and rate are required fields and there is no
    wildcard counterparty — a policy that permits the broad form has failed
    before it is written.
  * **a denial names the secret**, so the owner can grant it if they meant to.
  * **no secret reaches a ledger.** The record says which secret was asked for
    and what was decided, never what it is.
"""
import json

import pytest

from ai4science.harness.agents.sarsi import ledger, registry as reg, vault


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def config(tmp_path):
    c = reg.parse(reg.default_config(owner_id="7007143162"), root=tmp_path)
    c.ensure_dirs()
    vault.put(c, "mail.read", "hunter2")
    vault.put(c, "card.personal", "4111-1111-1111-1111")
    return c


def _asked(answers):
    """A stand-in owner. Records what it was shown; answers in order."""
    def prompt(*, secret, purpose, agent, act):
        prompt.shown.append({"secret": secret, "purpose": purpose,
                             "agent": agent, "act": act})
        return answers.pop(0) if answers else None
    prompt.shown = []
    return prompt


# ── stage 1: a standing policy answers alone ──────────────────────────

def test_a_matching_allow_policy_answers_without_asking(config):
    vault.write_policy(config, agent_id="work", secret="mail.read", act="read",
                       decision="ALLOW")
    ask = _asked([])
    out = vault.ask(config, agent_id="work", secret="mail.read", act="read",
                    purpose="triage the inbox", prompt=ask)
    assert out.allowed is True and out.stage == 1
    assert ask.shown == []                      # the owner was not interrupted


def test_a_matching_deny_policy_answers_without_asking(config):
    vault.write_policy(config, agent_id="work", secret="mail.read", act="send",
                       decision="DENY")
    ask = _asked(["yes"])
    out = vault.ask(config, agent_id="work", secret="mail.read", act="send",
                    purpose="reply to Bob", prompt=ask)
    assert out.allowed is False and out.stage == 1
    assert ask.shown == []                      # a deny rule is not re-litigated


def test_a_policy_for_another_agent_does_not_answer_for_this_one(config):
    vault.write_policy(config, agent_id="work", secret="mail.read", act="read",
                       decision="ALLOW")
    out = vault.ask(config, agent_id="abraham", secret="mail.read", act="read",
                    purpose="x", prompt=_asked([None]))
    assert out.allowed is False and out.stage == 2


# ── stage 2: the owner is asked, for this one use ─────────────────────

def test_with_no_rule_the_owner_is_asked_and_told_what_for(config):
    ask = _asked(["yes"])
    out = vault.ask(config, agent_id="work", secret="mail.read", act="read",
                    purpose="triage the inbox", prompt=ask)
    assert out.allowed is True and out.stage == 2
    assert ask.shown[0]["secret"] == "mail.read"
    assert ask.shown[0]["purpose"] == "triage the inbox"


def test_an_outward_act_is_asked_even_when_a_rule_allows_it(config):
    """Stage 1 may allow the read; leaving the machine still stops at the owner."""
    vault.write_policy(config, agent_id="social", secret="mail.read", act="post",
                       decision="ALLOW")
    ask = _asked(["yes"])
    out = vault.ask(config, agent_id="social", secret="mail.read", act="post",
                    purpose="publish the draft", prompt=ask, outward=True)
    assert out.stage == 2 and ask.shown != []


def test_no_answer_denies(config):
    """Fail-safe: a timeout or a shrug is a denial."""
    out = vault.ask(config, agent_id="work", secret="mail.read", act="read",
                    purpose="x", prompt=_asked([None]))
    assert out.allowed is False


def test_a_denial_names_the_secret(config):
    out = vault.ask(config, agent_id="work", secret="mail.read", act="read",
                    purpose="x", prompt=_asked(["no"]))
    assert "mail.read" in out.reason


def test_a_secret_that_does_not_exist_denies_and_names_it(config):
    out = vault.ask(config, agent_id="work", secret="bank.login", act="read",
                    purpose="x", prompt=_asked(["yes"]))
    assert out.allowed is False and "bank.login" in out.reason


# ── the secret itself ─────────────────────────────────────────────────

def test_an_allow_hands_over_the_value(config):
    out = vault.ask(config, agent_id="work", secret="mail.read", act="read",
                    purpose="x", prompt=_asked(["yes"]))
    assert out.value == "hunter2"


def test_a_denial_hands_over_nothing(config):
    out = vault.ask(config, agent_id="work", secret="mail.read", act="read",
                    purpose="x", prompt=_asked(["no"]))
    assert out.value is None


def test_the_decision_is_recorded_but_the_secret_is_not(config):
    vault.ask(config, agent_id="work", secret="mail.read", act="read",
              purpose="x", prompt=_asked(["yes"]))
    text = json.dumps(ledger.read(config, "vault"))
    assert "mail.read" in text                  # which secret: yes
    assert "hunter2" not in text                # what it is: never


def test_no_api_lists_secret_values(config):
    """The only interface is the question."""
    assert not hasattr(vault, "read_secret")
    assert vault.names(config) == ["card.personal", "mail.read"]


# ── promotion is an owner act, never an inference ─────────────────────

def test_five_approvals_do_not_create_a_standing_grant(config):
    ask = _asked(["yes"] * 5)
    for _ in range(5):
        vault.ask(config, agent_id="work", secret="mail.read", act="read",
                  purpose="x", prompt=ask)
    assert vault.policies(config) == []
    sixth = vault.ask(config, agent_id="work", secret="mail.read", act="read",
                      purpose="x", prompt=_asked([None]))
    assert sixth.allowed is False               # still asked, still refusable


def test_the_owner_may_promote_explicitly(config):
    vault.write_policy(config, agent_id="work", secret="mail.read", act="read",
                       decision="ALLOW")
    out = vault.ask(config, agent_id="work", secret="mail.read", act="read",
                    purpose="x", prompt=_asked([]))
    assert out.stage == 1


# ── the grammar that refuses the broad form ───────────────────────────

def test_a_money_policy_without_a_counterparty_is_refused(config):
    with pytest.raises(vault.PolicyRefused, match="counterparty"):
        vault.write_policy(config, agent_id="abraham", secret="card.personal",
                           act="pay", decision="ALLOW",
                           limit={"amount": 40, "currency": "GBP"},
                           rate={"uses": 2, "per": "week"})


def test_a_money_policy_without_a_limit_is_refused(config):
    with pytest.raises(vault.PolicyRefused, match="limit"):
        vault.write_policy(config, agent_id="abraham", secret="card.personal",
                           act="pay", decision="ALLOW",
                           counterparty={"class": "grocery"},
                           rate={"uses": 2, "per": "week"})


def test_a_money_policy_without_a_rate_is_refused(config):
    with pytest.raises(vault.PolicyRefused, match="rate"):
        vault.write_policy(config, agent_id="abraham", secret="card.personal",
                           act="pay", decision="ALLOW",
                           counterparty={"class": "grocery"},
                           limit={"amount": 40, "currency": "GBP"})


def test_a_wildcard_counterparty_is_refused(config):
    """`abraham may use the card` must not be expressible."""
    for wildcard in ("*", "any", "ANY", ""):
        with pytest.raises(vault.PolicyRefused):
            vault.write_policy(config, agent_id="abraham", secret="card.personal",
                               act="pay", decision="ALLOW",
                               counterparty={"class": wildcard},
                               limit={"amount": 40, "currency": "GBP"},
                               rate={"uses": 2, "per": "week"})


def test_the_narrow_money_policy_is_accepted(config):
    vault.write_policy(config, agent_id="abraham", secret="card.personal",
                       act="pay", decision="ALLOW",
                       counterparty={"class": "grocery"},
                       limit={"amount": 40, "currency": "GBP"},
                       rate={"uses": 2, "per": "week"})
    assert len(vault.policies(config)) == 1


def test_a_deny_policy_needs_no_grammar(config):
    """Refusing is always expressible; only permitting is constrained."""
    vault.write_policy(config, agent_id="abraham", secret="card.personal",
                       act="pay", decision="DENY")
    assert vault.policies(config)[0]["decision"] == "DENY"


# ── abraham has no standing grants at all ─────────────────────────────

def test_an_agent_with_standing_grants_off_is_always_asked(config):
    """Rule B, at its strongest: abraham's authority starts at nothing."""
    vault.write_policy(config, agent_id="abraham", secret="mail.read",
                       act="read", decision="ALLOW")
    ask = _asked(["yes"])
    out = vault.ask(config, agent_id="abraham", secret="mail.read", act="read",
                    purpose="x", prompt=ask, standing_grants=False)
    assert out.stage == 2 and ask.shown != []
