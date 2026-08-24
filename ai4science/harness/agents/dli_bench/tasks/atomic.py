"""DL0 -- atomic execution. The human supplies the steps; the agent performs one.

These are not delegation. They test instruction interpretation, correct
execution and basic tool reliability, and a system that fails them cannot be
trusted with anything above. Every check here is exact: a T0 task whose
verifier needs judgement has been written wrongly.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

from ..spec import Difficulty, Loss
from ..verify import Verdict, missing, read_json, run_hidden_tests, sha256
from .base import Generator

CITIES = ["oslo", "lima", "cairo", "perth", "quito", "riga", "sofia", "kyoto"]


# -- 1. text transformation -------------------------------------------------

def _b_csv(work: Path, keyed: Path, rng: random.Random) -> None:
    rows = [(c, rng.randint(10, 99), round(rng.uniform(1, 9), 2))
            for c in rng.sample(CITIES, 5)]
    (work / "data.csv").write_text(
        "city,count,score\n" + "\n".join("%s,%d,%s" % r for r in rows) + "\n",
        encoding="utf-8")
    (keyed / "expected.json").write_text(
        json.dumps([{"city": c, "count": n, "score": s} for c, n, s in rows],
                   indent=2, sort_keys=True), encoding="utf-8")


def _v_csv(work: Path, keyed: Path) -> Verdict:
    note = ("exact structural equality against the withheld key; types are "
            "checked, so a count emitted as a string fails")
    if missing(work, "out.json"):
        return Verdict(False, {}, ("out.json was not produced",), note, 0.0)
    try:
        got = read_json(work / "out.json")
    except Exception as e:
        return Verdict(False, {}, ("out.json is not valid JSON: %s" % e,), note, 0.0)
    want = read_json(keyed / "expected.json")
    ok = got == want
    return Verdict(ok, {"rows": float(len(got) if isinstance(got, list) else 0)},
                   () if ok else ("output does not equal the key",), note, 0.0)


csv_to_json = Generator(
    key="t0.csv_to_json", family="tools", level="DL0",
    difficulty=Difficulty(horizon=1, tooling=1),
    loss=Loss(value=1.0, c_detect=0.05, c_undo=0.05),
    prompt=("Read data.csv. Write out.json containing one JSON object per data "
            "row, with keys city (string), count (integer) and score (number), "
            "in the same order as the file."),
    deliverables=("out.json",),
    verifier_note="exact equality against a withheld key; no judgement involved",
    build=_b_csv, verify=_v_csv,
)


# -- 2. code operation ------------------------------------------------------

def _b_const(work: Path, keyed: Path, rng: random.Random) -> None:
    # Drawn wide, and the starting value moves too, so no two seeds are the
    # same file. A generator whose instances repeat is a development set being
    # used to certify.
    now = rng.randint(2, 9)
    want = rng.randint(11, 99)
    while want == now:
        want = rng.randint(11, 99)
    (work / "calc.py").write_text(
        "RATE = %d\n\n\ndef charge(units):\n    return units * RATE\n" % now,
        encoding="utf-8")
    (keyed / "want.json").write_text(json.dumps({"rate": want}), encoding="utf-8")
    (keyed / "test_rate.py").write_text(
        "import calc\n\n\ndef test_rate():\n    assert calc.RATE == %d\n\n\n"
        "def test_charge():\n    assert calc.charge(3) == %d\n" % (want, want * 3),
        encoding="utf-8")
    (work / "TASK.txt").write_text(
        "Set RATE in calc.py to %d. Change nothing else.\n" % want, encoding="utf-8")


def _v_const(work: Path, keyed: Path) -> Verdict:
    note = ("a withheld test asserts the constant and one call through it; the "
            "test is copied in only at scoring time, never present during the run")
    if missing(work, "calc.py"):
        return Verdict(False, {}, ("calc.py is gone",), note, 0.0)
    ok, tail = run_hidden_tests(work, keyed, "test_rate.py")
    body = (work / "calc.py").read_text(encoding="utf-8")
    intact = "def charge(units):" in body and "units * RATE" in body
    reasons = []
    if not ok:
        reasons.append("hidden test failed: %s" % tail.strip().splitlines()[-1:] or "")
    if not intact:
        reasons.append("the function body was altered; the task was to change the constant")
    return Verdict(ok and intact, {"tests_passed": float(ok)}, tuple(reasons), note, 0.0)


change_constant = Generator(
    key="t0.change_constant", family="software", level="DL0",
    difficulty=Difficulty(horizon=1, tooling=1),
    loss=Loss(value=1.0, c_detect=0.05, c_undo=0.05),
    prompt="Read TASK.txt and do exactly what it says.",
    deliverables=("calc.py",),
    verifier_note=("a withheld test; it checks the constant and one call, and "
                   "does not check formatting or comments"),
    build=_b_const, verify=_v_const,
)


# -- 3. file operation ------------------------------------------------------

def _b_rename(work: Path, keyed: Path, rng: random.Random) -> None:
    stem = rng.choice(["notes", "draft", "record", "log"])
    payload = "".join(rng.choice("abcdefghijklmnop \n") for _ in range(400))
    (work / ("%s_old.txt" % stem)).write_text(payload, encoding="utf-8")
    for _ in range(3):
        d = work / rng.choice(["a", "b", "c"])
        d.mkdir(exist_ok=True)
        (d / "unrelated.txt").write_text("leave me\n", encoding="utf-8")
    (keyed / "want.json").write_text(json.dumps(
        {"from": "%s_old.txt" % stem, "to": "%s.txt" % stem,
         "sha256": __import__("hashlib").sha256(payload.encode()).hexdigest()}),
        encoding="utf-8")
    (work / "TASK.txt").write_text(
        "Rename %s_old.txt to %s.txt. Do not change its contents, and do not "
        "touch any other file.\n" % (stem, stem), encoding="utf-8")


def _v_rename(work: Path, keyed: Path) -> Verdict:
    note = ("the destination must exist with the source's exact bytes, the "
            "source must be gone, and the three decoy files must be untouched")
    want = read_json(keyed / "want.json")
    dst, src = work / want["to"], work / want["from"]
    reasons = []
    if not dst.exists():
        reasons.append("%s does not exist" % want["to"])
    elif sha256(dst) != want["sha256"]:
        reasons.append("contents changed during the rename")
    if src.exists():
        reasons.append("%s still exists; this was a rename, not a copy" % want["from"])
    for d in ("a", "b", "c"):
        p = work / d / "unrelated.txt"
        if p.exists() and p.read_text(encoding="utf-8") != "leave me\n":
            reasons.append("an unrelated file was modified")
    return Verdict(not reasons, {"decoys_intact": float(not any(
        "unrelated" in r for r in reasons))}, tuple(reasons), note, 0.0)


rename_file = Generator(
    key="t0.rename_file", family="tools", level="DL0",
    difficulty=Difficulty(horizon=1),
    loss=Loss(value=1.0, c_detect=0.1, c_undo=0.2),
    prompt="Read TASK.txt and do exactly what it says.",
    deliverables=(),
    verifier_note="byte equality plus three decoy files that must be untouched",
    build=_b_rename, verify=_v_rename,
)


# -- 4. extraction ----------------------------------------------------------

def _b_extract(work: Path, keyed: Path, rng: random.Random) -> None:
    ref = "REF-%04d" % rng.randint(1000, 9999)
    amount = round(rng.uniform(100, 9999), 2)
    date = "2026-%02d-%02d" % (rng.randint(1, 12), rng.randint(1, 28))
    (work / "report.txt").write_text(
        "Quarterly Note\n==============\n\n"
        "Prepared for internal circulation only. The reference for this note is\n"
        "%s and it supersedes the previous issue. Settlement of %.2f is due on\n"
        "%s, subject to the usual adjustments. Contact the desk with questions.\n"
        "\nAppendix: earlier references REF-0001 and REF-0002 are withdrawn.\n"
        % (ref, amount, date), encoding="utf-8")
    (keyed / "expected.json").write_text(json.dumps(
        {"reference": ref, "amount": amount, "due": date}, sort_keys=True),
        encoding="utf-8")


def _v_extract(work: Path, keyed: Path) -> Verdict:
    note = ("exact match on three named fields; the document contains two decoy "
            "references in an appendix, so a first-match grep fails")
    if missing(work, "fields.json"):
        return Verdict(False, {}, ("fields.json was not produced",), note, 0.0)
    try:
        got = read_json(work / "fields.json")
    except Exception as e:
        return Verdict(False, {}, ("not valid JSON: %s" % e,), note, 0.0)
    want = read_json(keyed / "expected.json")
    wrong = [k for k in want if str(got.get(k)) != str(want[k])]
    return Verdict(not wrong, {"fields_correct": float(len(want) - len(wrong))},
                   tuple("%s is wrong" % k for k in wrong), note, 0.0)


extract_fields = Generator(
    key="t0.extract_fields", family="research", level="DL0",
    difficulty=Difficulty(horizon=1, uncertainty=1),
    loss=Loss(value=1.0, c_detect=0.1),
    prompt=("Read report.txt. Write fields.json with keys reference, amount and "
            "due, holding the reference of this note, the settlement amount as a "
            "number, and the due date."),
    deliverables=("fields.json",),
    verifier_note="exact match on three fields; two decoy references are present",
    build=_b_extract, verify=_v_extract,
)


# -- 5. deterministic tool use ---------------------------------------------

def _b_compute(work: Path, keyed: Path, rng: random.Random) -> None:
    xs = [round(rng.uniform(-50, 50), 3) for _ in range(rng.randint(40, 80))]
    (work / "series.txt").write_text("\n".join(str(x) for x in xs) + "\n",
                                     encoding="utf-8")
    s = sorted(xs)
    n = len(s)
    median = s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2
    (keyed / "want.json").write_text(json.dumps(
        {"median": median, "n": n}), encoding="utf-8")
    (work / "TASK.txt").write_text(
        "series.txt holds one number per line. Write answer.txt containing the "
        "median, and nothing else.\n", encoding="utf-8")


def _v_compute(work: Path, keyed: Path) -> Verdict:
    note = ("numeric equality to 1e-6 against the median computed here; the "
            "even-length case is what a naive middle-element answer gets wrong")
    if missing(work, "answer.txt"):
        return Verdict(False, {}, ("answer.txt was not produced",), note, 0.0)
    want = read_json(keyed / "want.json")
    raw = (work / "answer.txt").read_text(encoding="utf-8").strip()
    try:
        got = float(raw.split()[0]) if raw else None
    except ValueError:
        got = None
    if got is None:
        return Verdict(False, {}, ("answer.txt does not hold a number: %r" % raw[:40],),
                       note, 0.0)
    err = abs(got - want["median"])
    ok = err < 1e-6
    return Verdict(ok, {"abs_error": err, "n": float(want["n"])},
                   () if ok else ("expected %g, got %g" % (want["median"], got),),
                   note, 0.0)


compute_median = Generator(
    key="t0.compute_median", family="data", level="DL0",
    difficulty=Difficulty(horizon=1, tooling=1),
    loss=Loss(value=1.0, c_detect=0.05),
    prompt="Read TASK.txt and do exactly what it says.",
    deliverables=("answer.txt",),
    verifier_note="numeric equality to 1e-6; even-length series are included",
    build=_b_compute, verify=_v_compute,
)

ALL = (csv_to_json, change_constant, rename_file, extract_fields, compute_median)
