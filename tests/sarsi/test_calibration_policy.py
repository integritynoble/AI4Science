"""Calibration that changes a decision, not just a number. [plan v3 §M3.2, §11.7]

A Brier score nobody acts on is telemetry. The plan is explicit that
calibration must either affect a decision or be admitted as observation only.

The decision it may affect is **supervision**, and only in one direction. A
worker measured promising more than it delivers is watched more closely; a
well-calibrated one is never watched less than the checks already require.
`may_widen()` exists to be called and always refuses.
"""
import pytest

from ai4science.harness.agents.sarsi import (forecast as fc, plan as pl,
                                             registry as reg, session as ses,
                                             task as tsk, worker)


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
    return config.agents["sarsi-worker"]


def _finished(config, agent, goal, p, passed):
    """A task that was forecast BEFORE it was judged, then judged."""
    d = worker.Directive(agent_id=agent.id, goal=goal)
    t = tsk.attach_plan(config, agent, tsk.create(config, agent, d),
                        pl.Plan(goal=goal,
                                phases=[pl.Phase(title="do it",
                                                 verified_when="it is done")]))
    t = fc.record(config, agent, t, p, why="test")
    t.verdict = {"state": "PASS" if passed else "FAIL", "why": "test"}
    tsk._save(agent, t)
    return t


def _overconfident(config, agent):
    _finished(config, agent, "task one", 0.95, False)
    _finished(config, agent, "task two", 0.95, False)


# ── the policy ───────────────────────────────────────────────────────────────

def test_with_nothing_scored_supervision_is_the_default(config, agent):
    sup = fc.supervision(config, agent)
    assert sup.level == "normal"
    assert not sup.require_deterministic
    assert "unmeasured" in sup.why or "not enough" in sup.why


def test_one_scored_forecast_is_not_a_direction(config, agent):
    _finished(config, agent, "task one", 0.95, False)
    sup = fc.supervision(config, agent)
    assert sup.level == "normal"
    assert sup.n == 1


def test_measured_overconfidence_tightens_supervision(config, agent):
    _overconfident(config, agent)
    sup = fc.supervision(config, agent)
    assert sup.level == "tighter"
    assert sup.require_deterministic
    assert sup.max_delegated_phases == 1
    assert "overconfident" in sup.why


def test_a_calibrated_worker_is_not_watched_less_than_the_checks_require(config, agent):
    _finished(config, agent, "task one", 0.9, True)
    _finished(config, agent, "task two", 0.9, True)
    sup = fc.supervision(config, agent)
    assert sup.level == "normal"
    assert not sup.require_deterministic     # good calibration buys no skip
    assert fc.may_widen(sup) is False


# ── it is causally active, which is the whole requirement ────────────────────

def test_tightened_supervision_stops_a_model_closing_an_unjudgeable_phase(
        config, agent):
    """The lever, exercised through the real path: a criterion no deterministic
    check can evaluate, and a verifier that would happily say PASS."""
    _overconfident(config, agent)
    d = worker.Directive(agent_id=agent.id, goal="ship the thing")
    t = tsk.attach_plan(config, agent, tsk.create(config, agent, d),
                        pl.Plan(goal="ship the thing",
                                phases=[pl.Phase(title="make it good",
                                                 verified_when="it feels right")]))

    def always_pass(**_kw):
        return {"state": "PASS", "why": "looks done to me"}

    out = ses._verify_phase(config, agent, t, verifier=always_pass,
                            evidence="I did it", engine="claude", index=0,
                            now=lambda: 1.0)
    assert out.verdict["state"] == "UNVERIFIED"
    assert out.verdict["engine"] == "supervision-policy"
    assert not tsk.phase_passed(out, 0)


def test_without_the_tightening_the_same_phase_closes_normally(config, agent):
    """The contrast that proves the policy did it — same phase, same verifier,
    no measured overconfidence."""
    d = worker.Directive(agent_id=agent.id, goal="ship the thing")
    t = tsk.attach_plan(config, agent, tsk.create(config, agent, d),
                        pl.Plan(goal="ship the thing",
                                phases=[pl.Phase(title="make it good",
                                                 verified_when="it feels right")]))

    def always_pass(**_kw):
        return {"state": "PASS", "why": "looks done to me"}

    out = ses._verify_phase(config, agent, t, verifier=always_pass,
                            evidence="I did it", engine="claude", index=0,
                            now=lambda: 1.0)
    assert out.verdict["state"] == "PASS"


def test_the_policy_never_touches_authority(config, agent):
    """Tightening changes how closely work is watched. It has no ceiling, no
    grant and no permission in it at all."""
    _overconfident(config, agent)
    rec = fc.supervision(config, agent).as_record()
    assert set(rec) == {"level", "n", "bias", "require_deterministic",
                        "max_delegated_phases", "why"}
    assert "ceiling" not in str(rec).lower()
