"""§13 — what a run owes, and to whom. Recorded, never moved.

    | 10%   | the PWM treasury pool                                  |
    | 0-5%  | the agent's author, at the fraction of the slice they chose |
    | rest  | the LLM provider                                       |

    A run on ai4science pays no platform share.

**This computes and records. It does not move anything.** That is the line the
compute design already draws — *the CLI dispatches and attributes; the platform
settles; the CLI must never move tokens* — and it is the right one for the same
reason it was there: a machine that can compute what is owed is useful to run
unattended, and a machine that can move balances unattended is a different risk
entirely. Everything here is arithmetic over a ledger the owner can read.

Two rules do the load-bearing work, and both are rules this system already
applies elsewhere:

  * **unknown is not zero.** A run whose cost could not be metered records
    *nothing* — not a zero. `blast` counts unchecked commands rather than
    calling them clean and `spend` says what it could not measure; a fee ledger
    that wrote 0 for an unmeasured run would quietly say "this owed nothing",
    which is the one thing an accounting must never say by accident.
  * **the shares are exhaustive.** They add to the cost exactly. A split that
    lost a fraction to rounding would leak, every run, in a direction nobody
    would notice until it was large.
"""
import json

import pytest

from ai4science.harness.agents.sarsi import earnings, registry as reg


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


# ── the split ─────────────────────────────────────────────────────────

def test_the_treasury_takes_ten_percent():
    got = earnings.split(100.0)
    assert got.treasury == pytest.approx(10.0)


def test_an_agent_with_no_author_pays_no_author_share():
    """The seven shipped with the machine. Nobody uploaded them, so there is
    nobody for the slice to go to and it does not vanish into the treasury."""
    got = earnings.split(100.0)
    assert got.author == 0.0
    assert got.provider == pytest.approx(90.0)


def test_an_author_takes_their_chosen_fraction_of_five_percent():
    assert earnings.split(100.0, price_share=1.0).author == pytest.approx(5.0)
    assert earnings.split(100.0, price_share=0.5).author == pytest.approx(2.5)
    assert earnings.split(100.0, price_share=0.0).author == 0.0


def test_the_authors_share_comes_out_of_the_providers():
    """Not out of the treasury's, and not added on top. The user pays the same
    either way; what changes is who the rest of it reaches."""
    plain = earnings.split(100.0)
    paid = earnings.split(100.0, price_share=1.0)
    assert plain.treasury == paid.treasury
    assert paid.provider == pytest.approx(plain.provider - paid.author)


def test_five_percent_is_a_ceiling_not_a_multiplier():
    """`price_share` is a fraction OF the slice. A manifest asking for 2.0
    would otherwise take 10%, and the market refuses that at install — this is
    the second place the same number is bounded, because the first one is a
    different program's job."""
    assert earnings.split(100.0, price_share=99.0).author == pytest.approx(5.0)


def test_ai4science_pays_no_platform_share():
    """The difference this product is. The app adds a manager and a front door
    and charges for them; none of that is here."""
    got = earnings.split(100.0, price_share=1.0)
    assert got.platform == 0.0


def test_the_shares_add_to_the_cost_exactly():
    """A split that lost a fraction to rounding would leak, every run, in a
    direction nobody notices until it is large."""
    for cost in (100.0, 1.0, 0.07, 3.3333, 12345.678):
        for share in (0.0, 0.37, 1.0):
            got = earnings.split(cost, price_share=share)
            assert got.treasury + got.author + got.provider + got.platform \
                == pytest.approx(cost, abs=1e-9), (cost, share)


def test_a_zero_cost_run_owes_nothing_and_says_so():
    got = earnings.split(0.0, price_share=1.0)
    assert (got.treasury, got.author, got.provider) == (0.0, 0.0, 0.0)


def test_a_negative_cost_is_refused():
    """There is no such run, and an accounting that accepted one would let a
    single record undo every fee before it."""
    with pytest.raises(ValueError):
        earnings.split(-1.0)


# ── unknown is not zero ───────────────────────────────────────────────

def test_a_run_that_could_not_be_metered_records_nothing(config):
    owed = earnings.record(config, agent_id="sarsi-worker", task_id="tsk_1",
                           cost=None)
    assert owed is None
    assert earnings.owed(config) == []


def test_and_that_is_different_from_a_run_that_owed_nothing(config):
    earnings.record(config, agent_id="sarsi-worker", task_id="tsk_1", cost=0.0)
    rows = earnings.owed(config)
    assert len(rows) == 1 and rows[0].treasury == 0.0


def test_the_unmeasured_ones_are_counted_rather_than_dropped(config):
    """`spend` says "2 tasks could not be measured" for the same reason: a
    total that silently omitted them would read as complete."""
    earnings.record(config, agent_id="sarsi-worker", task_id="tsk_1", cost=None)
    earnings.record(config, agent_id="sarsi-worker", task_id="tsk_2", cost=10.0)
    total = earnings.total(config)
    assert total.unmeasured == 1
    assert total.treasury == pytest.approx(1.0)


def test_a_total_says_what_it_could_not_see(config):
    earnings.record(config, agent_id="sarsi-worker", task_id="tsk_1", cost=None)
    assert "could not be measured" in earnings.total(config).summary


# ── what is recorded ──────────────────────────────────────────────────

def test_a_recorded_run_names_the_agent_and_the_task(config):
    earnings.record(config, agent_id="sarsi-worker", task_id="tsk_9", cost=50.0)
    row = earnings.owed(config)[0]
    assert row.agent_id == "sarsi-worker" and row.task_id == "tsk_9"


def test_an_installed_agents_author_is_credited_by_handle(config, tmp_path):
    """The market record is where `price_share` and the author come from —
    attribution is not a thing the run reports about itself."""
    _install(config, tmp_path, handle="ada", share=0.5)
    earnings.record(config, agent_id="protein-fold", task_id="t", cost=100.0)
    row = earnings.owed(config)[0]
    assert row.author == pytest.approx(2.5)
    assert row.author_handle == "ada"


def test_a_shipped_agent_credits_nobody(config):
    earnings.record(config, agent_id="sarsi-worker", task_id="t", cost=100.0)
    row = earnings.owed(config)[0]
    assert row.author == 0.0 and row.author_handle == ""


def test_removing_the_package_does_not_erase_what_it_earned(config, tmp_path):
    """The author did the work of writing it. An uninstall is the owner's
    decision about the future, not a way to unpay the past."""
    from ai4science.harness.agents.sarsi import market
    _install(config, tmp_path, handle="ada", share=1.0)
    earnings.record(config, agent_id="protein-fold", task_id="t", cost=100.0)
    market.remove(reg.load(config.path), "protein-fold")
    row = earnings.owed(reg.load(config.path))[0]
    assert row.author == pytest.approx(5.0) and row.author_handle == "ada"


# ── and nothing here moves anything ───────────────────────────────────

def test_the_module_has_no_way_to_move_a_balance():
    """The line the compute design already draws: the CLI attributes, the
    platform settles. A machine that can compute what is owed is safe to run
    unattended; one that can move balances unattended is a different risk."""
    forbidden = ("transfer", "send", "pay", "settle", "mint", "burn",
                 "withdraw", "sell")
    assert [n for n in dir(earnings) if any(f in n.lower() for f in forbidden)] == []


def test_owed_is_a_read(config):
    earnings.record(config, agent_id="sarsi-worker", task_id="t", cost=10.0)
    before = earnings.total(config).treasury
    earnings.owed(config)
    earnings.owed(config)
    assert earnings.total(config).treasury == before


def _install(config, tmp_path, *, handle, share):
    from ai4science.harness.agents.sarsi import market
    d = tmp_path / "pkg"
    d.mkdir(exist_ok=True)
    (d / "agent.json").write_text(json.dumps({
        "id": "protein-fold", "version": "1.0.0",
        "author": {"handle": handle, "pwm_address": "0x" + "a" * 40},
        "purpose": "fold a protein", "tools": ["browser"], "outward": [],
        "price_share": share, "requires": {"ai4science": ">=0.1"}}))
    (d / "spec.md").write_text("x")
    market.install(config, d)


# ── it is fed by what was actually metered ────────────────────────────

def test_the_cost_comes_from_spend_not_from_the_run(config):
    """`spend` reads the provider's reported usage from the session's own
    ledger. A run reporting its own cost is the shape this system refuses
    everywhere else — a verdict comes from a verifier, a radius from the
    transcript, and a bill from the meter."""
    from ai4science.harness.agents.sarsi import spend as sp
    row = earnings.from_spend(config, agent_id="sarsi-worker", task_id="t",
                              spend=sp.Spend(pwm=12.0))
    assert row is not None and row.cost == pytest.approx(12.0)


def test_an_unmeasured_session_feeds_nothing(config):
    from ai4science.harness.agents.sarsi import spend as sp
    # `pwm=None` is `spend`'s own word for "this session was not metered by
    # us" — a Claude Code session is not. Reusing it means there is one place
    # that decides what measured means.
    assert earnings.from_spend(config, agent_id="sarsi-worker", task_id="t",
                               spend=sp.Spend(pwm=None)) is None
    assert earnings.total(config).unmeasured == 1


# ── and the owner can read it ─────────────────────────────────────────

def _cli():
    from typer.testing import CliRunner
    from ai4science.cli import app
    return CliRunner(), app


def test_earned_from_the_cli(config, tmp_path):
    _install(config, tmp_path, handle="ada", share=1.0)
    earnings.record(reg.load(config.path), agent_id="protein-fold",
                    task_id="t", cost=100.0)
    runner, app = _cli()
    out = runner.invoke(app, ["sarsi", "earned"]).output
    assert "ada" in out and "5" in out
    assert "treasury" in out.lower()


def test_it_says_what_it_could_not_measure(config):
    earnings.record(config, agent_id="sarsi-worker", task_id="t", cost=None)
    runner, app = _cli()
    assert "could not be measured" in runner.invoke(app, ["sarsi", "earned"]).output


def test_and_says_plainly_that_nothing_is_moved(config):
    """An owner reading a column of numbers should not have to guess whether
    the machine has been paying them out."""
    earnings.record(config, agent_id="sarsi-worker", task_id="t", cost=10.0)
    runner, app = _cli()
    out = runner.invoke(app, ["sarsi", "earned"]).output.lower()
    assert "settle" in out or "not moved" in out or "records" in out


def test_an_empty_ledger_says_so(config):
    runner, app = _cli()
    assert "nothing" in runner.invoke(app, ["sarsi", "earned"]).output.lower()
