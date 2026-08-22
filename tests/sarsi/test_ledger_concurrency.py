"""Two writers, one append-only file. [plan v3 §11.1]

Two sarsi sessions run on this machine at once and both write the same ledger.
Without a lock, two appends can interleave inside a single line and the result
is a file where some rows are two half-records spliced together — which a
reader that skips corrupt lines then discards silently, losing the record AND
the fact that it was lost.

`ledger.append()` takes `flock(LOCK_EX)` for the write. These tests hold it to
that under real concurrency rather than trusting the call is there.
"""
import json
import multiprocessing as mp
import os

import pytest

from ai4science.harness.agents.sarsi import ledger, registry as reg


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def config(tmp_path):
    c = reg.parse(reg.default_config(owner_id="7007143162"), root=tmp_path)
    c.ensure_dirs()
    return c


def _write_many(state_dir, root, tag, n):
    os.environ["SARSI_STATE_DIR"] = str(state_dir)
    from ai4science.harness.agents.sarsi import ledger as lg, registry as rg
    cfg = rg.parse(rg.default_config(owner_id="7007143162"), root=root)
    for i in range(n):
        lg.append(cfg, "reports", {"agent": "sarsi-worker", "state": "noted",
                                   "writer": tag, "seq": i,
                                   "evidence": ["x" * 400]})


def test_concurrent_appends_do_not_corrupt_the_file(config, tmp_path):
    """Long rows on purpose: a short record can fit in one atomic write by
    luck, and luck is not the property under test."""
    procs = [mp.Process(target=_write_many, args=(tmp_path, tmp_path, tag, 40))
             for tag in ("a", "b", "c")]
    for p in procs:
        p.start()
    for p in procs:
        p.join(60)

    path = ledger._path(config, "reports")
    lines = [l for l in path.read_text().splitlines() if l.strip()]
    rows = []
    for l in lines:
        rows.append(json.loads(l))          # raises if any line was spliced
    assert len(rows) == 120
    for tag in ("a", "b", "c"):
        assert sorted(r["seq"] for r in rows if r["writer"] == tag) == list(range(40))


def test_a_reader_that_meets_a_bad_line_keeps_the_rest(config):
    """Append-only means a damaged line is not a reason to lose what follows."""
    ledger.append(config, "reports", {"agent": "sarsi-worker", "state": "one"})
    path = ledger._path(config, "reports")
    with path.open("a") as fh:
        fh.write("{not json at all\n")
    ledger.append(config, "reports", {"agent": "sarsi-worker", "state": "two"})
    states = [r.get("state") for r in ledger.read(config, "reports")]
    assert states == ["one", "two"]


def test_every_row_is_stamped_when_it_was_written(config):
    ledger.append(config, "reports", {"agent": "sarsi-worker", "state": "one"})
    assert ledger.read(config, "reports")[0]["at"]
