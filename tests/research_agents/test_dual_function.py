"""The two functions, and the line between them.

The line is the whole design of point 11: a person asking for help is not the
agent deciding to spend their money. So function 1 works with the switch off,
function 2 refuses without it, and turning it off stops work already running.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from ai4science.harness.agents.research_agents import Budget, build
from ai4science.harness.agents.research_agents.dual import (
    BENCHMARK, Ledgers, OWNER_SET, SELF_DIRECTED, autonomous_loop,
    autonomous_round, run_user_task,
)
from .conftest import bench_or_skip as benchmark_for  # skips, not fails, when a corpus
# is absent — see conftest for why the two test files used to disagree about that.


class Sim:
    def __init__(self, ws: Path):
        self.ws = Path(ws)
        self.ws.mkdir(parents=True, exist_ok=True)
        self.executed = []

    def open_run(self, goal, cp, limits, interaction_profile="I1", agent_id=None):
        return {"run_id": "t", "capability_profile": cp,
                "interaction_profile": interaction_profile,
                "workspace_path": str(self.ws)}

    def stage_input(self, run_id, rel, content):
        d = self.ws / rel
        d.parent.mkdir(parents=True, exist_ok=True)
        d.write_bytes(content)
        return {"ok": True}

    def classify(self, run_id, kind, *, step_summary="", action_type=None):
        return {"decision": "ACT", "reason": "test"}

    def sandbox_execute(self, run_id, cmd, **kw):
        self.executed.append(cmd)
        p = subprocess.run([sys.executable] + cmd[1:], cwd=str(self.ws),
                           capture_output=True, text=True)
        return {"exit_code": p.returncode, "is_error": p.returncode != 0,
                "timed_out": False, "stdout": p.stdout, "stderr": p.stderr,
                "artifacts": []}


def _store(tmp_path):
    from ai4science.harness.runtime.task_store import TaskStore
    return TaskStore(tmp_path / "tasks")


# --------------------------------------------- 1. the ordinary function

def test_a_user_task_runs_with_the_autonomous_function_OFF(tmp_path):
    """The distinction point 11 rests on. If ordinary help needed the
    autonomous permission, the off switch would mean 'the agent is useless'
    rather than 'the agent does not act unasked'."""
    agent = build("low-dose-ct")
    assert not agent.switch.on
    out = run_user_task(agent, benchmark_for("low-dose-ct"),
                        client=Sim(tmp_path / "run"), store=_store(tmp_path),
                        task_id="user-1", workspace=tmp_path / "seed")
    assert out["status"] == "delivered", out
    assert out["metrics"]["lesion_cnr"] > 0
    assert not agent.switch.on, "and it did not turn itself on to do the work"


def test_the_user_task_is_verified_by_the_field_s_own_judge(tmp_path):
    """The judge runs and its verdict decides the outcome — which is not the
    same as the outcome being 'delivered'.

    On real capsule data the analytic prior does not beat plain intensity, so
    this field's judge refuses the result and the task ends blocked after its
    repairs. That is function 1 working: a person asked, the agent worked it,
    and the domain's own criteria said no. An earlier version asserted
    'delivered' and so was really asserting that the reference method wins."""
    agent = build("pill-camera")
    out = run_user_task(agent, benchmark_for("pill-camera"),
                        client=Sim(tmp_path / "run"), store=_store(tmp_path),
                        task_id="user-2", workspace=tmp_path / "seed")
    assert out["status"] in ("delivered", "blocked")
    assert "auc" in out["metrics"] and "baseline_auc" in out["metrics"], \
        "the field's own judge produced its own metrics"
    if out["status"] == "blocked":
        assert out["metrics"]["auc"] <= out["metrics"]["baseline_auc"]


def test_a_user_task_delivers_when_the_method_meets_the_field_s_bar(tmp_path):
    """And the other side of it: where the reference method does clear the
    domain's criteria, the same path delivers.

    This was `drug-design` until its judge began refusing a pinned EF@1% — the
    metric sits at 100% of its own ceiling and can no longer rank one method
    above another. `low-dose-ct` is the agent whose reference method still
    clears its field's bar on real data, so it is the one that demonstrates
    delivery here. What the test is about is the *path*, not which domain
    happens to exercise it."""
    agent = build("low-dose-ct")
    out = run_user_task(agent, benchmark_for("low-dose-ct"),
                        client=Sim(tmp_path / "run"), store=_store(tmp_path),
                        task_id="user-2b", workspace=tmp_path / "seed")
    assert out["status"] == "delivered", out.get("metrics")


def test_a_user_task_lands_in_the_owner_ledger_only(tmp_path):
    agent = build("cancer")
    led = Ledgers("cancer")
    run_user_task(agent, benchmark_for("cancer"), client=Sim(tmp_path / "run"),
                  store=_store(tmp_path), task_id="user-3",
                  workspace=tmp_path / "seed", ledgers=led)
    assert len(led.of(OWNER_SET)) == 1
    assert led.of(SELF_DIRECTED) == [] and led.of(BENCHMARK) == []


# ------------------------------------------- 2. the autonomous function

def test_autonomous_work_is_refused_until_the_owner_turns_it_on(tmp_path):
    agent = build("drug-design")
    with pytest.raises(PermissionError):
        autonomous_round(agent, benchmark_for("drug-design"),
                         client_factory=lambda s: Sim(tmp_path / ("r%d" % s)),
                         workspace_root=tmp_path / "ws", seeds=(0,))


def test_a_measuring_round_runs_every_seed_and_records_every_seed(tmp_path):
    """An agent whose method has no knobs still has a night's work.

    drug-design declares no parameters, so its night measures rather than
    searches — and reproduction is the strongest single use the design claims
    for these agents. Every seed runs and every seed lands in the ledger."""
    agent = build("drug-design")
    agent.switch.owner_turn_on(Budget("drug-design", units=6.0), by="owner")
    led = Ledgers("drug-design")
    r = autonomous_round(agent, benchmark_for("drug-design"),
                         client_factory=lambda s: Sim(tmp_path / ("r%d" % s)),
                         workspace_root=tmp_path / "ws", seeds=(0, 1, 2),
                         cost_per_seed=0.5, ledgers=led)
    assert r.improvement is None, "nothing to compare against: no knobs"
    assert "measured rather than searched" in r.outcome["why"]
    assert len(led.of(BENCHMARK)) == 3, "one ledger row per seed"
    assert r.spent == pytest.approx(1.5)


def test_a_searching_round_reports_every_validation_seed(tmp_path):
    """And where there IS something to search, the claim carries every seed it
    was validated on — including any that went the wrong way."""
    agent = build("pill-camera")
    agent.switch.owner_turn_on(Budget("pill-camera", units=20.0), by="owner")
    r = autonomous_round(agent, benchmark_for("pill-camera"),
                         client_factory=lambda s: Sim(tmp_path / ("r%d" % s)),
                         workspace_root=tmp_path / "ws", seeds=tuple(range(6)),
                         cost_per_seed=0.05, rounds=1)
    assert r.search and r.search.get("searched")
    v = r.search.get("validation")
    if v is not None:
        assert len(v["seeds"]) >= 4, "a claim needs a validation set worth the name"
        assert len(v["candidate"]) == len(v["seeds"])
        if r.improvement is not None:
            for s in v["seeds"]:
                assert ("seed %d" % s) in r.improvement.report()


def test_the_owner_can_turn_it_off_mid_round(tmp_path):
    """'Users can also turn off this function' has to mean work already running
    stops, not merely that the next one will not start."""
    # `cancer` has parameters now, so this exercises the SEARCH path — which
    # had no switch check at all when it was written. The owner turning the
    # function off was honoured for a measuring agent and ignored for a
    # searching one, and this test is what noticed.
    agent = build("cancer")
    agent.switch.owner_turn_on(Budget("cancer", units=6.0), by="owner")
    seen = {"n": 0}

    def factory(s):
        seen["n"] += 1
        if seen["n"] == 2:
            agent.switch.owner_turn_off()
        return Sim(tmp_path / ("r%d" % s))

    r = autonomous_round(agent, benchmark_for("cancer"), client_factory=factory,
                         workspace_root=tmp_path / "ws", seeds=(0, 1, 2, 3),
                         cost_per_seed=0.5)
    assert "turned it off" in r.stopped
    assert r.spent < 2.0, "it stopped part-way, it did not finish the set"


def test_the_budget_stops_the_loop_and_does_not_ask(tmp_path):
    """A search costs many runs, and the budget ends it mid-flight.

    Sized so the search genuinely starts and then cannot afford its next batch —
    an earlier version gave too few seeds for a validation set, so the search
    declined before spending anything and the budget was never reached."""
    agent = build("pill-camera")
    agent.switch.owner_turn_on(Budget("pill-camera", units=0.2), by="owner")
    r = autonomous_round(agent, benchmark_for("pill-camera"),
                         client_factory=lambda s: Sim(tmp_path / ("r%d" % s)),
                         workspace_root=tmp_path / "ws", seeds=tuple(range(6)),
                         cost_per_seed=0.5, rounds=1)
    assert r.stopped, "the budget should have ended it"
    assert "stops here" in r.stopped or "stops rather than asking" in r.stopped
    assert agent.switch.budget.remaining() >= 0.0


def test_an_exhausted_budget_ends_the_loop(tmp_path):
    agent = build("cancer")
    agent.switch.owner_turn_on(Budget("cancer", units=1.0), by="owner")
    rounds = autonomous_loop(agent, benchmark_for("cancer"),
                             client_factory=lambda s: Sim(tmp_path / ("x%d" % s)),
                             workspace_root=tmp_path / "ws", rounds=5,
                             seeds=(0, 1), cost_per_seed=0.5)
    assert any(r.stopped for r in rounds)
    assert agent.switch.budget.exhausted() or rounds[-1].stopped


def test_the_loop_works_the_field_map_and_does_not_repeat_itself(tmp_path):
    """The map is what makes the second night differ from the first."""
    agent = build("drug-design")
    agent.switch.owner_turn_on(Budget("drug-design", units=20.0), by="owner")
    before = agent.field_map.next_work().key
    autonomous_loop(agent, benchmark_for("drug-design"),
                    client_factory=lambda s: Sim(tmp_path / ("y%d" % s)),
                    workspace_root=tmp_path / "ws", rounds=2, seeds=(0,),
                    cost_per_seed=0.5)
    after = agent.field_map.next_work()
    assert after is None or after.key != before


# ------------------------------------------------------ the three ledgers

def test_the_three_ledgers_are_kept_apart(tmp_path):
    agent = build("cancer")
    agent.switch.owner_turn_on(Budget("cancer", units=8.0), by="owner")
    led = Ledgers("cancer")
    run_user_task(agent, benchmark_for("cancer"), client=Sim(tmp_path / "u"),
                  store=_store(tmp_path), task_id="u1",
                  workspace=tmp_path / "us", ledgers=led)
    autonomous_round(agent, benchmark_for("cancer"),
                     client_factory=lambda s: Sim(tmp_path / ("a%d" % s)),
                     workspace_root=tmp_path / "aw", seeds=(0, 1),
                     cost_per_seed=0.5, ledgers=led)
    # One owner-set task, one self-directed round, and one benchmark row per
    # run the round made. The count is not pinned: `cancer` measured two seeds
    # when it had no parameters and searches many more now that it has some,
    # and the property being tested is that the three stay APART, not how busy
    # the middle one was.
    assert len(led.of(OWNER_SET)) == 1
    assert len(led.of(SELF_DIRECTED)) == 1
    assert len(led.of(BENCHMARK)) >= 2
    assert all(r.get("seed") is not None for r in led.of(BENCHMARK)), \
        "a benchmark row records which seed produced it"
    assert "never summed" in led.report()


def test_there_is_no_single_number():
    led = Ledgers("imaging")
    with pytest.raises(NotImplementedError) as e:
        led.total()
    assert "pass its own exam" in str(e.value)
