"""Reference records: sealing, cost, the model revision, tiers, comparison.

These tests spend no money. The real-model calls are made once, by hand, with
`python -m ai4science.references record`, and the records they produced are on
the file at `docs/references/records.jsonl` — which the last test in this file
reads, so the evidence of a real run is checked by the suite rather than
asserted in a report.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from ai4science.references import compare as compare_mod
from ai4science.references.recorder import cost_of, record_run, revision_of
from ai4science.references.store import (
    CallCost, RecordInvalid, ReferenceRecord, ReferenceStore, SealBroken,
)
from ai4science.references.task import ldct_judge_task

RECORDS = Path(__file__).resolve().parents[2] / "docs" / "references" / "records.jsonl"


# --------------------------------------------------------------------------
# helpers: a fake `claude -p` envelope, shaped exactly like the real one
# --------------------------------------------------------------------------
def envelope(revision="claude-haiku-4-5-20251001", canonical="claude-haiku-4-5",
             result="A: PASS\nB: FAIL\nC: FAIL", cost=0.0190157, **extra):
    env = {
        "total_cost_usd": cost,
        "result": result,
        "is_error": False,
        "num_turns": 1,
        "duration_api_ms": 1942,
        "session_id": "0" * 8,
        "usage": {"input_tokens": 10, "output_tokens": 54,
                  "cache_read_input_tokens": 13607,
                  "cache_creation_input_tokens": 8214},
        "modelUsage": {revision: {
            "inputTokens": 907, "outputTokens": 64,
            "cacheReadInputTokens": 13607, "cacheCreationInputTokens": 8214,
            "costUSD": cost, "canonicalModel": canonical, "costBasis": "list",
        }},
        "_wall_seconds": 1.54,
    }
    env.update(extra)
    return env


def fake_runner(env):
    def _run(model, prompt, timeout=300, cwd=None):
        return env
    return _run


def a_record(**over):
    base = dict(
        record_id="t/basic/rev", tier="basic", task_id="t", task_digest="d" * 8,
        model_revision="claude-haiku-4-5-20251001",
        model_requested="claude-haiku-4-5",
        output="A: PASS\nB: FAIL\nC: FAIL",
        calls=(CallCost(usd_metered=0.019, usd_recomputed=0.0177,
                        input_tokens=907, output_tokens=64),),
        recorded_at="2026-09-22T00:00:00Z",
    )
    base.update(over)
    return ReferenceRecord(**base).sealed()


# --------------------------------------------------------------------------
# the required behaviours
# --------------------------------------------------------------------------
def test_a_reference_record_is_sealed_by_hash_and_a_changed_output_is_detected(tmp_path):
    store = ReferenceStore(tmp_path / "records.jsonl")
    record = store.put(a_record())
    assert record.seal and len(record.seal) == 64
    record.check_seal()                      # the untouched record verifies
    assert store.all()[0].output == record.output
    assert store.broken() == []

    # Edit the output on the file, exactly as an optimiser wanting a friendlier
    # reference would: the seal is left alone because recomputing it is a
    # different, louder act.
    line = json.loads((tmp_path / "records.jsonl").read_text().strip())
    line["output"] = "A: PASS\nB: PASS\nC: PASS"
    (tmp_path / "records.jsonl").write_text(json.dumps(line) + "\n")

    assert store.broken() == [record.record_id]
    with pytest.raises(SealBroken) as e:
        store.all()
    assert "changed after it was recorded" in str(e.value)

    # And a record whose seal was stripped is not quietly treated as fine.
    line.pop("seal")
    (tmp_path / "records.jsonl").write_text(json.dumps(line) + "\n")
    with pytest.raises(SealBroken):
        store.all()


def test_cost_is_recorded_per_call_and_summed(tmp_path):
    store = ReferenceStore(tmp_path / "records.jsonl")
    store.put(a_record(record_id="one", calls=(
        CallCost(usd_metered=0.019, usd_recomputed=0.0177),)))
    store.put(a_record(record_id="two", tier="strong",
                       model_revision="claude-opus-5-2026xxxx", calls=(
        CallCost(usd_metered=0.11, usd_recomputed=0.109),
        CallCost(usd_metered=0.02, usd_recomputed=0.019))))

    per_record = {r.record_id: r.cost_usd for r in store.all()}
    assert per_record["one"] == 0.019
    assert per_record["two"] == round(0.11 + 0.02, 6)      # summed per call
    assert store.total_cost_usd() == round(0.019 + 0.13, 6)  # summed per store

    # The metered figure is preferred over the recomputation, and a call that
    # could not be priced is named rather than counted as free.
    unpriced = a_record(record_id="three", calls=(
        CallCost(usd_metered=None, usd_recomputed=None,
                 not_measured=("provider did not report total_cost_usd",)),))
    assert unpriced.cost_usd is None
    store.put(unpriced)
    assert store.total_cost_usd() == round(0.019 + 0.13, 6)   # unchanged
    assert any("total_cost_usd" in m for m in store.cost_not_measured())

    # Cost comes off a real envelope, not off a constant in this test.
    call = cost_of(envelope(), "claude-haiku-4-5-20251001")
    assert call.usd_metered == 0.0190157
    assert call.usd == 0.0190157
    assert (call.input_tokens, call.output_tokens) == (907, 64)
    assert (call.cache_read_tokens, call.cache_write_tokens) == (13607, 8214)
    assert call.wall_seconds == 1.54
    assert call.usd_recomputed is not None and call.not_measured == ()


def test_a_record_without_a_model_revision_is_refused(tmp_path):
    with pytest.raises(RecordInvalid) as e:
        a_record(model_revision="")
    assert "exact model revision" in str(e.value)
    with pytest.raises(RecordInvalid):
        a_record(model_revision="   ")

    # And the recorder refuses rather than inventing one when the provider's
    # envelope names no model at all.
    nameless = envelope()
    nameless["modelUsage"] = {}
    assert revision_of(nameless, "claude-haiku-4-5") is None
    with pytest.raises(RecordInvalid) as e:
        record_run("claude-haiku-4-5", ldct_judge_task(), tier="basic",
                   runner=fake_runner(nameless))
    assert "exact model revision" in str(e.value)

    # Nothing reached the store.
    store = ReferenceStore(tmp_path / "records.jsonl")
    assert store.all() == []

    # A call that billed two models still names ONE — the one that answered.
    # This is what a real `--model claude-opus-5` invocation looks like: Opus
    # answers and Haiku runs a side call, so picking "the only key" would name
    # whichever key happened to be there.
    two = envelope(revision="claude-opus-5", canonical="claude-opus-5")
    two["modelUsage"]["claude-haiku-4-5-20251001"] = {
        "inputTokens": 1319, "outputTokens": 17, "costUSD": 0.001404,
        "canonicalModel": "claude-haiku-4-5", "costBasis": "list"}
    assert revision_of(two, "claude-opus-5") == "claude-opus-5"
    rec, _ = record_run("claude-opus-5", ldct_judge_task(), tier="strong",
                       runner=fake_runner(two))
    assert rec.model_revision == "claude-opus-5"
    assert sorted(rec.calls[0].per_model_usd) == ["claude-haiku-4-5-20251001",
                                                  "claude-opus-5"]
    assert any("billed 2 models" in m for m in rec.calls[0].not_measured)


def test_the_basic_and_strong_records_name_different_models():
    task = ldct_judge_task()
    basic, _ = record_run("claude-haiku-4-5", task, tier="basic",
                          runner=fake_runner(envelope()))
    strong, _ = record_run(
        "claude-opus-5", task, tier="strong",
        runner=fake_runner(envelope(revision="claude-opus-5",
                                    canonical="claude-opus-5", cost=0.12)))
    assert basic.tier == "basic" and strong.tier == "strong"
    assert basic.model_revision != strong.model_revision
    assert basic.record_id != strong.record_id

    # Whether the recorded name is a DATED revision or only an alias is
    # recorded, not assumed. Haiku's envelope gives the dated revision; Opus 5's
    # gives the alias back, and a pin built on an alias moves under it.
    assert basic.notes["revision_is_dated"] is True
    assert strong.notes["revision_is_dated"] is False

    # The two records the repo actually ships must also differ, on the same
    # frozen task — a "basic and strong" pair that is one model twice is not a
    # pair.
    if RECORDS.exists():
        store = ReferenceStore(RECORDS)
        b = store.tier("basic", task.task_id)
        s = store.tier("strong", task.task_id)
        assert b and s, "the shipped store needs one basic and one strong record"
        assert {r.model_revision for r in b}.isdisjoint(
            {r.model_revision for r in s})
        assert all(r.model_revision.startswith("claude-haiku") for r in b)
        assert all(r.model_revision.startswith("claude-opus") for r in s)


def test_a_comparison_of_a_new_run_against_a_reference_reports_better_worse_or_same_without_altering_the_reference(
        tmp_path):
    task = ldct_judge_task()
    store = ReferenceStore(tmp_path / "records.jsonl")
    # A reference that got two of three right (it missed C).
    reference = store.put(a_record(
        record_id="ref", task_id=task.task_id, task_digest=task.digest,
        output="A: PASS\nB: FAIL\nC: PASS"))
    before_file = (tmp_path / "records.jsonl").read_text()
    before_obj = copy.deepcopy(reference.to_dict())

    worse = compare_mod.compare("A: FAIL\nB: FAIL\nC: PASS", reference, task)
    same = compare_mod.compare("A: PASS\nB: FAIL\nC: PASS", reference, task)
    better = compare_mod.compare("A: PASS\nB: FAIL\nC: FAIL", reference, task)

    assert (worse.verdict, same.verdict, better.verdict) == (
        compare_mod.WORSE, compare_mod.SAME, compare_mod.BETTER)
    assert better.delta > 0 > worse.delta and same.delta == 0
    assert better.run_score == 1.0 and better.reference_score == pytest.approx(2 / 3)
    assert better.trustworthy

    # The reference is untouched: same object, same seal, same bytes on disk.
    assert reference.to_dict() == before_obj
    reference.check_seal()
    assert (tmp_path / "records.jsonl").read_text() == before_file
    assert store.get("ref").output == "A: PASS\nB: FAIL\nC: PASS"

    # A run that ties or wins while missing the negative control is flagged,
    # because in this field the blur that wins on PSNR is the whole point.
    control_missed = compare_mod.compare("A: PASS\nB: PASS\nC: FAIL", reference, task)
    assert control_missed.verdict == compare_mod.SAME
    assert not control_missed.trustworthy
    assert "negative control" in control_missed.caveat

    # A reference recorded against a different task digest is still ranked, but
    # the answer is marked untrustworthy rather than silently used.
    moved = store.put(a_record(record_id="moved", task_id=task.task_id,
                               task_digest="0" * 64,
                               output="A: PASS\nB: FAIL\nC: FAIL"))
    c = compare_mod.compare("A: PASS\nB: FAIL\nC: FAIL", moved, task)
    assert c.verdict == compare_mod.SAME and not c.trustworthy
    assert "the task moved" in c.caveat


# --------------------------------------------------------------------------
# the rest of the mechanism
# --------------------------------------------------------------------------
def test_the_frozen_task_takes_its_answer_key_from_the_repos_own_judge():
    task = ldct_judge_task()
    # Not hand-written here: recompute with the judge and compare.
    from ai4science.harness.agents.research_agents.runners.domains import _judge_ldct
    from ai4science.references.task import CASES, NEGATIVE_CONTROL
    for name, metrics in CASES:
        assert task.answer_key[name] == _judge_ldct(dict(metrics)).passed
    assert task.answer_key == {"A": True, "B": False, "C": False}
    # The negative control is the higher-PSNR blur: best fidelity of the three,
    # and it must fail.
    cases = dict(CASES)
    assert cases[NEGATIVE_CONTROL]["psnr"] == max(m["psnr"] for m in cases.values())
    assert task.answer_key[NEGATIVE_CONTROL] is False
    # The digest moves when the criterion or the cases move.
    assert len(task.digest) == 64
    assert task.fixture["corpus_present"] is False


def test_a_candidate_is_not_a_reference_until_something_outside_the_model_checks_it():
    task = ldct_judge_task()
    candidate, _ = record_run("claude-haiku-4-5", task, tier="basic",
                              runner=fake_runner(envelope()))
    assert candidate.status == "candidate" and candidate.verified_by is None

    # You cannot simply relabel it.
    with pytest.raises(RecordInvalid):
        ReferenceRecord(**{**candidate.to_dict(), "status": "reference",
                           "verified_by": None, "calls": candidate.calls,
                           "seal": None}).validated()
    with pytest.raises(RecordInvalid):
        candidate.promote("")

    promoted = candidate.promote("criterion:ldct-judge-3-candidates/1",
                                 grade=task.grade(candidate.output))
    assert promoted.status == "reference"
    assert promoted.verified_by.startswith("criterion:")
    assert promoted.record_id != candidate.record_id   # the candidate survives
    promoted.check_seal()


def test_the_store_is_append_only_so_a_reference_cannot_be_replaced(tmp_path):
    store = ReferenceStore(tmp_path / "records.jsonl")
    store.put(a_record(record_id="ref"))
    with pytest.raises(RecordInvalid) as e:
        store.put(a_record(record_id="ref", output="something friendlier"))
    assert "append-only" in str(e.value)
    assert len(store.all()) == 1


def test_the_shipped_records_are_real_runs_with_a_metered_cost():
    if not RECORDS.exists():
        pytest.skip("no recorded runs on this checkout")
    store = ReferenceStore(RECORDS)
    records = store.all()                     # raises if any seal is broken
    assert records
    for r in records:
        assert r.notes.get("provider", "").startswith("anthropic")
        assert r.model_revision
        for c in r.calls:
            assert c.usd_metered is not None, (
                "a shipped record must carry the provider's metered cost, not "
                "an estimate")
            assert c.input_tokens and c.output_tokens
            assert c.wall_seconds and c.wall_seconds > 0
        assert r.cost_usd and r.cost_usd > 0
    # The pilot's whole spend, in one number.
    assert store.total_cost_usd() < 2.0, "the pilot was capped at $2"
