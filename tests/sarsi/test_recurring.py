"""`abraham`'s second characteristic failure: **quiet accumulation.**

Subscriptions, renewals and standing bookings keep costing after everyone has
forgotten them. So a recurring obligation is its **own act class**: approving it
approves *one schedule*, not an open-ended commitment, and each one resurfaces
on a cadence **with what it has cost so far**.

An agent that can create recurring charges and never mentions them again has
been given a budget nobody agreed to.
"""
import pytest

from ai4science.harness.agents.sarsi import recurring as rec, registry as reg


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
    return config.agents["abraham"]


DAY = 86400.0


def _obligation(config, agent, **kw):
    base = dict(what="streaming subscription", amount=9.99, currency="GBP",
                every="month", payee="a streaming service")
    base.update(kw)
    return rec.approve(config, agent, now=lambda: 0.0, **base)


# ── approving one schedule, not an open commitment ────────────────────

def test_approving_records_one_schedule(config, agent):
    ob = _obligation(config, agent)
    assert ob["every"] == "month" and ob["amount"] == 9.99


def test_an_obligation_must_name_what_it_costs_and_how_often(config, agent):
    with pytest.raises(rec.Incomplete, match="every"):
        rec.approve(config, agent, what="something", amount=5.0,
                    currency="GBP", every="", payee="someone")


def test_an_obligation_must_name_its_payee(config, agent):
    with pytest.raises(rec.Incomplete, match="payee"):
        rec.approve(config, agent, what="something", amount=5.0,
                    currency="GBP", every="month", payee="")


def test_it_is_recorded_as_its_own_act_class(config, agent):
    from ai4science.harness.agents.sarsi import ledger
    _obligation(config, agent)
    assert ledger.count(config, "outward", kind="recurring") == 1


# ── what it has cost so far ───────────────────────────────────────────

def test_cost_so_far_starts_at_nothing(config, agent):
    ob = _obligation(config, agent)
    assert rec.cost_so_far(config, agent, ob["id"], now=lambda: 0.0) == 0.0


def test_cost_so_far_accrues_with_the_schedule(config, agent):
    ob = _obligation(config, agent)
    after_three_months = 92 * DAY
    assert rec.cost_so_far(config, agent, ob["id"],
                           now=lambda: after_three_months) == pytest.approx(29.97)


def test_a_weekly_obligation_accrues_faster(config, agent):
    ob = _obligation(config, agent, every="week", amount=2.0)
    assert rec.cost_so_far(config, agent, ob["id"],
                           now=lambda: 21 * DAY) == pytest.approx(6.0)


# ── it resurfaces ─────────────────────────────────────────────────────

def test_nothing_is_due_before_the_cadence(config, agent):
    _obligation(config, agent)
    assert rec.due(config, agent, now=lambda: 10 * DAY) == []


def test_it_resurfaces_after_the_review_cadence(config, agent):
    _obligation(config, agent)
    assert len(rec.due(config, agent, now=lambda: rec.REVIEW_EVERY_S + 1)) == 1


def test_what_resurfaces_carries_the_running_cost(config, agent):
    _obligation(config, agent)
    line = rec.resurface(config, agent, now=lambda: 200 * DAY)
    assert "streaming subscription" in line
    assert "so far" in line.lower()
    # 200 days is 6 COMPLETED months: a partial period has not been charged
    assert "59.94" in line


def test_reviewing_resets_the_cadence_without_cancelling(config, agent):
    ob = _obligation(config, agent)
    rec.reviewed(config, agent, ob["id"], now=lambda: 200 * DAY)
    assert rec.due(config, agent, now=lambda: 200 * DAY + 1) == []
    assert len(rec.all_of(config, agent)) == 1        # still standing


def test_an_empty_review_says_nothing_rather_than_padding(config, agent):
    assert rec.resurface(config, agent, now=lambda: 200 * DAY) == ""


# ── cancelling ────────────────────────────────────────────────────────

def test_cancelling_keeps_the_record(config, agent):
    ob = _obligation(config, agent)
    rec.cancel(config, agent, ob["id"], now=lambda: 100 * DAY)
    assert rec.all_of(config, agent)[0]["cancelled_at"] is not None
    assert rec.due(config, agent, now=lambda: 400 * DAY) == []


def test_a_cancelled_obligation_stops_accruing(config, agent):
    ob = _obligation(config, agent)
    rec.cancel(config, agent, ob["id"], now=lambda: 31 * DAY)
    at_one_month = rec.cost_so_far(config, agent, ob["id"], now=lambda: 31 * DAY)
    assert rec.cost_so_far(config, agent, ob["id"],
                           now=lambda: 400 * DAY) == at_one_month


# ── it is not only abraham's, but it is mostly ────────────────────────

def test_any_agent_may_hold_one_but_they_do_not_share(config):
    _obligation(config, config.agents["abraham"])
    assert rec.all_of(config, config.agents["work"]) == []
