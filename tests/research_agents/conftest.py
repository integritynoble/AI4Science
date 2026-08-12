"""One definition of "this machine does not have the data".

A dataset someone has to accept terms for is not a broken build, so a missing
corpus skips. That rule was written once in test_domain_runners and not in
test_dual_function, and the two files disagreed in a way that only showed up on
a machine with no corpora at all: the domain tests skipped politely while the
dual-function tests raised CorpusMissing and reported eight failures. Same
absent file, two verdicts, and the noisier one was wrong.

It lives here so there is one shape to audit rather than two.
"""
from __future__ import annotations

import pytest

from ai4science.harness.agents.research_agents.runners import (
    benchmark_for as _benchmark_for, corpus as _corpus,
)


@pytest.fixture(autouse=True)
def isolated_selfmodel_store(tmp_path, monkeypatch):
    """No test in this package reads or writes the real observation store.

    `run_domain_task` records a passing default-params run through
    `observations.record_run`, and `build()` replays whatever is stored. Without
    this, `test_the_intended_method_passes[drug-design]` would append a row to
    ~/.ai4science/selfmodel on every run on a machine that has DUD-E, and every
    test that builds an agent would see whatever last night left there. A suite
    whose result depends on the developer's home directory is not a suite.

    It redirects the path and nothing else — the recording and the replay still
    happen, and test_observations.py sets the variable again itself rather than
    relying on this.
    """
    monkeypatch.setenv("AI4SCIENCE_SELFMODEL_STORE", str(tmp_path / "selfmodel"))


def needs_corpus(bench) -> None:
    """Skip, do not fail, when the real data is not on this machine."""
    if not bench.real:
        return
    c = _corpus.ALL[bench.corpus]
    if not c.present():
        pytest.skip("%s not fetched on this machine (%s)" % (c.key, c.fetch))


def bench_or_skip(name: str):
    """`benchmark_for`, but it declines rather than explodes without data."""
    b = _benchmark_for(name)
    needs_corpus(b)
    return b
