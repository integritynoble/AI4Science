"""The delegation harness.

The claim under test is not "the agent is good". It is narrower and checkable:

    Holding the solver fixed, wrapping it in this loop changes what comes back,
    and the change comes from making the class checkable and the work
    restartable rather than from capability.

So the tests that matter are the two directions. A capable-but-careless solver
must end up **accepted** where bare it does not. An executor that cannot succeed
must end up **escalated**, never reported as done -- that second one is the
property a retry loop does not have and the one delegation actually turns on.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from ai4science.harness.agents.delegation import (
    CriterionRegister, DelegationAgent, RegisterViolation, accept, read_task)
from ai4science.harness.agents.delegation.bench_solver import (
    COVERED, CarelessSolver, StubbornSolver)
from ai4science.harness.agents.delegation.compress import Library
from ai4science.harness.agents.delegation.escalate import (
    cheapest_question, rather_ask_than_guess)
from ai4science.harness.agents.delegation.executor import (
    Competence, CompetenceModel, FailureKind, SolverExecutor, classify_failure)
from ai4science.harness.agents.delegation.reversible import (
    Reversibility, Step, UndoLedger)
from ai4science.harness.agents.delegation.router import Router
from ai4science.harness.agents.dli_bench.tasks import GENERATORS

SEEDS = (0, 1, 2)


def _loss(spec):
    return {"value": spec.loss.value, "c_detect": spec.loss.c_detect,
            "c_undo": spec.loss.c_undo, "c_residual": spec.loss.c_residual}


# ------------------------------------------------- the class, read in advance

def test_an_irreversible_class_demands_certainty_and_so_is_refused():
    c = read_task("t", "Send the summary to the customer by email")
    assert c.p_star == 1.0
    ok, why = c.autonomy_justified(0.99)
    assert not ok and "unbounded residual" in why


def test_p_star_comes_from_the_class_not_from_a_convention():
    c = read_task("t", "Clean raw.csv to the rules in RULES.md",
                  declared_loss={"value": 1.0, "c_detect": 30.0, "c_undo": 0.0,
                                 "c_residual": 0.0})
    assert abs(c.p_star - 30 / 31) < 1e-6
    assert not c.autonomy_justified(0.90)[0]      # 0.90 is not "usually fine" here
    assert c.autonomy_justified(0.98)[0]


def test_a_workspace_under_version_control_reads_as_reversible():
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        (ws / ".git").mkdir()
        assert read_task("t", "edit the parser", ws).reversibility.value == 4


# ------------------------------------------- acceptance, made structural

def test_a_criterion_cannot_be_registered_about_something_that_already_exists():
    """The check that stops acceptance being written around a result."""
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td) / "ws"
        ws.mkdir()
        (ws / "out.json").write_text("[]", encoding="utf-8")
        reg = CriterionRegister(Path(td) / "c.jsonl", workspace=ws)
        with pytest.raises(RegisterViolation) as e:
            reg.register("late", "pycode:pass", "anything", about="out.json")
        assert "already exists" in str(e.value)


def test_the_register_is_write_once_and_sealed_when_work_starts():
    with tempfile.TemporaryDirectory() as td:
        reg = CriterionRegister(Path(td) / "c.jsonl")
        reg.register("a", "pycode:pass", "covers a")
        with pytest.raises(RegisterViolation):
            reg.register("a", "pycode:pass", "covers a again")
        reg.seal()
        with pytest.raises(RegisterViolation) as e:
            reg.register("b", "pycode:pass", "covers b")
        assert "sealed" in str(e.value)


def test_a_criterion_must_say_what_it_misses():
    with tempfile.TemporaryDirectory() as td:
        reg = CriterionRegister(Path(td) / "c.jsonl")
        with pytest.raises(RegisterViolation):
            reg.register("a", "pycode:pass", "   ")


def test_editing_a_registered_criterion_breaks_the_chain():
    """File permissions can be undone by the same user. A hash cannot."""
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "c.jsonl"
        reg = CriterionRegister(path)
        reg.register("a", "pycode:assert True", "covers a")
        reg.register("b", "pycode:assert True", "covers b")
        assert reg.verify_chain()[0]
        rows = [json.loads(l) for l in path.read_text().splitlines()]
        rows[0]["check"] = "pycode:pass  # loosened after the fact"
        path.write_text("\n".join(json.dumps(r, sort_keys=True) for r in rows) + "\n")
        ok, why = CriterionRegister(path).verify_chain()
        assert not ok and "edited" in why


def test_a_broken_chain_is_not_accepted_however_well_the_checks_run():
    with tempfile.TemporaryDirectory() as td:
        path, ws = Path(td) / "c.jsonl", Path(td) / "ws"
        ws.mkdir()
        reg = CriterionRegister(path)
        reg.register("always", "pycode:pass", "nothing at all")
        rows = [json.loads(l) for l in path.read_text().splitlines()]
        rows[0]["prev_hash"] = "spliced"
        path.write_text(json.dumps(rows[0], sort_keys=True) + "\n")
        acc = accept(CriterionRegister(path), ws)
        assert not acc.accepted and not acc.chain_ok


def test_no_criterion_is_not_a_pass():
    """An unaccepted result is not a completed task."""
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td) / "ws"
        ws.mkdir()
        acc = accept(CriterionRegister(Path(td) / "c.jsonl"), ws)
        assert not acc.accepted
        assert "nothing accepts this" in acc.chain_note


def test_the_acceptor_runs_in_a_copy_so_a_check_cannot_alter_the_result():
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td) / "ws"
        ws.mkdir()
        (ws / "answer.txt").write_text("original", encoding="utf-8")
        reg = CriterionRegister(Path(td) / "c.jsonl")
        reg.register("rewrites", "pycode:open('answer.txt','w').write('tampered')",
                     "a check that tries to change the deliverable")
        accept(reg, ws)
        assert (ws / "answer.txt").read_text() == "original"


# --------------------------------------------------------- reversibility

def test_an_irreversible_step_does_not_run_unattended():
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td) / "ws"
        ws.mkdir()
        led = UndoLedger(ws, Path(td) / "snaps")
        ok, why = led.gate(Step("send the email", Reversibility.NONE))
        assert not ok and "cannot be undone" in why
        ok2, _ = led.gate(Step("send the email", Reversibility.NONE),
                          authorisation="owner said go")
        assert ok2


def test_a_snapshot_actually_restores():
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td) / "ws"
        ws.mkdir()
        (ws / "a.txt").write_text("before", encoding="utf-8")
        led = UndoLedger(ws, Path(td) / "snaps")
        sid = led.snapshot()
        (ws / "a.txt").write_text("after", encoding="utf-8")
        (ws / "junk.txt").write_text("x", encoding="utf-8")
        led.restore(sid)
        assert (ws / "a.txt").read_text() == "before"
        assert not (ws / "junk.txt").exists()


# ------------------------------------------------------------- escalation

def test_the_shallowest_question_that_unblocks_is_the_one_asked():
    e = cheapest_question(missing_fact="what is the account id",
                          needs_permission="may I write to prod",
                          stuck_on="I cannot work out the approach")
    assert e.cid == 0        # a permission costs the level nothing
    e2 = cheapest_question(missing_fact="what is the account id",
                           stuck_on="I cannot work out the approach")
    assert e2.cid == 1       # a fact, not a strategy
    assert cheapest_question() is None   # nothing missing, nothing to ask


def test_asking_beats_guessing_exactly_when_the_arithmetic_says_so():
    ask, _ = rather_ask_than_guess(confidence=0.8, p_star=0.97, rho=30.0)
    assert ask
    ask2, _ = rather_ask_than_guess(confidence=0.8, p_star=0.5, rho=1.0)
    assert not ask2


# ------------------------------------------------- competence and routing

def test_competence_carries_its_evidence_count():
    c = Competence("x", "cls")
    assert c.evidence == 0
    for _ in range(8):
        c.observe(True)
    assert c.mean > 0.8 and c.evidence == 8
    assert c.lower() < c.mean          # pessimism, so one success cannot certify


def test_the_second_failure_of_one_executor_is_capability_not_bad_luck():
    class Acc:
        chain_ok = True
        results = [("c", False, "assertion failed")]
    assert classify_failure(Acc(), [], 1) is FailureKind.EXECUTION
    assert classify_failure(Acc(), [], 2) is FailureKind.CAPABILITY


def test_an_execution_failure_retries_the_same_executor():
    """The bug this pins: re-scoring on every failure silently swapped
    executors, so each kept restarting from its first attempt."""
    ex = [SolverExecutor("a", CarelessSolver("t2.pipeline")),
          SolverExecutor("b", CarelessSolver("t2.pipeline"))]
    r = Router(ex, CompetenceModel())
    c = read_task("t", "do the thing")
    nxt = r.next_after_failure(FailureKind.EXECUTION, c, "cls", [], current=ex[0])
    assert nxt.executor is ex[0]


def test_a_capability_failure_moves_the_work_elsewhere():
    ex = [SolverExecutor("a", CarelessSolver("t2.pipeline")),
          SolverExecutor("b", CarelessSolver("t2.pipeline"))]
    r = Router(ex, CompetenceModel())
    c = read_task("t", "do the thing")
    nxt = r.next_after_failure(FailureKind.CAPABILITY, c, "cls", ["a"], current=ex[0])
    assert nxt.executor is not None and nxt.executor.name == "b"


def test_a_specification_failure_does_not_re_run_anything():
    r = Router([], CompetenceModel())
    nxt = r.next_after_failure(FailureKind.SPECIFICATION, read_task("t", "x"), "cls", [])
    assert nxt.executor is None and "contract is at fault" in nxt.because


def test_an_executor_is_not_benched_on_three_observations():
    """Benching early is the heroic-run error backwards, and an excluded
    executor never earns the evidence that would readmit it."""
    comp = CompetenceModel()
    for _ in range(3):
        comp.observe("a", "cls", False)
    ex = [SolverExecutor("a", CarelessSolver("t2.pipeline"))]
    c = read_task("t", "x", declared_loss={"value": 1.0, "c_detect": 1.0})
    assert Router(ex, comp).choose(c, "cls").executor is not None
    for _ in range(9):
        comp.observe("a", "cls", False)
    assert Router(ex, comp).choose(c, "cls").executor is None


# ------------------------------------------------------ the loop, end to end

@pytest.mark.parametrize("key", COVERED)
@pytest.mark.parametrize("seed", SEEDS)
def test_the_harness_turns_a_careless_solver_into_an_accepted_result(key, seed):
    gen = GENERATORS[key]
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)

        bare = td / "bare"
        gen.instantiate(bare, seed)
        CarelessSolver(key).attempt(None, bare / "work", ())
        assert not gen.verify(bare / "work", bare / "keyed").passed, (
            "%s: the careless pass was supposed to be wrong" % key)

        h = td / "h"
        spec = gen.instantiate(h, seed)
        out = DelegationAgent(CarelessSolver(key), max_attempts=3).run(
            spec.task_id, spec.prompt, h / "work", h / "store",
            declared_loss=_loss(spec), class_key=key)
        assert out.accepted, "%s: harness did not accept: %s" % (key, out.trace)
        assert gen.verify(h / "work", h / "keyed").passed, (
            "%s: the harness accepted something the benchmark rejects" % key)


@pytest.mark.parametrize("key", COVERED)
@pytest.mark.parametrize("seed", SEEDS)
def test_an_executor_that_cannot_succeed_is_never_reported_as_done(key, seed):
    """The property a retry loop does not have."""
    gen = GENERATORS[key]
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        spec = gen.instantiate(td, seed)
        out = DelegationAgent(StubbornSolver(key), max_attempts=3).run(
            spec.task_id, spec.prompt, td / "work", td / "store",
            declared_loss=_loss(spec), class_key=key)
        assert not out.accepted, "%s: accepted work that is wrong" % key
        assert not gen.verify(td / "work", td / "keyed").passed
        assert out.escalations or out.refused, (
            "%s: failed silently -- it must escalate, not just stop" % key)


@pytest.mark.parametrize("key", COVERED)
def test_routing_recovers_when_the_first_executor_cannot_do_it(key):
    gen = GENERATORS[key]
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        spec = gen.instantiate(td, 4)
        ex = [SolverExecutor("stubborn", StubbornSolver(key), cost=1.0),
              SolverExecutor("careless", CarelessSolver(key), cost=1.2)]
        out = DelegationAgent(executors=ex, competence=CompetenceModel(),
                              max_attempts=4).run(
            spec.task_id, spec.prompt, td / "work", td / "store",
            declared_loss=_loss(spec), class_key=key)
        assert out.accepted, "%s: routing did not recover: %s" % (key, out.trace)
        assert any(k == "capability" for _, k in out.route), (
            "%s: never diagnosed the stubborn executor" % key)


def test_the_competence_model_learns_only_from_verdicts():
    key = "t2.pipeline"
    gen = GENERATORS[key]
    comp = CompetenceModel()
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        spec = gen.instantiate(td, 0)
        ex = [SolverExecutor("stubborn", StubbornSolver(key))]
        DelegationAgent(executors=ex, competence=comp, max_attempts=3).run(
            spec.task_id, spec.prompt, td / "work", td / "store",
            declared_loss=_loss(spec), class_key=key)
    c = comp.get("stubborn", key)
    # It was confident every time; the model reflects the verdicts, not that.
    assert c.mean < 0.5 and c.evidence >= 2


def test_compression_leaves_a_check_behind_that_runs():
    key = "t0.csv_to_json"
    gen = GENERATORS[key]
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        lib = Library(td / "lib")
        spec = gen.instantiate(td / "a", 0)
        out = DelegationAgent(CarelessSolver(key), library=lib, max_attempts=3).run(
            spec.task_id, spec.prompt, td / "a" / "work", td / "a" / "store",
            declared_loss=_loss(spec), class_key=key)
        assert out.accepted and out.compression is not None
        artifact = lib.root / out.compression.artifact
        assert artifact.exists()
        # And a later run of the same class finds it already there.
        assert lib.known(key)
        spec2 = gen.instantiate(td / "b", 1)
        out2 = DelegationAgent(CarelessSolver(key), library=lib, max_attempts=3).run(
            spec2.task_id, spec2.prompt, td / "b" / "work", td / "b" / "store",
            declared_loss=_loss(spec2), class_key=key)
        assert any("library" in t for t in out2.trace), out2.trace
        assert out2.accepted
