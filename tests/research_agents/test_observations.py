"""The gap between a benchmark that measured something and a report that says so.

`SelfModel.observe()` was the only way a number entered a self-model, and
`build()` returned a fresh agent per process, so the drug-design benchmark could
produce a real EF number and `selfmodel-report` would still print seven
`unmeasured` rows minutes later. These tests are about the floor under that —
and, mostly, about what does NOT go through it: a run the judge refused, a
search candidate, a row whose evidence somebody typed.

The run inputs are fabricated. The screening corpus is not on this machine and
only one seed is cached, so running the real benchmark here would test whether
DUD-E was downloaded rather than whether an observation survives a process.
"""
from __future__ import annotations

import json

import pytest

from ai4science.harness.agents.research_agents import Unobserved, build, observations
from ai4science.harness.agents.research_agents.runners import BENCHMARKS
from ai4science.harness.agents.research_agents.runners.common import (
    DomainBenchmark, Observed, Parameter, Verdict,
)

#: What a screening run's scorer returns, cut down to what these tests read.
#: The two EF figures differ on purpose: filing the overall number under a
#: dimension whose measurement says "on held-out targets" is the mistake the
#: mapping exists to avoid, and identical values would hide it.
METRICS = {"ef_at_1pct": 5.5,
           "ef_at_1pct_heldout_targets": 3.25,
           "auc_unseen": 0.86,
           "active_fraction": 0.015}

NOTE = ("EF@1% on the targets held out entirely; BEDROC is not computed by "
        "this benchmark")


def _bench(**kw) -> DomainBenchmark:
    """A screening-shaped benchmark that needs no corpus to describe itself."""
    args = dict(
        agent="drug-design",
        goal="a stand-in for the screening run",
        package="screening",
        deliverables=("results/scores.npy",),
        answer_key=("data/labels.npy",),
        score=lambda seed_ws, run_ws: dict(METRICS),
        judge=lambda m: Verdict(True, ("stub",), m),
        corpus="dude",
        parameters=(Parameter("top_k", 1, 15, 1, integer=True),),
        observes=(Observed("enrichment", "ef_at_1pct_heldout_targets",
                           note=NOTE),),
    )
    args.update(kw)
    return DomainBenchmark(**args)


def _passed(metrics=None) -> Verdict:
    return Verdict(True, ("EF@1% 3.25 on targets held out entirely",),
                   dict(metrics or METRICS))


def _failed() -> Verdict:
    return Verdict(False, ("EF@1% 66.79 against a ceiling of 66.79 — 0.00% "
                           "headroom. This number cannot rank one method above "
                           "another",), dict(METRICS))


def _record(bench=None, *, verdict=None, params=None, seed=7, metrics=None):
    b = bench or _bench()
    m = dict(metrics or METRICS)
    return observations.record_run(
        b, seed=seed, metrics=m, verdict=verdict or _passed(m),
        params=b.defaults() if params is None else params,
        run_workspace="/tmp/run-ws")


# --------------------------------------------------------------- the happy path

def test_a_passing_default_run_survives_the_process_that_made_it(monkeypatch, tmp_path):
    """The whole point: a number measured in one process is in the self-model
    the next process builds."""
    monkeypatch.setenv("AI4SCIENCE_SELFMODEL_STORE", str(tmp_path))
    rows = _record()
    assert [r["dimension"] for r in rows] == ["enrichment"]
    assert observations.path_for("drug-design").exists()

    sm = build("drug-design").self_model
    assert sm.measured("enrichment")
    assert sm.value("enrichment") == pytest.approx(3.25)


def test_the_evidence_is_composed_from_the_run_not_from_a_caller(monkeypatch, tmp_path):
    """`observe()` refuses a value with no evidence. A caller-supplied sentence
    would pass that check while defeating it, so every clause here is read off
    the run and this test names them one by one."""
    monkeypatch.setenv("AI4SCIENCE_SELFMODEL_STORE", str(tmp_path))
    ev = _record(seed=7)[0]["evidence"]
    assert "ef_at_1pct_heldout_targets" in ev and "3.25" in ev
    assert "seed 7" in ev
    assert "drug-design" in ev and "screening" in ev
    assert "judge" in ev
    assert "real data:" in ev                       # bench.provenance()
    assert "outside the sandbox" in ev and "withheld answer key" in ev
    assert NOTE in ev


def test_the_dimension_records_the_held_out_number(monkeypatch, tmp_path):
    """The dimension's declared measurement says *on held-out targets*, and the
    overall EF is a different, higher number. One standing in for the other is
    the failure selfmodel.py exists to prevent."""
    monkeypatch.setenv("AI4SCIENCE_SELFMODEL_STORE", str(tmp_path))
    row = _record()[0]
    assert row["metric"] == "ef_at_1pct_heldout_targets"
    assert row["value"] == pytest.approx(METRICS["ef_at_1pct_heldout_targets"])
    assert row["value"] != pytest.approx(METRICS["ef_at_1pct"])


# ------------------------------------------------------------ what is refused

def test_a_run_the_judge_refused_is_not_a_measurement(monkeypatch, tmp_path):
    """The screening judge refuses a saturated EF@1% because it "cannot rank one
    method above another". Recording it as this agent's competence would launder
    exactly the number the benchmark just said means nothing."""
    monkeypatch.setenv("AI4SCIENCE_SELFMODEL_STORE", str(tmp_path))
    assert _record(verdict=_failed()) == []
    assert not observations.path_for("drug-design").exists()
    assert not build("drug-design").self_model.measured("enrichment")


def test_a_search_candidate_is_not_a_measurement(monkeypatch, tmp_path):
    """Non-default params are a proposal about a method. A night of them
    last-written into the self-model would report whichever variant ran last."""
    monkeypatch.setenv("AI4SCIENCE_SELFMODEL_STORE", str(tmp_path))
    assert _record(params={"top_k": 5.0}) == []
    assert not observations.path_for("drug-design").exists()
    assert not build("drug-design").self_model.measured("enrichment")


def test_a_benchmark_that_declares_nothing_records_nothing(monkeypatch, tmp_path):
    """Silence means the benchmark has not said which dimension its metrics
    measure — not that something should be guessed."""
    monkeypatch.setenv("AI4SCIENCE_SELFMODEL_STORE", str(tmp_path))
    assert _record(_bench(observes=())) == []
    assert not observations.path_for("drug-design").exists()


def test_a_pair_naming_a_metric_the_scorer_never_produced_is_loud(monkeypatch, tmp_path):
    """A row that quietly never appears is the failure class this system
    refuses, so the wiring mistake raises at its own source."""
    monkeypatch.setenv("AI4SCIENCE_SELFMODEL_STORE", str(tmp_path))
    bad = _bench(observes=(Observed("enrichment", "bedroc"),))
    with pytest.raises(ValueError) as e:
        _record(bad)
    assert "bedroc" in str(e.value)
    assert not observations.path_for("drug-design").exists()


# --------------------------------------------------------------- replay itself

def test_a_row_with_blank_evidence_cannot_be_replayed(monkeypatch, tmp_path):
    """The refusal has to bite on the replay path too, and the failure has to be
    loud: a stored row that cannot be applied means a number a run produced
    would vanish while the report went on saying `unmeasured`."""
    monkeypatch.setenv("AI4SCIENCE_SELFMODEL_STORE", str(tmp_path))
    p = observations.path_for("drug-design")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"agent": "drug-design", "dimension": "enrichment",
                             "metric": "ef_at_1pct_heldout_targets",
                             "value": 3.25, "evidence": "  ", "at": 1.0}) + "\n")
    with pytest.raises(ValueError) as e:
        build("drug-design")
    assert str(p) in str(e.value)
    assert "line 1" in str(e.value)


def test_a_row_naming_an_unknown_dimension_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("AI4SCIENCE_SELFMODEL_STORE", str(tmp_path))
    p = observations.path_for("drug-design")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"dimension": "bedroc", "value": 1.0,
                             "evidence": "a run", "at": 1.0}) + "\n")
    with pytest.raises(ValueError) as e:
        build("drug-design")
    assert "bedroc" in str(e.value) and str(p) in str(e.value)


def test_no_store_is_not_an_error(monkeypatch, tmp_path):
    monkeypatch.setenv("AI4SCIENCE_SELFMODEL_STORE", str(tmp_path / "nothing-here"))
    assert observations.replay(build("drug-design").self_model) == 0


def test_replay_applies_rows_in_file_order(monkeypatch, tmp_path):
    """No arbitration — later overwrites earlier, because that is what
    `observe()` does. Picking the highest would be this module computing an
    aggregate the judge never computed."""
    monkeypatch.setenv("AI4SCIENCE_SELFMODEL_STORE", str(tmp_path))
    _record(seed=1, metrics={**METRICS, "ef_at_1pct_heldout_targets": 4.0})
    _record(seed=2, metrics={**METRICS, "ef_at_1pct_heldout_targets": 2.0})
    rows = [json.loads(l) for l in
            observations.path_for("drug-design").read_text().splitlines()]
    assert [r["seed"] for r in rows] == [1, 2]

    sm = build("drug-design").self_model
    # 2.0, not 4.0: the last row wins because that is what `observe()` does.
    assert sm.value("enrichment") == pytest.approx(2.0)


# ------------------------------------------- what replay must leave untouched

def test_the_other_dimensions_are_still_unmeasured(monkeypatch, tmp_path):
    """One measured dimension does not make the rest zero. A `0.0` in a table
    reads as *measured and bad* rather than *never run*, and those are opposite
    facts."""
    monkeypatch.setenv("AI4SCIENCE_SELFMODEL_STORE", str(tmp_path))
    _record()
    sm = build("drug-design").self_model
    assert sm.unmeasured and len(sm.unmeasured) == len(sm.dimensions) - 1

    report = sm.report()
    assert "limits:" in report
    lines = report.splitlines()
    for key in sm.unmeasured:
        title = sm.dimensions[key].title
        row = [l for l in lines if l.strip().startswith(title)]
        assert row, title
        assert "unmeasured" in row[0], title
        assert "0.0" not in row[0], title
        with pytest.raises(Unobserved):
            sm.value(key)


def test_reading_the_store_still_confers_no_authority(monkeypatch, tmp_path):
    """`replay` returns a count. A count is not a permission."""
    monkeypatch.setenv("AI4SCIENCE_SELFMODEL_STORE", str(tmp_path))
    _record()
    a = build("drug-design")
    assert observations.replay(a.self_model) == 1
    with pytest.raises(NotImplementedError):
        a.self_model.authority()


# ------------------------------------------------------------- the declarations

def test_every_declared_pair_names_a_real_dimension(monkeypatch, tmp_path):
    """The mapping is the benchmark's to declare, which means nothing checks it
    at build time. This is the check."""
    monkeypatch.setenv("AI4SCIENCE_SELFMODEL_STORE", str(tmp_path))
    declared = 0
    for name, bench in BENCHMARKS.items():
        for ob in bench.observes:
            declared += 1
            sm = build(bench.agent).self_model
            assert ob.dimension in sm.dimensions, (name, ob.dimension)
    assert declared, "no benchmark declares an observation — test is vacuous"


def test_only_drug_design_is_wired(monkeypatch, tmp_path):
    """A mapping for a benchmark nobody has run is a claim, not a wiring. When
    the second one is run and wired, this test is the place to say so."""
    monkeypatch.setenv("AI4SCIENCE_SELFMODEL_STORE", str(tmp_path))
    wired = sorted(n for n, b in BENCHMARKS.items() if b.observes)
    assert wired == ["drug-design"]
