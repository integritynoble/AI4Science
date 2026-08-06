"""The exchange node: it earns, and it never touches the owner's work.

    When it runs short, an exchange node starts: visible, bounded by a budget
    the owner sets, and never touching the owner's tasks — it is not a worker,
    holds no task list, and may not drive a session. With enough PWM the owner
    may stop it.

Four properties, and three of them are refusals. That is the right proportion:
this is a thing that runs on the owner's machine to make money, and every way
it could quietly become something else is worth closing by code path rather
than by intention.

  * **it is not a worker.** `workers()` does not offer it, `admit` refuses it,
    and `assign` refuses to drive a session for it. That is the invariant
    *the agent you talk to does not execute* with a sibling: **the thing that
    earns does not work for you.** A node that could hold a task would be an
    agent nobody granted anything to, running on the owner's machine, paid by
    somebody else.
  * **it holds no task list.** Not an empty one — asking is a refusal, because
    an empty list invites something to fill it.
  * **it is bounded.** It will not start without a budget the owner set, and it
    stops at it. An earner with no ceiling is a machine deciding for itself how
    much of the owner's electricity to spend.
  * **it is visible.** It appears in the listings the owner already reads, as
    what it is, so a machine that is earning never looks like a machine that
    is idle.

It records what it supplied. It moves nothing — the same line `earnings` holds,
for the same reason.
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


# ── it is not a worker ────────────────────────────────────────────────

def test_it_is_not_offered_as_a_worker(config):
    exchange.start(config, budget_pwm=10.0)
    assert exchange.NODE_ID not in [a.id for a in reg.load(config.path).workers()]


def test_it_cannot_be_given_a_task(config):
    """The sibling of the invariant: the thing that earns does not work for
    you. A node holding a task would be an agent nobody granted anything to,
    running on the owner's machine, paid by somebody else."""
    exchange.start(config, budget_pwm=10.0)
    from ai4science.harness.agents.sarsi import worker as wk
    fresh = reg.load(config.path)
    node = fresh.agents[exchange.NODE_ID]
    d = wk.Directive(agent_id=node.id, goal="do some work for me")
    with pytest.raises(wk.NotAWorker) as e:
        wk.admit(fresh, node, d)
    # Asserted on the WORDING, not on the id: `exchange` appears in
    # `exchange-node`, so matching the id let the refusal say "is a manager",
    # which it is not. A refusal that names the wrong thing sends the owner to
    # the wrong fix.
    assert "manager" not in str(e.value)
    assert "supplies capacity" in str(e.value) or "not a worker" in str(e.value)


def test_it_cannot_drive_a_session(config):
    exchange.start(config, budget_pwm=10.0)
    from ai4science.harness.agents.sarsi import (plan as pl, session as ses,
                                                 task as tsk, worker as wk)
    fresh = reg.load(config.path)
    node = fresh.agents[exchange.NODE_ID]
    d = wk.Directive(agent_id=node.id, goal="x")
    t = tsk.Task(id="tsk_x", agent_id=node.id, goal="x")
    with pytest.raises(Exception) as e:
        ses.assign(fresh, node, t, runtime=_Runtime(), installed=lambda: set())
    assert "exchange" in str(e.value).lower() or "worker" in str(e.value).lower()


def test_it_holds_no_task_list(config):
    """Not an empty one. An empty list is a thing something can fill."""
    exchange.start(config, budget_pwm=10.0)
    with pytest.raises(exchange.NotAnAgent, match="task"):
        exchange.tasks_of(reg.load(config.path))


# ── it is bounded ─────────────────────────────────────────────────────

def test_it_will_not_start_without_a_budget(config):
    """An earner with no ceiling is a machine deciding for itself how much of
    the owner's electricity to spend."""
    with pytest.raises(exchange.NotAnAgent, match="budget"):
        exchange.start(config, budget_pwm=None)


def test_nor_with_a_budget_of_nothing(config):
    with pytest.raises(exchange.NotAnAgent):
        exchange.start(config, budget_pwm=0.0)


def test_it_stops_when_it_reaches_the_budget(config):
    exchange.start(config, budget_pwm=10.0)
    exchange.supplied(config, kind="llm", pwm=4.0)
    assert exchange.status(config).running is True
    exchange.supplied(config, kind="llm", pwm=7.0)
    got = exchange.status(config)
    assert got.running is False
    assert "budget" in got.why.lower()


def test_and_what_it_supplied_is_kept_after_it_stops(config):
    exchange.start(config, budget_pwm=5.0)
    exchange.supplied(config, kind="gpu", pwm=6.0)
    assert exchange.status(config).earned == pytest.approx(6.0)


def test_supplying_when_it_is_not_running_is_refused(config):
    """Otherwise the record grows for a node the owner stopped."""
    with pytest.raises(exchange.NotAnAgent, match="not running"):
        exchange.supplied(config, kind="llm", pwm=1.0)


# ── the owner may stop it ─────────────────────────────────────────────

def test_the_owner_can_stop_it(config):
    exchange.start(config, budget_pwm=10.0)
    exchange.stop(config)
    assert exchange.status(config).running is False


def test_stopping_takes_it_out_of_the_roster(config):
    exchange.start(config, budget_pwm=10.0)
    exchange.stop(config)
    assert exchange.NODE_ID not in reg.load(config.path).agents


def test_but_keeps_what_it_earned(config):
    exchange.start(config, budget_pwm=10.0)
    exchange.supplied(config, kind="llm", pwm=3.0)
    exchange.stop(config)
    assert exchange.status(config).earned == pytest.approx(3.0)


# ── it is visible ─────────────────────────────────────────────────────

def test_it_appears_in_the_listing_as_what_it_is(config):
    from ai4science.harness.agents.sarsi import admin
    exchange.start(config, budget_pwm=10.0)
    rows = {r["id"]: r for r in admin.agent_rows(reg.load(config.path))}
    assert exchange.NODE_ID in rows
    assert rows[exchange.NODE_ID]["role"] == exchange.ROLE
    assert rows[exchange.NODE_ID]["drives_sessions"] is False


def test_a_machine_that_is_earning_never_looks_idle(config):
    exchange.start(config, budget_pwm=10.0)
    exchange.supplied(config, kind="llm", pwm=2.0)
    got = exchange.status(config)
    assert got.running and got.earned == pytest.approx(2.0)
    assert got.budget == pytest.approx(10.0)


def test_status_with_no_node_says_so_rather_than_looking_stopped(config):
    """"Never started" and "started and stopped" are different, and the second
    has earnings behind it."""
    got = exchange.status(config)
    assert got.running is False
    assert "never" in got.why.lower() or "not started" in got.why.lower()


# ── and it moves nothing ──────────────────────────────────────────────

def test_the_module_has_no_way_to_move_a_balance():
    forbidden = ("transfer", "pay", "settle", "mint", "burn", "withdraw",
                 "sell")
    assert [n for n in dir(exchange)
            if any(f in n.lower() for f in forbidden)] == []


class _Runtime:
    engine = "claude"

    def start(self, name, cwd, **kw):
        return {"ok": True, "name": name, "pid": 1, "cwd": cwd}

    def send(self, name, text, **kw):
        return {"ok": True}

    def stop(self, name):
        return {"ok": True}

    def set_ceiling(self, name, ceiling):
        return {"name": name, "ceiling": ceiling}
