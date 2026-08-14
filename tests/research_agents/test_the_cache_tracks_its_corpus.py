"""A cached benchmark must not outlive the data it was built from.

The seed cache keyed itself on the agent, the seed and the generator's SOURCE,
and reasoned from that: "change a generator and the key changes, so a stale
cache cannot serve data the current code would not produce". Half of what the
data depends on was missing from that sentence. Every one of these benchmarks
reads a corpus at run time, and a corpus is not source.

What it cost, on 2026-08-14: the TCGA fetcher was found to be dropping living
patients, leaving a development cohort of 196 with 180 deaths. Fixing it gave
499 cases at 36% events. Nothing invalidated, so the next run returned the OLD
numbers for the seeds that happened to be cached and NEW numbers for the rest —
seeds 0-3 identical to the last digit, seeds 4-11 completely different. One
night's results, drawn from two different cohorts, with nothing in the output
saying which was which.

That is the failure mode this whole package exists to refuse, so it is guarded
here rather than remembered.
"""
from __future__ import annotations

import json

import pytest

from ai4science.harness.agents.research_agents.runners import ONCO, common
from ai4science.harness.agents.research_agents.runners import corpus as _c


@pytest.fixture
def fake_corpus(tmp_path, monkeypatch):
    """A corpus root under our control, so the test can change the data."""
    monkeypatch.setattr(_c, "DEFAULT_ROOT", tmp_path)
    monkeypatch.setattr(_c, "_DIGESTS", {})
    d = tmp_path / _c.TCGA_SURVIVAL.key
    d.mkdir(parents=True)

    def write(n_dev):
        rows = [{"case": "TCGA-%02d-%04d" % (i % 7, i), "age": 60.0, "male": 1.0,
                 "stage": 2.0, "t_stage": 2.0, "n_stage": 0.0, "staged": 1.0,
                 "prior_malignancy": 0.0, "time": 100.0 + i, "event": i % 3 == 0}
                for i in range(n_dev)]
        (d / "dev.json").write_text(json.dumps({"project": "TCGA-LUAD", "rows": rows}))
        (d / "ext.json").write_text(json.dumps({"project": "TCGA-LUSC", "rows": rows}))
    return write


def test_the_key_changes_when_the_corpus_changes(fake_corpus):
    fake_corpus(120)
    before = common._seed_key(ONCO, 0)
    fake_corpus(240)
    _c._DIGESTS.clear()
    after = common._seed_key(ONCO, 0)
    assert before != after, (
        "the same key for two different cohorts — a re-fetch would leave every "
        "cached seed serving data that no longer exists")


def test_the_key_is_stable_when_nothing_changes(fake_corpus):
    """The point is invalidation, not cache-busting. A key that moved on its own
    would regenerate every seed of every night and cost the hour the cache was
    introduced to save."""
    fake_corpus(120)
    first = common._seed_key(ONCO, 0)
    _c._DIGESTS.clear()
    assert common._seed_key(ONCO, 0) == first


def test_the_digest_is_content_not_timestamps(fake_corpus, tmp_path):
    """A corpus copied to another machine keeps its bytes and loses its mtimes.
    Two machines holding the same data must agree on the key, or a fleet shares
    no cache at all and every machine re-derives what its neighbour already had.
    """
    fake_corpus(120)
    d = tmp_path / _c.TCGA_SURVIVAL.key
    digest = _c.TCGA_SURVIVAL.digest()
    for f in d.iterdir():
        import os
        os.utime(f, (1_000_000, 1_000_000))
    _c._DIGESTS.clear()
    assert _c.TCGA_SURVIVAL.digest() == digest


def test_a_seed_is_only_as_distinct_as_its_data(fake_corpus):
    """Two different seeds still differ. Folding the corpus in must not collapse
    the seed axis, which is what a mis-ordered hash update would do."""
    fake_corpus(120)
    assert common._seed_key(ONCO, 0) != common._seed_key(ONCO, 1)
