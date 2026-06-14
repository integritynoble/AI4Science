"""Contribution-improvement measurement: eval-delta -> quality multiplier."""
import re

import pytest

from ai4science.harness.contribution_eval import (
    ContributionCandidate, EvalTask, ContributionScore,
    evaluate_contribution, quality_from_improvement,
    contains_grader, threshold_grader, QUALITY_GAIN,
)


def _cand(kind="tool"):
    return ContributionCandidate(contribution_id="c1", agent_name="computational-imaging",
                                 kind=kind, title="t")


def test_quality_from_improvement_neutral_and_gain():
    assert quality_from_improvement(0.0) == 1.0
    assert quality_from_improvement(0.25) == pytest.approx(1.0 + QUALITY_GAIN * 0.25)
    # negative improvement never penalizes below baseline 1.0
    assert quality_from_improvement(-0.5) == 1.0


def test_contains_grader():
    g = contains_grader("psnr", "done")
    assert g("PSNR computed, DONE") == 1.0
    assert g("only psnr") == 0.0
    g_any = contains_grader("a", "b", all_required=False)
    assert g_any("has b") == 1.0


def test_threshold_grader_ramp():
    extract = lambda t: float(m.group(1)) if (m := re.search(r"psnr=([\d.]+)", t)) else None
    g = threshold_grader(extract, target=30.0)
    assert g("psnr=30.0") == 1.0
    assert g("psnr=15.0") == pytest.approx(0.5)
    assert g("no metric") == 0.0
    g_low = threshold_grader(extract, target=10.0, higher_is_better=False)
    assert g_low("psnr=10.0") == 1.0
    assert g_low("psnr=20.0") == pytest.approx(0.5)


def test_evaluate_contribution_measures_lift():
    # candidate variant solves the task; baseline does not.
    tasks = [EvalTask(task_id="t1", prompt="recon", grader=contains_grader("solved"))]

    def run(task, variant):
        return "solved it" if variant == "candidate" else "could not"

    score = evaluate_contribution(_cand(), tasks, run)
    assert score.baseline == 0.0 and score.candidate == 1.0
    assert score.improvement == 1.0
    assert score.quality == pytest.approx(1.0 + QUALITY_GAIN)
    assert score.per_task[0].delta == 1.0


def test_evaluate_no_improvement_is_neutral():
    tasks = [EvalTask(task_id="t1", prompt="x", grader=contains_grader("ok"))]
    score = evaluate_contribution(_cand(), tasks, lambda t, v: "ok always")
    assert score.improvement == 0.0 and score.quality == 1.0
    assert score.raw_improvement == 0.0


def test_evaluate_regression_clamped_but_recorded():
    tasks = [EvalTask(task_id="t1", prompt="x", grader=contains_grader("passed"))]

    def run(task, variant):  # candidate is WORSE
        return "passed" if variant == "baseline" else "failed"

    score = evaluate_contribution(_cand(), tasks, run)
    assert score.raw_improvement < 0
    assert score.improvement == 0.0 and score.quality == 1.0


def test_weighted_mean_across_tasks():
    tasks = [
        EvalTask(task_id="easy", prompt="", grader=contains_grader("good"), weight=1.0),
        EvalTask(task_id="hard", prompt="", grader=contains_grader("good"), weight=3.0),
    ]

    def run(task, variant):
        if variant == "baseline":
            return "bad"
        # candidate fixes only the heavy task
        return "good" if task.task_id == "hard" else "bad"

    score = evaluate_contribution(_cand(), tasks, run)
    # weighted candidate mean = (0*1 + 1*3)/4 = 0.75
    assert score.candidate == pytest.approx(0.75)
    assert score.improvement == pytest.approx(0.75)


def test_flaky_task_noted_not_fatal():
    def boom(_):
        raise RuntimeError("LLM down")

    tasks = [EvalTask(task_id="t1", prompt="", grader=contains_grader("ok"))]
    score = evaluate_contribution(_cand(), tasks, lambda t, v: (_ for _ in ()).throw(RuntimeError("x")))
    assert score.quality == 1.0 and score.notes and "eval error" in score.notes[0]


def test_requires_tasks():
    with pytest.raises(ValueError):
        evaluate_contribution(_cand(), [], lambda t, v: "")


def test_score_as_dict_roundtrips():
    tasks = [EvalTask(task_id="t1", prompt="", grader=contains_grader("solved"))]
    d = evaluate_contribution(_cand(), tasks, lambda t, v: "solved" if v == "candidate" else "no").as_dict()
    assert d["contribution_id"] == "c1" and d["kind"] == "tool"
    assert d["quality"] == pytest.approx(1.0 + QUALITY_GAIN)
    assert d["per_task"][0]["delta"] == 1.0
