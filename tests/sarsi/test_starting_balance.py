"""The non-exchangeable starting balance: spendable on fees, never sellable.

    Everyone starts with a small non-exchangeable balance to pay it — spendable
    on fees, never sellable, and visibly distinct so it cannot leak into the
    exchangeable supply.

I held this back through the whole economy build, on the grounds that it *holds
a balance* and holding a balance raises custody. That reasoning was half right,
and the half it got wrong is the design:

  **what made a balance dangerous was that it could MOVE.** This one cannot. It
  is granted once and can only ever be spent DOWN, and the only thing it can be
  spent on is a fee this machine already computes. There is no transfer, no
  conversion, no withdrawal — not "not implemented yet", but no function, and a
  test that fails if one appears.

So it is not money held in custody. It is a fee credit that can only be
destroyed, and the one property that has to hold is that it can never become
anything else:

  * **it never becomes exchangeable.** No conversion, and the two are reported
    apart wherever either is reported, so a total that mixed them could not be
    written by accident.
  * **it is granted once.** A balance that can be topped up on request is an
    infinite one, and every fee after the first would be free.
  * **it cannot go negative.** Spending more than is there is refused, not
    overdrawn — an overdraft is a loan, and a loan is the custody question
    coming back in through the side.
  * **spending it does not erase the fee.** The treasury is still owed exactly
    what it was owed; what changes is the record of how it was paid.
"""
import json

import pytest

from ai4science.harness.agents.sarsi import balance, registry as reg


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path / "state"))
    return tmp_path


@pytest.fixture
def config(tmp_path):
    root = tmp_path / "state"
    root.mkdir(parents=True, exist_ok=True)
    path = reg.config_path(root)
    path.write_text(json.dumps(reg.default_config(owner_id="7007143162")))
    c = reg.load(path)
    c.ensure_dirs()
    return c


# ── it can never become exchangeable ──────────────────────────────────

def test_there_is_no_function_that_moves_it():
    """Not "not implemented yet" — absent, and a test that fails if one turns
    up. That is the difference between a fee credit and money in custody."""
    forbidden = ("transfer", "send", "sell", "withdraw", "convert", "exchange",
                 "cash", "redeem", "swap", "mint")
    assert [n for n in dir(balance)
            if any(f in n.lower() for f in forbidden)] == []


def test_it_is_reported_apart_from_anything_exchangeable(config):
    balance.grant(config)
    got = balance.of(config)
    assert got.exchangeable is False
    assert "non-exchangeable" in got.summary.lower()


def test_the_summary_never_reads_as_a_single_pot(config):
    """A number with no kind beside it is a number somebody will add up."""
    balance.grant(config)
    balance.spend(config, pwm=1.0, fee_for="tsk_1")
    text = balance.of(config).summary.lower()
    assert "fee" in text
    assert "sell" in text or "not exchangeable" in text or "never" in text


# ── granted once ──────────────────────────────────────────────────────

def test_a_new_machine_gets_one(config):
    got = balance.grant(config)
    assert got.remaining == pytest.approx(balance.STARTING)
    assert balance.STARTING > 0


def test_granting_twice_is_refused(config):
    """A balance that can be topped up on request is an infinite one, and every
    fee after the first would be free."""
    balance.grant(config)
    with pytest.raises(balance.Refused, match="once"):
        balance.grant(config)


def test_and_spending_it_down_does_not_re_open_the_grant(config):
    balance.grant(config)
    balance.spend(config, pwm=balance.STARTING, fee_for="tsk_1")
    assert balance.of(config).remaining == 0.0
    with pytest.raises(balance.Refused, match="once"):
        balance.grant(config)


# ── it cannot go negative ─────────────────────────────────────────────

def test_spending_more_than_is_there_is_refused(config):
    """An overdraft is a loan, and a loan is the custody question coming back
    in through the side."""
    balance.grant(config)
    with pytest.raises(balance.Refused, match="only"):
        balance.spend(config, pwm=balance.STARTING + 1, fee_for="tsk_1")


def test_and_the_refusal_leaves_the_balance_untouched(config):
    balance.grant(config)
    before = balance.of(config).remaining
    with pytest.raises(balance.Refused):
        balance.spend(config, pwm=before + 1, fee_for="tsk_1")
    assert balance.of(config).remaining == pytest.approx(before)


def test_a_negative_spend_is_refused(config):
    """It would be a credit wearing a debit's name."""
    balance.grant(config)
    with pytest.raises(balance.Refused):
        balance.spend(config, pwm=-5.0, fee_for="tsk_1")


def test_spending_before_there_is_a_balance_is_refused(config):
    with pytest.raises(balance.Refused):
        balance.spend(config, pwm=1.0, fee_for="tsk_1")


# ── only a fee ────────────────────────────────────────────────────────

def test_a_spend_must_name_the_fee_it_pays(config):
    """Spendable ON FEES. A debit with no fee behind it is the balance being
    used as money, which is the one thing it is not."""
    balance.grant(config)
    with pytest.raises(balance.Refused, match="fee"):
        balance.spend(config, pwm=1.0, fee_for="")


def test_and_what_it_paid_for_is_kept(config):
    balance.grant(config)
    balance.spend(config, pwm=2.0, fee_for="tsk_9")
    assert [r.fee_for for r in balance.history(config)] == ["tsk_9"]


# ── the fee is still owed, and still recorded ─────────────────────────

def test_paying_from_it_does_not_erase_the_fee(config):
    """The treasury is owed exactly what it was owed. What changes is the
    record of HOW it was paid, not whether it was."""
    from ai4science.harness.agents.sarsi import earnings as ern
    ern.record(config, agent_id="sarsi-worker", task_id="t", cost=100.0)
    owed = ern.total(config).treasury
    balance.grant(config)
    balance.spend(config, pwm=owed, fee_for="t")
    assert ern.total(config).treasury == pytest.approx(owed)


def test_the_two_ledgers_stay_separate(config):
    """One says what is owed, the other says what this credit covered. A single
    ledger would make "paid" and "owed" one number that cannot disagree — and
    they must be able to, or nobody could tell an unpaid fee from a paid one."""
    from ai4science.harness.agents.sarsi import earnings as ern
    balance.grant(config)
    balance.spend(config, pwm=1.0, fee_for="t")
    assert ern.total(config).runs == 0
    assert len(balance.history(config)) == 1


# ── and the owner can see it ──────────────────────────────────────────

def _cli():
    from typer.testing import CliRunner
    from ai4science.cli import app
    return CliRunner(), app


def test_the_cli_shows_it_and_says_what_it_is(config):
    balance.grant(config)
    runner, app = _cli()
    out = runner.invoke(app, ["sarsi", "balance"]).output.lower()
    assert "non-exchangeable" in out
    assert "fee" in out


def test_before_it_is_granted_it_says_so(config):
    runner, app = _cli()
    out = runner.invoke(app, ["sarsi", "balance"]).output.lower()
    # "granted ... yet" rather than a bare 0. A zero would read as a spent
    # balance, and "never had one" and "spent it all" are different facts.
    assert "granted" in out and "yet" in out
    assert "--grant" in out
