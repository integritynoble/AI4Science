"""Bring your own key, and the 10% still applies.

    A user may use their own API key or subscription; the 10% still applies,
    computed at the PWM/token ratio.

A Claude Code session is exactly that case, and until now the economy saw
nothing of it: `spend` reads its tokens but reports `PWM: not charged here`, and
`earnings` recorded it as unmeasured. Both were half right, and the halves are
different numbers that must not be conflated:

  * **what the run COST the owner** in PWM is nothing — they paid Anthropic, or
    it came out of a subscription. `spend` saying *not charged here* stays true
    and unchanged.
  * **what the run OWES** is 10% of its value at the PWM/token ratio. That is
    the fee, and it applies on your own key by design — otherwise every run
    would be free by bringing one.

So a BYO-key run owes the treasury and the author, and the **provider is not
owed anything here** because they were already paid outside PWM. Recording them
as owed would double-count a bill the owner has already settled.

**The cache rate is the whole correctness of this.** A Claude Code session's
cached tokens dwarf its fresh input — one live session read 1,006 fresh against
8,201,359 cached — so pricing cache at the input rate would inflate the fee by
orders of magnitude. `spend` already keeps the two apart, and says why: *both
are "input" and they are nowhere near the same cost.*
"""
import pytest

from ai4science.harness.agents.sarsi import earnings, spend as sp
from ai4science.llm import pricing


# ── the cache rate ────────────────────────────────────────────────────

def test_cached_input_is_not_priced_as_fresh_input():
    """The live shape: a handful of fresh tokens against millions of cached."""
    fresh = pricing.price_session("claude-opus-4-8", input=1_000_000,
                                  output=0, cached=0, cache_write=0)
    cached = pricing.price_session("claude-opus-4-8", input=0, output=0,
                                   cached=1_000_000, cache_write=0)
    assert cached["usd"] < fresh["usd"]
    assert cached["usd"] == pytest.approx(fresh["usd"] * pricing.CACHE_READ)


def test_a_cache_write_costs_more_than_fresh_input():
    """It is written once and read many times; the write carries a premium."""
    fresh = pricing.price_session("claude-opus-4-8", input=1_000_000,
                                  output=0, cached=0, cache_write=0)
    write = pricing.price_session("claude-opus-4-8", input=0, output=0,
                                  cached=0, cache_write=1_000_000)
    assert write["usd"] > fresh["usd"]


def test_the_live_session_is_not_priced_as_millions_of_fresh_tokens():
    """1,006 in / 195,373 out / 8,201,359 cached — a real session from grace.
    Priced with cache at the input rate this would be absurd, and the fee
    computed from it would be too."""
    got = pricing.price_session("claude-opus-4-8", input=1006, output=195_373,
                                cached=8_201_359, cache_write=458_860)
    naive = pricing.price_session("claude-opus-4-8",
                                  input=1006 + 8_201_359 + 458_860,
                                  output=195_373, cached=0, cache_write=0)
    assert got["usd"] < naive["usd"]


def test_an_unknown_model_says_it_is_a_fallback():
    """A price guessed from a default is not a price read from a table, and a
    fee built on the first should say so."""
    got = pricing.price_session("some-model-nobody-has-heard-of",
                                input=1000, output=1000, cached=0,
                                cache_write=0)
    assert got["known_model"] is False
    known = pricing.price_session("claude-opus-4-8", input=1, output=1,
                                  cached=0, cache_write=0)
    assert known["known_model"] is True


# ── what a BYO-key run owes ───────────────────────────────────────────

def _spend(**kw):
    base = dict(input_tokens=1000, output_tokens=1000, cached_tokens=0,
                cache_write_tokens=0, pwm=None)
    base.update(kw)
    return sp.Spend(**base)


def test_a_claude_code_run_is_now_priced():
    """It was recorded as unmeasured, so the economy saw nothing of the runs
    this machine actually does."""
    got = earnings.notional(_spend(), model="claude-opus-4-8")
    assert got is not None and got > 0


def test_and_the_treasury_is_owed_ten_percent_of_it():
    value = earnings.notional(_spend(), model="claude-opus-4-8")
    got = earnings.split_byo(value)
    assert got.treasury == pytest.approx(value * 0.10)


def test_the_provider_is_not_owed_anything_here():
    """They were paid outside PWM — by the API bill or the subscription.
    Recording them as owed would double-count a bill already settled."""
    got = earnings.split_byo(100.0)
    assert got.provider == 0.0
    assert got.paid_outside == pytest.approx(100.0 - got.treasury - got.author)


def test_the_author_still_earns_on_a_byo_run():
    """An author's slice is for the agent being used, not for who paid the
    provider."""
    got = earnings.split_byo(100.0, price_share=1.0)
    assert got.author == pytest.approx(5.0)


def test_and_the_owed_shares_still_add_up():
    for value in (100.0, 0.07, 3.3333):
        for share in (0.0, 0.5, 1.0):
            got = earnings.split_byo(value, price_share=share)
            assert got.treasury + got.author + got.paid_outside \
                == pytest.approx(value, abs=1e-9)


# ── unknown is still not zero ─────────────────────────────────────────

def test_a_session_with_no_token_counts_is_still_unmeasured():
    """The rule does not weaken because there is now a way to price. A
    transcript that could not be read gives no tokens, and no tokens is not
    zero tokens."""
    assert earnings.notional(_spend(input_tokens=None, output_tokens=None,
                                    cached_tokens=None,
                                    cache_write_tokens=None),
                             model="claude-opus-4-8") is None


def test_a_metered_run_is_left_alone():
    """When the harness priced it itself, that number wins — this path is only
    for the sessions it does not meter."""
    assert earnings.notional(_spend(pwm=7.0), model="claude-opus-4-8") == \
        pytest.approx(7.0)


# ── and it reaches a real run ─────────────────────────────────────────

import json
from ai4science.harness.agents.sarsi import registry as reg


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


def test_from_spend_now_records_a_claude_code_run(config):
    """The gap this closes: `earned` read "0 runs, 1 could not be measured"
    after a run that plainly happened."""
    row = earnings.from_spend(config, agent_id="sarsi-worker", task_id="t",
                              spend=_spend(), model="claude-opus-4-8")
    assert row is not None and row.cost > 0
    assert earnings.total(config).runs == 1


def test_and_records_it_as_paid_outside_not_owed_to_the_provider(config):
    earnings.from_spend(config, agent_id="sarsi-worker", task_id="t",
                        spend=_spend(), model="claude-opus-4-8")
    row = earnings.owed(config)[0]
    assert row.provider == 0.0
    assert row.treasury > 0


def test_a_session_the_harness_metered_is_unchanged(config):
    """The old path still wins where it applies — the provider IS owed there."""
    earnings.from_spend(config, agent_id="sarsi-worker", task_id="t",
                        spend=_spend(pwm=100.0), model="claude-opus-4-8")
    row = earnings.owed(config)[0]
    assert row.provider == pytest.approx(90.0)


def test_and_an_unreadable_one_is_still_unmeasured(config):
    assert earnings.from_spend(
        config, agent_id="sarsi-worker", task_id="t",
        spend=_spend(input_tokens=None, output_tokens=None,
                     cached_tokens=None, cache_write_tokens=None),
        model="claude-opus-4-8") is None
    assert earnings.total(config).unmeasured == 1
