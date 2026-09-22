"""CLI for the reference-record store. There is no GUI; this is the demo.

    python -m ai4science.references task
    python -m ai4science.references record --model claude-haiku-4-5 --tier basic
    python -m ai4science.references list
    python -m ai4science.references verify
    python -m ai4science.references cost
    python -m ai4science.references compare --against <record_id> --output-file out.txt

`record` SPENDS MONEY: it calls a real model once and prints what the call cost
before it prints anything else.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DEFAULT_STORE = Path("docs/references/records.jsonl")


def _store(path: str):
    from ai4science.references.store import ReferenceStore
    return ReferenceStore(path)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m ai4science.references")
    p.add_argument("--store", default=str(DEFAULT_STORE))
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("task", help="print the frozen task and its answer key")

    rec = sub.add_parser("record", help="run a real model once and record it")
    rec.add_argument("--model", required=True)
    rec.add_argument("--tier", required=True, choices=("basic", "strong"))
    rec.add_argument("--record-id", default=None)
    rec.add_argument("--timeout", type=int, default=300)
    rec.add_argument("--dry-run", action="store_true",
                     help="print the prompt and spend nothing")
    rec.add_argument("--envelope-file", default=None,
                     help="record from a provider envelope already captured "
                          "from a real call, instead of calling again. Spends "
                          "nothing and keeps a paid-for call from being wasted "
                          "when the record was refused for a fixable reason.")

    pro = sub.add_parser("promote", help="candidate → reference, naming the check")
    pro.add_argument("--record-id", required=True)
    pro.add_argument("--verified-by", required=True,
                     help="what checked the output: 'criterion:<task_id>' for "
                          "the fixture's own answer key, or 'human:<name>' when "
                          "a person signed it. A criterion check is the weaker "
                          "of the two and the record keeps them distinguishable.")

    sub.add_parser("list", help="every record, seals re-checked")
    sub.add_parser("verify", help="re-check every seal; exit 1 if any is broken")
    sub.add_parser("cost", help="cost per call and the sum")

    cmp_ = sub.add_parser("compare", help="rank a new run against a reference")
    cmp_.add_argument("--against", required=True, help="record_id")
    cmp_.add_argument("--output-file", required=True,
                      help="file holding the new run's output")

    a = p.parse_args(argv)
    from ai4science.references.task import ldct_judge_task
    task = ldct_judge_task()

    if a.cmd == "task":
        print(json.dumps({"task_id": task.task_id, "digest": task.digest,
                          "answer_key": dict(task.answer_key),
                          "criterion_source": task.criterion_source,
                          "fixture": task.fixture}, indent=2))
        print("\n--- prompt ---\n" + task.prompt)
        return 0

    if a.cmd == "record":
        if a.dry_run:
            print(task.prompt)
            return 0
        from ai4science.references.recorder import record_run
        runner = None
        if a.envelope_file:
            saved = json.loads(Path(a.envelope_file).read_text(encoding="utf-8"))

            def runner(model, prompt, timeout=300, cwd=None, _e=saved):  # noqa: F811
                if _e.get("_prompt") and _e["_prompt"] != prompt:
                    raise SystemExit(
                        "the saved envelope answered a different prompt; a "
                        "record sealed against this task would be a lie")
                return _e
        record, _ = record_run(a.model, task, tier=a.tier, record_id=a.record_id,
                              timeout=a.timeout,
                              **({"runner": runner} if runner else {}))
        for i, c in enumerate(record.calls):
            print("call %d: metered $%s | recomputed $%s | in=%s out=%s "
                  "cache_read=%s cache_write=%s | %.2fs"
                  % (i, c.usd_metered, c.usd_recomputed, c.input_tokens,
                     c.output_tokens, c.cache_read_tokens, c.cache_write_tokens,
                     c.wall_seconds or 0.0))
            for m in c.not_measured:
                print("  NOT MEASURED: %s" % m)
        store = _store(a.store)
        store.put(record)
        print("recorded %s (%s, %s) revision=%s cost=$%s grade=%s/%s"
              % (record.record_id, record.tier, record.status,
                 record.model_revision, record.cost_usd,
                 record.grade["correct"], record.grade["of"]))
        print("store total so far: $%s" % store.total_cost_usd())
        return 0

    store = _store(a.store)

    if a.cmd == "promote":
        candidate = store.get(a.record_id)
        if a.verified_by.startswith("criterion:"):
            want = a.verified_by.split(":", 1)[1]
            if want != task.task_id:
                raise SystemExit(
                    "criterion %r is not this task's (%r) — a promotion must "
                    "name the check that actually ran" % (want, task.task_id))
            grade = task.grade(candidate.output)
            if grade["score"] < 1.0 or not grade["negative_control_passed"]:
                raise SystemExit(
                    "the criterion did not pass this output (%d/%d, negative "
                    "control %s) — nothing to promote"
                    % (grade["correct"], grade["of"],
                       "passed" if grade["negative_control_passed"] else "MISSED"))
        else:
            grade = candidate.grade
        promoted = store.put(candidate.promote(a.verified_by, grade=grade))
        print("promoted %s -> %s (verified_by=%s); the candidate %s stays on "
              "the file" % (candidate.record_id, promoted.record_id,
                            promoted.verified_by, candidate.record_id))
        return 0

    if a.cmd == "list":
        for r in store.all():
            print("%-64s %-7s %-10s %-34s $%-10s %s"
                  % (r.record_id, r.tier, r.status, r.model_revision,
                     r.cost_usd, r.seal[:12]))
        return 0

    if a.cmd == "verify":
        bad = store.broken()
        if bad:
            print("SEAL BROKEN: %s" % ", ".join(bad))
            return 1
        print("%d record(s), every seal verifies" % len(store._read_raw()))
        return 0

    if a.cmd == "cost":
        for r in store.all():
            for i, c in enumerate(r.calls):
                print("%s call %d: $%s" % (r.record_id, i, c.usd))
        print("TOTAL $%s" % store.total_cost_usd())
        for m in store.cost_not_measured():
            print("NOT MEASURED: %s" % m)
        return 0

    if a.cmd == "compare":
        from ai4science.references.compare import compare
        reference = store.get(a.against)
        output = Path(a.output_file).read_text(encoding="utf-8")
        c = compare(output, reference, task)
        print("%s: run %.3f vs reference %.3f (delta %+.3f)"
              % (c.verdict.upper(), c.run_score, c.reference_score, c.delta))
        if c.caveat:
            print("CAVEAT: %s" % c.caveat)
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())
