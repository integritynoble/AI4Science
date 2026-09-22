"""The exchange node's bookkeeping, after the September 21 source audit.

Three follow-ups it named: a supply accepted any float, a restarted node kept
counting what an earlier run had supplied, and nothing stopped one delivery
from being recorded twice. Each is now a code path, not an intention.
"""
import json

import pytest

from ai4science.harness.agents.sarsi import exchange, registry as reg


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


# ── a supply is a positive finite amount ──────────────────────────────

@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf"),
                                 -1.0, 0.0, "lots", None])
def test_a_supply_that_is_not_a_positive_finite_amount_is_refused(config, bad):
    exchange.start(config, budget_pwm=10.0)
    with pytest.raises(exchange.NotAnAgent, match="positive finite|number"):
        exchange.supplied(config, kind="llm", pwm=bad)
    assert exchange.status(config).earned == 0.0


# ── each start is its own bounded run ─────────────────────────────────

def test_a_restart_does_not_inherit_what_the_last_run_supplied(config):
    exchange.start(config, budget_pwm=10.0)
    exchange.supplied(config, kind="llm", pwm=7.0)
    exchange.stop(config)
    exchange.start(config, budget_pwm=10.0)
    got = exchange.status(config)
    assert got.running is True
    assert got.earned == 0.0 and got.budget == 10.0
    # ...so the new run gets its whole budget, not the 3 PWM that were left.
    exchange.supplied(config, kind="llm", pwm=8.0)
    assert exchange.status(config).running is True


# ── one delivery counts once ──────────────────────────────────────────

def test_a_receipt_recorded_twice_counts_once(config):
    exchange.start(config, budget_pwm=10.0)
    exchange.supplied(config, kind="llm", pwm=4.0, receipt="rcpt-1")
    again = exchange.supplied(config, kind="llm", pwm=4.0, receipt="rcpt-1")
    assert again.earned == pytest.approx(4.0)
    assert exchange.status(config).earned == pytest.approx(4.0)


def test_the_same_receipt_with_another_amount_is_a_conflict(config):
    exchange.start(config, budget_pwm=10.0)
    exchange.supplied(config, kind="llm", pwm=4.0, receipt="rcpt-1")
    with pytest.raises(exchange.NotAnAgent, match="conflict"):
        exchange.supplied(config, kind="llm", pwm=5.0, receipt="rcpt-1")
    assert exchange.status(config).earned == pytest.approx(4.0)


def test_a_receipt_survives_a_restart(config):
    """A delivery replayed after the node was stopped and started again is
    still the same delivery."""
    exchange.start(config, budget_pwm=10.0)
    exchange.supplied(config, kind="llm", pwm=4.0, receipt="rcpt-1")
    exchange.stop(config)
    exchange.start(config, budget_pwm=10.0)
    exchange.supplied(config, kind="llm", pwm=4.0, receipt="rcpt-1")
    assert exchange.status(config).earned == 0.0


def test_supplies_without_a_receipt_still_add_up(config):
    exchange.start(config, budget_pwm=10.0)
    exchange.supplied(config, kind="llm", pwm=1.0)
    exchange.supplied(config, kind="llm", pwm=1.0)
    assert exchange.status(config).earned == pytest.approx(2.0)


def test_it_still_moves_nothing():
    forbidden = ("transfer", "pay", "settle", "mint", "burn", "withdraw", "sell")
    assert [n for n in dir(exchange)
            if any(f in n.lower() for f in forbidden)] == []
