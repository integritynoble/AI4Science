"""`L3` — how well-calibrated this worker is.

L4 answers *what has it proven*. This answers a different and harder question:
**when it says it will work, is it right?** A worker that succeeds 70% of the
time and says so is more useful than one that succeeds 90% of the time and
claims 100%, because only the first can be planned around.

Calibration needs a forecast, and a forecast has one property that makes it
evidence rather than narration:

  **It must be made BEFORE the outcome.** That is not a convention here, it is
  enforced: recording a forecast on a task that already has a verdict raises.
  A number written after the fact is a story about the past wearing the costume
  of a prediction, and it would score perfectly while meaning nothing. This is
  the same L7-is-not-admitted rule the competence module applies, moved earlier
  in time.

The other three refusals are inherited from `competence.py` deliberately:

  **Unmeasured is None, never zero.** A Brier score of 0.0 is *perfect*
  calibration. Returning it for "nothing forecast yet" would be the most
  flattering possible lie.

  **The score never travels alone.** A Brier number is meaningless without its
  sample size and a baseline: 0.25 is what you get by always saying 50%, and
  the base rate's own score is what a forecaster must beat to have added
  anything.

  **It may narrow, never widen.** Good calibration cannot buy an agent a
  skipped check.
"""
import json

import pytest

from ai4science.harness.agents.sarsi import (forecast as fc, registry as reg,
                                             task as tsk, worker as wk)


@pytest.fixture
def config(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path / "s"))
    root = tmp_path / "s"; root.mkdir(parents=True, exist_ok=True)
    p = reg.config_path(root)
    p.write_text(json.dumps(reg.default_config(owner_id="7007143162")))
    c = reg.load(p); c.ensure_dirs()
    return c


def _task(config, agent, goal="g"):
    return tsk.create(config, agent, wk.Directive(agent_id=agent.id, goal=goal))


def _forecast_then_judge(config, agent, p, state, *, n=1):
    for _ in range(n):
        t = _task(config, agent)
        fc.record(config, agent, t, p)
        t.verdict = {"state": state, "independent": True}
        tsk._save(agent, t)


# ── a forecast is made BEFORE the outcome, and that is enforced ───────

def test_a_forecast_is_recorded_on_the_task(config):
    a = config.agents["sarsi-worker"]
    t = _task(config, a)
    t = fc.record(config, a, t, 0.7, why="the plan is short and the tools exist")
    assert t.forecast and t.forecast["p"] == 0.7
    assert t.forecast["why"]


def test_forecasting_after_the_verdict_is_refused(config):
    """The rule the whole module rests on. A number written after the outcome
    would score perfectly and mean nothing."""
    a = config.agents["sarsi-worker"]
    t = _task(config, a)
    t.verdict = {"state": "PASS", "independent": True}
    tsk._save(a, t)
    with pytest.raises(fc.TooLate):
        fc.record(config, a, t, 0.9)


def test_and_the_refusal_says_why(config):
    a = config.agents["sarsi-worker"]
    t = _task(config, a)
    t.verdict = {"state": "PASS", "independent": True}
    tsk._save(a, t)
    with pytest.raises(fc.TooLate) as e:
        fc.record(config, a, t, 0.9)
    assert "already" in str(e.value).lower()


def test_a_forecast_outside_zero_to_one_is_refused(config):
    a = config.agents["sarsi-worker"]
    t = _task(config, a)
    for bad in (-0.1, 1.5, 2):
        with pytest.raises(ValueError):
            fc.record(config, a, t, bad)


def test_it_survives_a_round_trip(config):
    a = config.agents["sarsi-worker"]
    t = fc.record(config, a, _task(config, a), 0.6)
    again = [x for x in tsk.all_of(config, a) if x.id == t.id][0]
    assert again.forecast["p"] == 0.6


# ── unmeasured is None, never zero ────────────────────────────────────

def test_no_forecasts_means_no_calibration(config):
    """0.0 is PERFECT calibration. Returning it here would be the most
    flattering possible lie."""
    a = config.agents["sarsi-worker"]
    assert fc.calibration(config, a) is None


def test_a_forecast_with_no_verdict_is_not_yet_evidence(config):
    a = config.agents["sarsi-worker"]
    fc.record(config, a, _task(config, a), 0.8)
    assert fc.calibration(config, a) is None


def test_a_verdict_with_no_forecast_is_not_evidence_either(config):
    """L4 counts it; L3 cannot, because nothing was predicted."""
    a = config.agents["sarsi-worker"]
    t = _task(config, a)
    t.verdict = {"state": "PASS", "independent": True}
    tsk._save(a, t)
    assert fc.calibration(config, a) is None


# ── the score never travels alone ─────────────────────────────────────

def test_a_confident_correct_forecaster_scores_well(config):
    a = config.agents["sarsi-worker"]
    _forecast_then_judge(config, a, 0.9, "PASS", n=4)
    cal = fc.calibration(config, a)
    assert cal["brier"] == pytest.approx(0.01, abs=1e-6), cal
    assert cal["n"] == 4


def test_a_confident_WRONG_forecaster_scores_badly(config):
    """The case that matters: high confidence, wrong every time."""
    a = config.agents["sarsi-worker"]
    _forecast_then_judge(config, a, 0.9, "FAIL", n=4)
    cal = fc.calibration(config, a)
    assert cal["brier"] == pytest.approx(0.81, abs=1e-6), cal


def test_the_baseline_is_published_with_it(config):
    """0.25 is what always-saying-50% scores. A Brier number without that is
    not interpretable."""
    a = config.agents["sarsi-worker"]
    _forecast_then_judge(config, a, 0.9, "PASS", n=3)
    cal = fc.calibration(config, a)
    assert cal["uninformed"] == pytest.approx(0.25)
    assert "beats_uninformed" in cal


def test_and_it_says_when_the_forecaster_is_worse_than_a_coin(config):
    a = config.agents["sarsi-worker"]
    _forecast_then_judge(config, a, 0.9, "FAIL", n=3)
    cal = fc.calibration(config, a)
    assert cal["beats_uninformed"] is False, cal


def test_the_sample_travels_with_it(config):
    a = config.agents["sarsi-worker"]
    _forecast_then_judge(config, a, 0.5, "PASS", n=2)
    assert fc.calibration(config, a)["n"] == 2


# ── over- and under-confidence are different faults ──────────────────

def test_overconfidence_is_named(config):
    """Predicting 90% and succeeding 25% of the time is a specific, nameable
    fault, and it is the one that gets an owner hurt."""
    a = config.agents["sarsi-worker"]
    _forecast_then_judge(config, a, 0.9, "PASS", n=1)
    _forecast_then_judge(config, a, 0.9, "FAIL", n=3)
    cal = fc.calibration(config, a)
    assert cal["bias"] < 0, cal          # predicted far above observed
    assert "overconfident" in fc.render(cal).lower()


def test_underconfidence_is_named_too(config):
    a = config.agents["sarsi-worker"]
    _forecast_then_judge(config, a, 0.2, "PASS", n=4)
    cal = fc.calibration(config, a)
    assert cal["bias"] > 0, cal
    assert "underconfident" in fc.render(cal).lower()


# ── it may narrow, never widen ────────────────────────────────────────

def test_may_widen_always_refuses(config):
    a = config.agents["sarsi-worker"]
    _forecast_then_judge(config, a, 0.95, "PASS", n=50)
    assert fc.may_widen(config, a) is False


# ── and it says something when there is nothing to say ────────────────

def test_the_unmeasured_case_gets_a_sentence(config):
    assert "no forecast" in fc.render(None).lower()


# ── the self-model carries it as L3 ───────────────────────────────────

def test_the_worker_can_say_how_calibrated_it_is(config):
    from ai4science.harness.agents.sarsi import selfaware
    a = config.agents["sarsi-worker"]
    _forecast_then_judge(config, a, 0.8, "PASS", n=3)
    by = {c["field"]: c for c in selfaware.claims(config, a)}
    assert "calibration" in by, sorted(by)
    assert by["calibration"]["authority_level"] == 3, by["calibration"]


def test_and_admits_when_it_cannot(config):
    from ai4science.harness.agents.sarsi import selfaware
    a = config.agents["sarsi-worker"]
    by = {c["field"]: c for c in selfaware.claims(config, a)}
    assert "no forecast" in str(by["calibration"]["value"]).lower()


# ── the refusal must be visible to a script, not just a reader ────────

def test_the_cli_refuses_with_a_nonzero_exit(config, monkeypatch):
    """A refusal that exits 0 is one an automation never notices. Checked as a
    real process, because `$?` after a pipeline is the pipeline's — a trap this
    session fell into twice while verifying other work.

    Uses the `config` fixture's isolated state dir for BOTH the test process and
    the subprocess. My first version set `SARSI_STATE_DIR` only for the child,
    so the parent read the developer's real registry and asserted against a
    live task. Read-only, and still exactly the isolation failure that makes a
    test lie about what it exercised.
    """
    import os, subprocess, sys
    state = os.environ["SARSI_STATE_DIR"]          # set by the fixture
    env = {**os.environ, "SARSI_STATE_DIR": state}
    run = lambda *a: subprocess.run([sys.executable, "-m", "ai4science.cli",
                                     "sarsi", *a], capture_output=True,
                                    text=True, env=env, timeout=120)

    a = config.agents["sarsi-worker"]
    t = _task(config, a)

    bad = run("forecast", "sarsi-worker", t.id, "5")
    assert bad.returncode != 0, bad.stdout

    t.verdict = {"state": "PASS", "independent": True}
    tsk._save(a, t)
    late = run("forecast", "sarsi-worker", t.id, "0.99")
    assert late.returncode != 0, late.stdout
    assert "already been judged" in (late.stdout + late.stderr), late.stdout
