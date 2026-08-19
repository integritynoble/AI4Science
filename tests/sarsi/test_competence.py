"""L4 — what this worker has been *verified* to do.

Ported from the console's `sarsi/competence.py`. The self-model could say what
the worker IS and what it is HOLDING, and not what it has PROVEN: every verdict
was on disk and nothing read them back.

The four refusals come across unchanged, because each is the point:

  **Only verified outcomes count.** A task the verifier never judged, or refused
  to judge, is not evidence about capability. The worker's own account of how it
  went is L7 and is not admitted at any weight.

  **Unmeasured is None, never zero.** `0.0` would make "never seen it work"
  indistinguishable from "seen it fail", and the second is a far stronger claim
  than the evidence supports.

  **The mean is never published alone.** Laplace `(k+1)/(n+2)` with its sample
  count and interval, because 1-of-1 and 100-of-100 are the same number and not
  the same claim.

  **It may narrow what the worker does; it may never widen it.** `may_widen()`
  exists to be called and always refuses, so a future caller reaching for "the
  record is good enough to skip this" finds a refusal at the call site rather
  than a convention in a docstring.

One thing is ADDED, because the target system records something the console
does not: an ai4science verdict carries `independent` — whether the engine that
judged is the engine that did the work. A self-judged PASS is weaker evidence,
and averaging the two together destroys exactly the distinction the flag exists
to make.
"""
import json

import pytest

from ai4science.harness.agents.sarsi import (competence as comp, registry as reg,
                                             task as tsk, worker as wk)


@pytest.fixture
def config(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path / "s"))
    root = tmp_path / "s"; root.mkdir(parents=True, exist_ok=True)
    p = reg.config_path(root)
    p.write_text(json.dumps(reg.default_config(owner_id="7007143162")))
    c = reg.load(p); c.ensure_dirs()
    return c


def _judged(config, agent, state, *, independent=True, ceiling="A1", n=1):
    for _ in range(n):
        t = tsk.create(config, agent, wk.Directive(agent_id=agent.id, goal="g"))
        t.verdict = {"state": state, "independent": independent,
                     "engine": "claude" if not independent else "gpt"}
        t.session = {"name": "s", "ceiling": ceiling}
        tsk._save(agent, t)


# ── unmeasured is None, never zero ────────────────────────────────────

def test_a_worker_with_no_verdicts_has_no_estimate(config):
    a = config.agents["sarsi-worker"]
    assert comp.competence(config, a) is None


def test_and_that_is_not_the_same_as_zero(config):
    """The distinction the whole module exists to preserve."""
    a = config.agents["sarsi-worker"]
    assert comp.competence(config, a) is not 0.0
    _judged(config, a, "FAIL", n=2)
    est = comp.competence(config, a)
    assert est is not None and est["p"] > 0.0, est


def test_an_unjudged_task_is_an_absence_not_a_failure(config):
    """Charging the worker for the judge being unavailable is the error this
    prevents."""
    a = config.agents["sarsi-worker"]
    tsk.create(config, a, wk.Directive(agent_id=a.id, goal="never judged"))
    assert comp.competence(config, a) is None


def test_a_verdict_the_verifier_would_not_give_is_also_an_absence(config):
    a = config.agents["sarsi-worker"]
    t = tsk.create(config, a, wk.Directive(agent_id=a.id, goal="g"))
    t.verdict = {"state": "UNKNOWN", "independent": True}
    tsk._save(a, t)
    assert comp.competence(config, a) is None


# ── the mean is never published alone ─────────────────────────────────

def test_three_lucky_runs_are_not_certainty(config):
    """`k/n` says 100%. Laplace does not, and that is the whole reason for it."""
    a = config.agents["sarsi-worker"]
    _judged(config, a, "PASS", n=3)
    est = comp.competence(config, a)
    assert est["p"] < 1.0, est
    assert est["p"] == pytest.approx(4 / 5), est


def test_the_sample_and_the_interval_travel_with_it(config):
    a = config.agents["sarsi-worker"]
    _judged(config, a, "PASS", n=3)
    est = comp.competence(config, a)
    assert est["n"] == 3 and est["passed"] == 3 and est["failed"] == 0
    assert est["ci"] > 0


def test_more_evidence_narrows_the_interval(config):
    """1-of-1 and 100-of-100 are the same mean and not the same claim."""
    a = config.agents["sarsi-worker"]
    _judged(config, a, "PASS", n=1)
    few = comp.competence(config, a)["ci"]
    _judged(config, a, "PASS", n=40)
    many = comp.competence(config, a)["ci"]
    assert many < few, (few, many)


# ── the ai4science addition: a self-judged verdict is weaker ──────────

def test_self_judged_and_independent_are_reported_apart(config):
    """An ai4science verdict says whether the engine that judged is the engine
    that worked. Averaging them destroys the distinction the flag exists for."""
    a = config.agents["sarsi-worker"]
    _judged(config, a, "PASS", independent=False, n=4)
    _judged(config, a, "FAIL", independent=True, n=1)
    split = comp.by_independence(config, a)
    assert split["independent"]["n"] == 1
    assert split["self-judged"]["n"] == 4
    assert split["self-judged"]["p"] > split["independent"]["p"]


def test_the_headline_says_how_much_of_it_is_self_judged(config):
    """A single number that hides four self-judged passes is the number an
    owner would act on wrongly."""
    a = config.agents["sarsi-worker"]
    _judged(config, a, "PASS", independent=False, n=4)
    est = comp.competence(config, a)
    assert est["self_judged"] == 4, est


def test_split_by_the_ceiling_the_work_ran_under(config):
    """The same verdict under a wider grant is a weaker claim."""
    a = config.agents["sarsi-worker"]
    _judged(config, a, "PASS", ceiling="A1", n=2)
    _judged(config, a, "PASS", ceiling="A2", n=1)
    by = comp.by_ceiling(config, a)
    assert set(by) == {"A1", "A2"}
    assert by["A1"]["n"] == 2 and by["A2"]["n"] == 1


# ── it may narrow, never widen ────────────────────────────────────────

def test_may_widen_always_refuses(config):
    """It exists to be CALLED. A future caller reaching for 'the record is good
    enough to skip this' must find a refusal at the call site."""
    a = config.agents["sarsi-worker"]
    _judged(config, a, "PASS", n=100)
    assert comp.may_widen(config, a) is False


# ── it says something when there is nothing to say ────────────────────

def test_the_unmeasured_case_gets_a_sentence(config):
    """A blank reads as a rendering fault and invites the reader to supply
    their own number."""
    assert "no verified outcomes" in comp.render(None).lower()


def test_and_a_measured_one_reads_as_a_claim(config):
    a = config.agents["sarsi-worker"]
    _judged(config, a, "PASS", n=3)
    line = comp.render(comp.competence(config, a))
    assert "3" in line and "%" in line
    # Not pytest's "N passed, N failed": these are verdicts on tasks, and that
    # phrasing was read as a failing test run by two different log scanners.
    assert "passed," not in line and "failed" not in line, line


# ── and the self-model carries it ─────────────────────────────────────

def test_the_worker_can_now_say_what_it_has_proven(config):
    from ai4science.harness.agents.sarsi import selfaware
    a = config.agents["sarsi-worker"]
    _judged(config, a, "PASS", n=3)
    by = {c["field"]: c for c in selfaware.claims(config, a)}
    assert "proven" in by, sorted(by)
    assert by["proven"]["authority_level"] == 4, by["proven"]


def test_and_says_so_honestly_when_it_has_not(config):
    from ai4science.harness.agents.sarsi import selfaware
    a = config.agents["sarsi-worker"]
    by = {c["field"]: c for c in selfaware.claims(config, a)}
    assert "no verified outcomes" in str(by["proven"]["value"]).lower()
