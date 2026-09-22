"""The durable session budget (A03): a kill between reserve and reconcile
leaves an `unknown` action that still counts, is never re-dispatched under
its id, and is listed for the owner."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from ai4science.harness.runtime import budget as b


def test_amounts_are_exact_and_validated():
    assert b.micro("0.1") == 100_000 and b.micro(1) == 1_000_000
    for bad in ["nan", "inf", -1, "lots"]:
        with pytest.raises(ValueError):
            b.micro(bad)


def test_reserve_reconcile_and_cap(tmp_path):
    bud = b.Budget(tmp_path / "s.sqlite", cap_pwm=1)
    bud.reserve("a", 0.4)
    bud.reserve("b", 0.5)
    with pytest.raises(b.BudgetError, match="cap reached"):
        bud.reserve("c", 0.2)
    bud.reconcile("a", delivered=True, actual_pwm=0.1)     # actual replaces the estimate
    assert bud.remaining() == b.micro(0.4)
    bud.reserve("c", 0.2)
    bud.reconcile("b", delivered=False)                      # released counts nothing
    assert bud.snapshot()["used_pwm"] == pytest.approx(0.3)
    with pytest.raises(b.BudgetError, match="already"):
        bud.reserve("a", 0.1)
    bud.reconcile("a", delivered=True, actual_pwm=0.1)      # replay is idempotent
    with pytest.raises(b.BudgetError):
        bud.reconcile("a", delivered=True, actual_pwm=0.2)  # a different actual is a conflict
    with pytest.raises(b.BudgetError):
        bud.reconcile("b", delivered=True)                  # released cannot become delivered
    with pytest.raises(b.BudgetError, match="unknown action"):
        bud.reconcile("zzz", delivered=True)


def test_kill_at_dispatch_leaves_an_unknown_action_a_fresh_process_sees(tmp_path):
    path = tmp_path / "s.sqlite"
    b.Budget(path, cap_pwm=1).close()
    code = (
        "import os, sys; from ai4science.harness.runtime import budget as b\n"
        "bud = b.Budget(sys.argv[1]); bud.reserve('task:1', 0.6, note='child')\n"
        "os._exit(9)\n"                     # SIGKILL stand-in: no cleanup, no reconcile
    )
    r = subprocess.run([sys.executable, "-c", code, str(path)], cwd=Path(__file__).parents[2])
    assert r.returncode == 9
    fresh = b.Budget(path)                                     # a new process, no cap given
    assert fresh.unknown() == ["task:1"]
    assert fresh.status("task:1") == "unknown"
    assert fresh.remaining() == b.micro(0.4)                   # still counted
    with pytest.raises(b.BudgetError, match="already unknown"):
        fresh.reserve("task:1", 0.6)                           # never re-dispatched under its id
    with pytest.raises(b.BudgetError, match="cap reached"):
        fresh.reserve("task:2", 0.5)
    fresh.reconcile("task:1", delivered=False)                 # the owner resolves it
    fresh.reserve("task:2", 0.5)
    with pytest.raises(b.BudgetError, match="cannot change"):
        b.Budget(path, cap_pwm=5)                              # a resume cannot raise the cap


def test_open_for_session(tmp_path):
    assert b.open_for_session(tmp_path, "sid") is None         # uncapped: no ledger
    created = b.open_for_session(tmp_path, "sid", cap_pwm=2)
    created.reserve("x", 1); created.close()
    reopened = b.open_for_session(tmp_path, "sid")             # resume: cap from disk
    assert reopened.snapshot()["cap_pwm"] == 2 and reopened.unknown() == ["x"]


def test_guard_session_reserves_before_and_reconciles_after(tmp_path):
    bud = b.Budget(tmp_path / "s.sqlite", cap_pwm=1)
    calls = []

    class Child:
        def __init__(self):
            self.meter = lambda u: calls.append(("meter", u))
        def run_turn(self, text, images=None):
            self.meter(7)                                      # a Usage stand-in
            calls.append(("ran", text))
            return "done"

    c = b.guard_session(Child(), bud, action_id="task:1", estimate_pwm=0.3,
                        cost_of=lambda u: 0.02 * u)
    assert c.run_turn("go") == "done"
    assert bud.status("task:1") == "delivered"
    assert bud.snapshot()["actions"][0]["actual_pwm"] == pytest.approx(0.14)
    assert ("ran", "go") in calls and ("meter", 7) in calls

    class Boom(Child):
        def run_turn(self, text, images=None):
            raise RuntimeError("provider down")

    c2 = b.guard_session(Boom(), bud, action_id="task:2", estimate_pwm=0.3)
    with pytest.raises(RuntimeError):
        c2.run_turn("go")
    assert bud.status("task:2") == "unknown"                   # dispatched, outcome unknown

    c3 = b.guard_session(Child(), bud, action_id="task:3", estimate_pwm=0.9)
    with pytest.raises(b.BudgetError, match="cap reached"):
        c3.run_turn("go")                                      # refused BEFORE running
    assert ("ran", "go") in calls and calls.count(("ran", "go")) == 1
    assert bud.status("task:3") is None
