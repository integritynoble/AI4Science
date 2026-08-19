"""The night driver: one authorised night, or a refusal that spends nothing.

`run_one_night` is the single call an owner's overnight schedule makes. It sits
in front of `autonomous_round` and enforces the two things the driver must never
get wrong: it runs exactly ONE named agent's night, and it runs it only when the
owner has supplied the authorisation — a `Budget` — at the call site. Everything
else is a refusal, and a refusal must cost nothing: no client, no workspace, no
round.

Tests 1, 2 and 3 need no corpus and PASS here. Tests 4 and 5 need a benchmark,
so they use `bench_or_skip` and SKIP on a machine with no corpora — which is the
honest outcome, not a hidden failure.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from ai4science.harness.agents.research_agents import Budget, build
from ai4science.harness.agents.research_agents.dual import Round
from ai4science.harness.agents.research_agents.fieldmap import SETTLED
from ai4science.harness.agents.research_agents.registry import NAMES
from ai4science.harness.agents.research_agents import night
from ai4science.harness.agents.research_agents.night import run_one_night
from .conftest import bench_or_skip as benchmark_for  # SKIPs, never fails, without a corpus


class Sim:
    """The same stub `test_dual_function` drives its rounds with."""

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


# --------------------------------------------- 1. an unknown name is refused

def test_an_unknown_agent_is_refused_and_the_message_lists_the_seven(tmp_path):
    """The driver takes a name; a name it does not know must be refused, and the
    refusal must say which seven names it does know — read from `NAMES`, so it
    cannot drift from the registry."""
    counter = {"n": 0}

    def factory(s):
        counter["n"] += 1
        return Sim(tmp_path / ("r%d" % s))

    assert len(NAMES) == 7, "the design set lists seven agents"
    with pytest.raises(KeyError) as e:
        run_one_night("not-a-real-agent", client_factory=factory,
                      workspace_root=tmp_path / "ws",
                      budget=Budget("x", units=5.0), seeds=(0,))
    msg = str(e.value)
    for name in NAMES:
        assert name in msg, "the refusal names %r" % name
    assert counter["n"] == 0, "an unknown name runs nothing"


# ------------------------------- 2. imaging has no runnable benchmark, refused

def test_imaging_is_refused_as_having_no_runnable_benchmark(tmp_path):
    """`imaging` is a real name in `NAMES`, but it is the generalist and has no
    domain runner — `benchmark_for('imaging')` raises. The night has nothing to
    run, so the driver refuses it by name and before it ever touches the switch."""
    counter = {"n": 0}

    def factory(s):
        counter["n"] += 1
        return Sim(tmp_path / ("r%d" % s))

    with pytest.raises(ValueError) as e:
        run_one_night("imaging", client_factory=factory,
                      workspace_root=tmp_path / "ws",
                      budget=Budget("imaging", units=6.0), seeds=(0,))
    msg = str(e.value)
    assert "imaging" in msg
    assert "generalist" in msg
    assert "benchmark" in msg, "the refusal says it has no runnable benchmark"
    assert counter["n"] == 0, "nothing ran"


# ------------------- 3. the switch is off (no budget): refused, and NOTHING ran

def test_no_budget_is_refused_and_nothing_ran(tmp_path):
    """The budget IS the switch here: `build()` hands back a fresh agent whose
    switch is off, and the only way on is the owner constructing a `Budget` and
    calling `owner_turn_on`. With no budget, the driver refuses — and the proof
    that nothing ran is a client factory that would have been called and was not.
    'It raised' is not enough; the counter is."""
    counter = {"n": 0}

    def factory(s):
        counter["n"] += 1
        return Sim(tmp_path / ("r%d" % s))

    with pytest.raises(PermissionError) as e:
        run_one_night("drug-design", client_factory=factory,
                      workspace_root=tmp_path / "ws", budget=None,
                      seeds=(0, 1, 2))
    assert counter["n"] == 0, "no client was ever constructed"
    assert not (tmp_path / "ws").exists(), "no workspace was ever created"
    msg = str(e.value)
    assert "--budget" in msg, "the refusal names the CLI action"
    assert "Budget" in msg and "owner_turn_on" in msg, \
        "the refusal names the owner action: construct a Budget, owner_turn_on"


def test_the_driver_exposes_main_and_does_not_run_on_import():
    """Importing the module must not run a night — the import at the top of this
    file already proves that; here we just assert the two entry points exist."""
    assert callable(run_one_night)
    assert callable(night.main)


def test_main_with_an_unknown_name_exits_nonzero_and_lists_the_seven(capsys):
    """A typo'd name must be heard as a name problem, not a budget problem: the
    CLI validates the name before it ever asks about --budget, so the refusal
    lists the seven names from `NAMES` (and never mentions a missing budget)."""
    rc = night.main(["no-such"])
    assert rc != 0
    err = capsys.readouterr().err
    assert len(NAMES) == 7
    for name in NAMES:
        assert name in err, "the refusal names %r" % name
    assert "--budget" not in err, "an unknown name is not a budget problem"


def test_main_imaging_with_budget_exits_nonzero_with_no_benchmark_refusal(capsys):
    """`imaging` is a real name but has no runnable benchmark, and that refusal
    comes before the budget check — so even *with* a --budget the CLI refuses it
    by name, saying it is the generalist with no runnable benchmark."""
    rc = night.main(["imaging", "--budget", "5"])
    assert rc != 0
    err = capsys.readouterr().err
    assert "imaging" in err
    assert "generalist" in err
    assert "benchmark" in err
    assert "--budget" not in err, "imaging is refused before the budget check"


def test_main_valid_name_without_budget_still_refuses_with_budget_message(capsys):
    """Regression: a valid, runnable name with no --budget must still hit the
    budget refusal and exit non-zero — reordering the name check must not weaken
    the switch."""
    rc = night.main(["drug-design"])
    assert rc != 0
    err = capsys.readouterr().err
    assert "--budget" in err
    assert "Budget" in err and "owner_turn_on" in err


def test_main_without_a_budget_exits_nonzero_and_prints_the_refusal():
    """Run as a person would: `python -m ...night <agent>` with no --budget must
    exit non-zero and print the refusal. Corpus-free and network-free: it refuses
    before it would build a client."""
    proc = subprocess.run(
        [sys.executable, "-m",
         "ai4science.harness.agents.research_agents.night", "drug-design"],
        capture_output=True, text=True)
    assert proc.returncode != 0, proc.stdout + proc.stderr
    combined = proc.stdout + proc.stderr
    assert "--budget" in combined, combined


# ----------------------------------- 4. a single round runs against the stub

def test_a_single_round_runs_against_the_stub_client(tmp_path):
    """With a budget supplied, the driver turns the switch on the documented way
    and runs exactly one `autonomous_round`, returning its `Round`."""
    benchmark_for("drug-design")  # SKIPs here — no corpus on this machine
    r = run_one_night("drug-design",
                      client_factory=lambda s: Sim(tmp_path / ("r%d" % s)),
                      workspace_root=tmp_path / "ws",
                      budget=Budget("drug-design", units=6.0),
                      seeds=(0, 1, 2), cost_per_seed=0.5)
    assert isinstance(r, Round)
    assert r.agent == "drug-design"
    assert r.spent > 0, "a night that ran spent something"


# ----------------- 5. a no-improvement night leaves the field map untouched

def test_a_no_improvement_night_leaves_the_field_map_exactly_as_it_was(tmp_path):
    """The night writes the map only from evidence about the CLAIM, and a
    parameter search supplies none — so after a night that found no improvement
    the claim keeps its status, its note, and its place as the open work. The
    driver must not change that: it runs the round, it does not settle claims."""
    agent = build("drug-design")
    benchmark_for("drug-design")  # SKIPs here — no corpus on this machine
    worked = agent.field_map.next_work()
    key, status_before, note_before = worked.key, worked.status, worked.note
    settled_before = agent.field_map.summary()[SETTLED]

    r = run_one_night("drug-design", agent=agent,
                      client_factory=lambda s: Sim(tmp_path / ("y%d" % s)),
                      workspace_root=tmp_path / "ws",
                      budget=Budget("drug-design", units=20.0),
                      seeds=(0,), cost_per_seed=0.5)
    assert isinstance(r, Round)
    assert not (r.improvement and r.improvement.survives()), \
        "a parameter sweep supplies no mechanism, so nothing here clears the bar"

    c = agent.field_map.claims[key]
    assert c.status == status_before != SETTLED, "unchecked stays unchecked"
    assert not c.trusted, "nothing reproduced it, so nothing may trust it"
    assert c.note == note_before
    assert "did NOT reproduce" not in c.note
    assert agent.field_map.summary()[SETTLED] == settled_before
    assert not any("did NOT reproduce" in x.note
                   for x in agent.field_map.claims.values())
    assert agent.field_map.next_work().key == key, \
        "the claim is still the open work it was before the night ran"
