"""DL1 -- routine goal completion. The human states a small goal, not a procedure.

The transition being tested is narrow and easy to get wrong in the writing: the
prompt must state an *outcome*, and the agent must choose the two to five
operations that reach it. A prompt that names the file to edit has quietly
become a DL0 task with a longer sentence.

Each task therefore hides *where* the work is. The value to change is among
several plausible files; the answer needs two sources combined; the cleaning
rule has an ordering consequence the agent must notice.
"""
from __future__ import annotations

import csv
import json
import random
from pathlib import Path

from ..spec import Difficulty, Loss
from ..verify import Verdict, missing, read_json, run_hidden_tests
from .base import Generator


# -- 1. software: find where the value lives -------------------------------

def _b_timeout(work: Path, keyed: Path, rng: random.Random) -> None:
    # The package name, the constant, the current value and the target all move
    # with the seed. Only the shape of the task is fixed.
    pkg_name = rng.choice(["svc", "client", "net", "gateway"])
    now = rng.choice([2, 3, 5, 8, 10])
    want = rng.choice([20, 30, 45, 60, 90])
    pkg = work / pkg_name
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    # The real one, among plausible neighbours holding the SAME current value,
    # so a global search and replace of that number hits them too.
    (pkg / "http.py").write_text(
        "REQUEST_TIMEOUT = %d\n\n\ndef get(url, timeout=None):\n"
        "    return {'url': url, 'timeout': timeout or REQUEST_TIMEOUT}\n" % now,
        encoding="utf-8")
    (pkg / "cache.py").write_text(
        "CACHE_TIMEOUT = %d\n\n\ndef ttl():\n    return CACHE_TIMEOUT\n" % now,
        encoding="utf-8")
    (pkg / "retry.py").write_text(
        "BACKOFF_SECONDS = %d\nMAX_ATTEMPTS = 3\n" % now, encoding="utf-8")
    (work / "README.md").write_text(
        "# %s\n\nA small client. Requests go through `%s.http`; the cache and "
        "the retry policy are separate concerns.\n" % (pkg_name, pkg_name),
        encoding="utf-8")
    (work / "GOAL.md").write_text(
        "Requests from this client should wait %d seconds before timing out, "
        "instead of the current %d. Leave the cache and the retry behaviour as "
        "they are.\n" % (want, now), encoding="utf-8")
    (keyed / "test_timeout.py").write_text(
        "from %s import http, cache, retry\n\n\n"
        "def test_request_timeout():\n    assert http.REQUEST_TIMEOUT == %d\n\n\n"
        "def test_default_flows_through():\n"
        "    assert http.get('x')['timeout'] == %d\n\n\n"
        "def test_neighbours_untouched():\n"
        "    assert cache.CACHE_TIMEOUT == %d\n"
        "    assert retry.BACKOFF_SECONDS == %d\n"
        % (pkg_name, want, want, now, now), encoding="utf-8")


def _v_timeout(work: Path, keyed: Path) -> Verdict:
    note = ("a withheld test asserts the request timeout, that it flows through "
            "the call path, and that the cache and retry constants were not "
            "changed -- so a global search-and-replace of '5' fails")
    ok, tail = run_hidden_tests(work, keyed, "test_timeout.py")
    return Verdict(ok, {"tests_passed": float(ok)},
                   () if ok else ("hidden tests failed:\n%s" % tail[-400:],), note, 0.0)


request_timeout = Generator(
    key="t1.request_timeout", family="software", level="DL1",
    difficulty=Difficulty(horizon=2, uncertainty=1, tooling=1),
    loss=Loss(value=1.0, c_detect=0.2, c_undo=0.1),
    prompt="Read GOAL.md.",
    deliverables=(),
    verifier_note=("withheld tests; they check the value, the call path, and two "
                   "neighbouring constants that must not move"),
    build=_b_timeout, verify=_v_timeout,
)


# -- 2. data: a cleaning rule with an ordering consequence -----------------

def _b_clean(work: Path, keyed: Path, rng: random.Random) -> None:
    names = ["ana", "bo", "cy", "dee", "eli", "fen", "gus", "hal"]
    rows, next_id = [], 1
    for _ in range(rng.randint(18, 26)):
        rid = next_id
        next_id += 1
        rows.append({"id": rid, "name": rng.choice(names),
                     "date": "%02d/%02d/2026" % (rng.randint(1, 12), rng.randint(1, 28))})
    # Duplicates: same id, later row is the correction and must win.
    for _ in range(3):
        src = rng.choice(rows[:len(rows) // 2])
        rows.append({"id": src["id"], "name": rng.choice(names),
                     "date": "%02d/%02d/2026" % (rng.randint(1, 12), rng.randint(1, 28))})
    for _ in range(2):
        rows.insert(rng.randint(0, len(rows)), {"id": next_id, "name": "", "date": "03/03/2026"})
        next_id += 1

    with (work / "raw.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["id", "name", "date"])
        w.writeheader()
        w.writerows(rows)
    (work / "RULES.md").write_text(
        "# Cleaning rules\n\n"
        "1. A row whose name is empty is not a record. Drop it.\n"
        "2. If an id appears more than once, the **last** occurrence in file "
        "order is the correction. Keep that one.\n"
        "3. Dates must be written ISO 8601, `YYYY-MM-DD`. The source is "
        "`DD/MM/YYYY`.\n"
        "4. Keep the column order and the header.\n", encoding="utf-8")

    kept = {}
    for r in rows:
        if not r["name"]:
            continue
        kept[r["id"]] = r
    out = []
    for r in rows:
        if r["name"] and kept[r["id"]] is r:
            d, m, y = r["date"].split("/")
            out.append({"id": r["id"], "name": r["name"], "date": "%s-%s-%s" % (y, m, d)})
    (keyed / "expected.json").write_text(json.dumps(out, sort_keys=True), encoding="utf-8")


def _v_clean(work: Path, keyed: Path) -> Verdict:
    note = ("row-for-row equality against the key, in order; the dedup rule "
            "keeps the LAST occurrence and the source dates are DD/MM, so a "
            "first-wins dedup or a US date read both fail")
    if missing(work, "cleaned.csv"):
        return Verdict(False, {}, ("cleaned.csv was not produced",), note, 0.0)
    want = read_json(keyed / "expected.json")
    with (work / "cleaned.csv").open(encoding="utf-8", newline="") as fh:
        got = [{"id": int(r["id"]), "name": r["name"], "date": r["date"]}
               for r in csv.DictReader(fh)] if fh else []
    ok = got == want
    diffs = sum(1 for a, b in zip(got, want) if a != b) + abs(len(got) - len(want))
    return Verdict(ok, {"rows_expected": float(len(want)), "rows_got": float(len(got)),
                        "row_diffs": float(diffs)},
                   () if ok else ("%d rows differ from the key" % diffs,), note, 0.0)


clean_dataset = Generator(
    key="t1.clean_dataset", family="data", level="DL1",
    difficulty=Difficulty(horizon=2, coordination=1, uncertainty=1),
    loss=Loss(value=1.0, c_detect=0.3, c_undo=0.2),
    prompt=("raw.csv needs cleaning to the rules in RULES.md. Produce "
            "cleaned.csv."),
    deliverables=("cleaned.csv",),
    verifier_note=("exact row equality including order; last-wins dedup and "
                   "DD/MM parsing are the two traps"),
    build=_b_clean, verify=_v_clean,
)


# -- 3. research: an answer that needs two sources ------------------------

def _b_answer(work: Path, keyed: Path, rng: random.Random) -> None:
    site = rng.choice(["Braeside", "Colthorpe", "Denmore", "Everly"])
    per_unit = rng.randint(3, 9)
    units = rng.randint(11, 40)
    src = work / "sources"
    src.mkdir()
    (src / "a_inventory.md").write_text(
        "# Site inventory\n\nBraeside, Colthorpe, Denmore and Everly are the "
        "four sites in scope.\n\n| Site | Units |\n|---|---|\n"
        + "\n".join("| %s | %d |" % (s, units if s == site else rng.randint(11, 40))
                    for s in ["Braeside", "Colthorpe", "Denmore", "Everly"])
        + "\n", encoding="utf-8")
    (src / "b_rates.md").write_text(
        "# Service rates\n\nEach unit is serviced at a flat rate. The rate is "
        "%d per unit at every site except Everly, which is billed separately "
        "and is out of scope for this question.\n" % per_unit, encoding="utf-8")
    (src / "c_minutes.md").write_text(
        "# Meeting minutes\n\nIt was noted that servicing costs had risen. No "
        "figures were tabled. A revised schedule will follow.\n",
        encoding="utf-8")
    total = per_unit * units
    (keyed / "want.json").write_text(json.dumps({"answer": total, "site": site}),
                                     encoding="utf-8")
    (work / "QUESTION.txt").write_text(
        "What is the total servicing cost for %s? Write the number, and "
        "nothing else, to answer.txt.\n" % site, encoding="utf-8")


def _v_answer(work: Path, keyed: Path) -> Verdict:
    note = ("exact numeric match; the figure exists in no single source and "
            "the third source is a decoy containing no numbers")
    if missing(work, "answer.txt"):
        return Verdict(False, {}, ("answer.txt was not produced",), note, 0.0)
    want = read_json(keyed / "want.json")
    raw = (work / "answer.txt").read_text(encoding="utf-8").strip()
    digits = "".join(ch for ch in raw if ch.isdigit() or ch == ".")
    try:
        got = float(digits) if digits else None
    except ValueError:
        got = None
    ok = got is not None and abs(got - want["answer"]) < 1e-9
    return Verdict(ok, {"expected": float(want["answer"]),
                        "got": float(got) if got is not None else -1.0},
                   () if ok else ("expected %s, got %r" % (want["answer"], raw[:40]),),
                   note, 0.0)


bounded_answer = Generator(
    key="t1.bounded_answer", family="research", level="DL1",
    difficulty=Difficulty(horizon=2, uncertainty=2, ambiguity=1),
    loss=Loss(value=1.0, c_detect=0.4),
    prompt="Read QUESTION.txt and answer it from the files in sources/.",
    deliverables=("answer.txt",),
    verifier_note=("exact numeric match; the answer requires combining two of "
                   "three sources and one source is a decoy"),
    build=_b_answer, verify=_v_answer,
)

ALL = (request_timeout, clean_dataset, bounded_answer)
