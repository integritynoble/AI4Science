"""The DL4, DL6 and DLOmega environments.

Same discipline as the task suite: the interesting assertions are that a
competent policy **passes**, because a world only ever shown to refuse may be
unwinnable and look rigorous. Each environment is also checked against a naive
policy that plays the way an agent actually plays when it is not doing the
level -- acts on the brief without checking the world, commits on surface
signal, persists nothing -- and must fail.

The leak tests are the other half. An environment whose ``observe`` depends on
hidden state has handed the agent the answer for free, so each hidden field is
mutated after setup and the observation must not move.
"""
from __future__ import annotations

import json

import pytest

from ai4science.harness.agents.dli_bench.envs import (
    COMPETENT, ENVIRONMENTS, NAIVE, CharterEnv, MissionEnv, ProjectEnv)
from ai4science.harness.agents.dli_bench.envs.core import ActionError
from ai4science.harness.agents.dli_bench.frontier import BANDS, LEVEL_REQ
from ai4science.harness.agents.dli_bench.tasks import COVERAGE, missing_levels

KEYS = sorted(ENVIRONMENTS)
SEEDS = (1, 2, 3, 4, 5)


def _run(key, seed, policy_map, budget=None):
    spec = ENVIRONMENTS[key]
    env = spec.instantiate(seed, budget)
    policy_map[key](env)
    return env, env.score()


# ------------------------------------------------------------- the gates

@pytest.mark.parametrize("key", KEYS)
@pytest.mark.parametrize("seed", SEEDS)
def test_a_competent_policy_passes(key, seed):
    env, v = _run(key, seed, COMPETENT)
    assert v.passed, "%s seed %d rejected competent play: %s" % (key, seed, v.reasons)


@pytest.mark.parametrize("key", KEYS)
@pytest.mark.parametrize("seed", SEEDS)
def test_a_naive_policy_fails(key, seed):
    env, v = _run(key, seed, NAIVE)
    assert not v.passed, "%s seed %d accepted naive play" % (key, seed)


@pytest.mark.parametrize("key", KEYS)
def test_doing_nothing_fails(key):
    spec = ENVIRONMENTS[key]
    env = spec.instantiate(0)
    assert not env.score().passed


# ------------------------------------------- observations hide what they must

def test_project_observation_does_not_depend_on_hidden_state():
    """Mutating a hidden field must not move the observation. Anything that
    does move it was being given away for nothing."""
    e = ProjectEnv(seed=3, budget=120)
    before = json.dumps(e.observe(), sort_keys=True)
    e.corrupt = "src_delta" if e.corrupt != "src_delta" else "src_alpha"
    e.invalid = [m for m in ("ridge", "forest", "spectral") if m != e.invalid][0]
    e.best = [m for m in e.truth if m != e.best][0]
    e.truth = {k: 0.999 for k in e.truth}
    assert json.dumps(e.observe(), sort_keys=True) == before


def test_mission_observation_does_not_depend_on_hidden_state():
    e = MissionEnv(seed=3, budget=150)
    before = json.dumps(e.observe(), sort_keys=True)
    e.breaking = [m for m in ("rebuild", "patch", "reroute", "rewrite")
                  if m != e.breaking][0]
    e.right_method = {c: "rewrite" for c in e.right_method}
    e.severity = {c: 0.99 for c in e.severity}
    assert json.dumps(e.observe(), sort_keys=True) == before


def test_charter_observation_does_not_depend_on_hidden_state():
    e = CharterEnv(seed=3, budget=220)
    before = json.dumps(e.observe(), sort_keys=True)
    for v in e.q.values():
        v["utility"] = 9.9
        v["distractor"] = not v["distractor"]
        v["method"] = "model"
    assert json.dumps(e.observe(), sort_keys=True) == before


@pytest.mark.parametrize("key", KEYS)
def test_observations_never_name_hidden_fields(key):
    env = ENVIRONMENTS[key].instantiate(2)
    text = json.dumps(env.observe(), sort_keys=True).lower()
    for word in ("utility", "distractor", "right_method", "breaking", "corrupt",
                 "invalid", "truth", "severity", "prereq", "surface"):
        assert word not in text, "%s leaks %r in observe()" % (key, word)


def test_a_distractor_is_only_visible_after_paying_for_it():
    """Surface signal is what a distractor exploits, so it must be available;
    the fact that it *is* one must not be, until investigated."""
    e = CharterEnv(seed=4, budget=220)
    d = sorted(e.distractors)[0]
    surveyed = e.act("survey")["open_questions"]
    if d in surveyed:
        assert "is_substantive" not in surveyed[d]
    shallow = e.act("investigate", q=d, effort=0.5)
    assert "is_substantive" not in shallow
    deep = e.act("investigate", q=d, effort=2.0)
    assert deep.get("is_substantive") is False


# ------------------------------------------------------------- the mechanics

@pytest.mark.parametrize("key", KEYS)
def test_runs_are_reproducible(key):
    a, _ = _run(key, 9, COMPETENT)
    b, _ = _run(key, 9, COMPETENT)
    assert a.transcript_json() == b.transcript_json()


@pytest.mark.parametrize("key", KEYS)
def test_seeds_give_different_worlds(key):
    seen = {_run(key, s, COMPETENT)[0].transcript_json() for s in range(5)}
    assert len(seen) == 5, "%s repeats across seeds" % key


@pytest.mark.parametrize("key", KEYS)
def test_events_fire_on_action_count_not_wall_clock(key):
    env = ENVIRONMENTS[key].instantiate(6)
    assert env.events, "%s has no scheduled events; then nothing changes" % key
    first = min(e.at_action for e in env.events)
    while env.n < first and not env.closed:
        env.act("observe")
    assert all(not e.fired for e in env.events if e.at_action > env.n)


@pytest.mark.parametrize("key", KEYS)
def test_an_unknown_action_is_refused_not_ignored(key):
    env = ENVIRONMENTS[key].instantiate(1)
    with pytest.raises(ActionError):
        env.act("do_the_thing")


@pytest.mark.parametrize("key", KEYS)
def test_the_budget_actually_binds(key):
    env = ENVIRONMENTS[key].instantiate(1, budget=3.0)
    for _ in range(20):
        try:
            r = env.act(sorted(a for a, c in env.COST.items() if c > 0)[0])
        except ActionError:
            break
        if r.get("error") == "budget exhausted":
            break
    assert env.spent <= 3.0
    assert env.closed


@pytest.mark.parametrize("key", KEYS)
def test_free_actions_are_not_meaningful_work(key):
    env = ENVIRONMENTS[key].instantiate(1)
    for _ in range(30):
        env.act("observe")
    assert env.meaningful_actions == 0


# ------------------------------------------------------------- registration

@pytest.mark.parametrize("key", KEYS)
def test_environment_bands_where_its_level_requires(key):
    spec = ENVIRONMENTS[key]
    assert spec.difficulty.band == LEVEL_REQ[spec.level][0]
    assert spec.difficulty.band in BANDS


def test_every_level_is_now_posed_by_something():
    assert missing_levels() == ()
    for lvl in ("DL4", "DL6", "DLOmega"):
        assert COVERAGE[lvl].startswith("built")


def test_omega_needs_more_than_novelty_to_band_there():
    """TOmega is not 'T5 but longer'. It is the level where the agent chooses
    the problems, so it needs ambiguity and a world that moves, not just an
    unknown method."""
    from ai4science.harness.agents.dli_bench.spec import Difficulty
    assert Difficulty(novelty=4).band == "T5"
    assert Difficulty(novelty=4, change=3, ambiguity=4).band == "TOmega"
    assert Difficulty(horizon=4, change=3).band == "T6"
