"""DL3 classes with a plausible wrong reading that survives a careful model.

The first suite saturated. Two frontier executors scored identically on it and
failed only one class, which means the benchmark was measuring its own ceiling
rather than the systems under test. A suite discriminates only where a
competent attempt can still be wrong.

What makes a class discriminating is not that it is laborious. It is that the
**obvious implementation is defensible and incorrect**, the specification says
plainly which reading is intended, and the difference is externally checkable to
the last row. Each class here names its own trap in the task text --- these are
not gotchas, and a model that reads carefully should pass. That is the point:
what is being measured is whether careful reading survives contact with a
familiar-looking problem.

Three traps, chosen because each is a real defect that ships:

* **causal order** --- events carry timestamps and a parent pointer, and clock
  skew puts them in different orders. Sorting by time is the reflex.
* **civil days across a DST change** --- one local day has 23 hours and another
  25, so bucketing by UTC date silently misfiles the events near midnight.
* **Unicode identity** --- identifiers that render identically differ in bytes,
  so an exact comparison keeps duplicates that a person would call one thing.
"""
from __future__ import annotations

import csv
import json
import random
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Sequence, Tuple
from zoneinfo import ZoneInfo

from ..spec import Difficulty, Loss
from ..verify import Verdict, missing, read_json
from .base import Generator

#: Shared T3 shape: strategy choice, a stated constraint that changes the
#: answer, and verification that is exact.
_T3 = Difficulty(horizon=3, coordination=2, uncertainty=3, ambiguity=2,
                 tooling=2, verification=2, novelty=1)


# ------------------------------------------------------------ causal order

def _replay(ops: Sequence[Dict], fields: Sequence[str]) -> Dict[str, int]:
    st = {f: 0 for f in fields}
    for o in ops:
        if o["op"] == "set":
            st[o["field"]] = o["value"]
        else:
            st[o["field"]] += o["value"]
    return st


def _b_causal(work: Path, keyed: Path, rng: random.Random) -> None:
    """Build an instance and *check that it contains its own trap*.

    `inc` is commutative, so a timestamp-sorted replay differs from a causal one
    only when the skew reorders a `set` against an `inc` on the same field. With
    random skew that sometimes does not happen, and the instance then scores a
    naive solver correct -- an instance of this class that is not an instance of
    this class. So the two replays are compared at build time and the skews are
    redrawn until they disagree.

    The general rule this is an instance of: a generator whose trap is
    probabilistic must verify the trap fired, or the suite silently fills with
    instances that discriminate nothing.
    """
    fields = ["alpha", "beta", "gamma"]
    base = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)

    for attempt in range(200):
        order: List[Dict] = []
        parent = None
        for i in range(24):
            f = rng.choice(fields)
            kind = "set" if rng.random() < 0.35 else "inc"
            val = rng.randint(1, 9) if kind == "inc" else rng.randint(10, 99)
            op = {"id": "op%02d" % i, "parent": parent, "op": kind,
                  "field": f, "value": val}
            order.append(op)
            parent = op["id"]

        # Clock skew: each machine stamps with its own drifting clock.
        for i, op in enumerate(order):
            skew = rng.choice([-140, -90, -45, -20, 5, 15, 40, 75, 120])
            op["timestamp"] = (base + timedelta(seconds=i * 30 + skew)).isoformat()

        causal = _replay(order, fields)
        by_time = _replay(sorted(order, key=lambda o: o["timestamp"]), fields)
        if causal != by_time:
            break
    else:                                   # pragma: no cover - 200 misses
        raise RuntimeError("could not build a causal_order instance whose "
                           "timestamp order disagrees with its parent chain")

    shuffled = list(order)
    rng.shuffle(shuffled)
    (work / "ops.jsonl").write_text(
        "\n".join(json.dumps(o, sort_keys=True) for o in shuffled) + "\n",
        encoding="utf-8")
    (keyed / "expected.json").write_text(json.dumps(causal, sort_keys=True),
                                         encoding="utf-8")
    # Recorded so a reader of the instance can see the trap is present.
    (keyed / "trap.json").write_text(json.dumps(
        {"causal": causal, "by_timestamp": by_time,
         "fields_that_differ": sorted(k for k in causal if causal[k] != by_time[k])},
        sort_keys=True), encoding="utf-8")

    (work / "SPEC.md").write_text(
        "# Replay\n\n`ops.jsonl` holds updates from several machines, one per\n"
        "line and in no particular order. Each carries an `id`, the `parent`\n"
        "id of the update it followed, a `timestamp`, and an operation:\n"
        "`set` replaces a field's value, `inc` adds to it.\n\n"
        "**Apply them in causal order** --- each update after the one its\n"
        "`parent` names. The single update with `parent: null` is first.\n\n"
        "The machines' clocks are not synchronised, so the timestamps do not\n"
        "agree with the causal order. Write the final state to `state.json`\n"
        "as an object mapping each field to its value.\n", encoding="utf-8")


def _v_causal(work: Path, keyed: Path) -> Verdict:
    note = ("exact equality of the final state against a replay in parent-chain "
            "order; timestamps disagree with causal order on about a third of "
            "the events, so a time-sorted replay produces different numbers")
    if missing(work, "state.json"):
        return Verdict(False, {}, ("state.json was not produced",), note, 0.0)
    try:
        got = read_json(work / "state.json")
    except Exception as e:
        return Verdict(False, {}, ("state.json is not valid JSON: %s" % e,), note, 0.0)
    want = read_json(keyed / "expected.json")
    wrong = [k for k in want if got.get(k) != want[k]]
    return Verdict(not wrong,
                   {"fields_correct": float(len(want) - len(wrong))},
                   tuple("%s: expected %r, got %r" % (k, want[k], got.get(k))
                         for k in wrong), note, 0.0)


causal_order = Generator(
    key="t3.causal_order", family="data", level="DL3",
    difficulty=_T3, loss=Loss(value=1.0, c_detect=0.5, c_undo=0.3),
    prompt="Read SPEC.md and produce what it asks for.",
    deliverables=("state.json",),
    verifier_note=("exact final state; a replay sorted by timestamp instead of "
                   "by the parent chain gives different values"),
    build=_b_causal, verify=_v_causal,
)


# --------------------------------------------- civil days across a DST change

def _b_dst(work: Path, keyed: Path, rng: random.Random) -> None:
    tz = ZoneInfo("Europe/Berlin")
    # The October change: 03:00 local goes back to 02:00, so that civil day has
    # 25 hours. Events cluster around local midnight, where the two bucketings
    # disagree.
    start = datetime(2026, 10, 23, 0, 0, tzinfo=tz)
    rows: List[Tuple[str, float]] = []
    totals: Dict[str, float] = {}
    for day in range(5):
        for _ in range(rng.randint(6, 10)):
            local = (start + timedelta(days=day,
                                       hours=rng.choice([0, 1, 2, 12, 22, 23]),
                                       minutes=rng.randint(0, 59)))
            amt = round(rng.uniform(5, 200), 2)
            utc = local.astimezone(timezone.utc)
            rows.append((utc.strftime("%Y-%m-%dT%H:%M:%SZ"), amt))
            key = local.date().isoformat()
            totals[key] = round(totals.get(key, 0.0) + amt, 2)
    rng.shuffle(rows)
    with (work / "events.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["timestamp_utc", "amount"])
        w.writerows(rows)
    (keyed / "expected.json").write_text(
        json.dumps({k: round(v, 2) for k, v in totals.items()}, sort_keys=True),
        encoding="utf-8")
    (work / "SPEC.md").write_text(
        "# Daily totals\n\n`events.csv` timestamps are UTC, with a trailing `Z`.\n\n"
        "Total the amounts **per civil day in Europe/Berlin**, and write\n"
        "`totals.json` mapping each local date (`YYYY-MM-DD`) to its total,\n"
        "rounded to 2 decimal places.\n\n"
        "The clocks change during this period, so one local day does not have\n"
        "24 hours. A day with no events does not appear.\n", encoding="utf-8")


def _v_dst(work: Path, keyed: Path) -> Verdict:
    note = ("per-day totals to 0.01 against local civil days in Europe/Berlin, "
            "across a DST change where one day has 25 hours. Bucketing by UTC "
            "date misfiles the events near local midnight and shifts the day "
            "boundaries by an hour on one side of the change")
    if missing(work, "totals.json"):
        return Verdict(False, {}, ("totals.json was not produced",), note, 0.0)
    try:
        got = read_json(work / "totals.json")
    except Exception as e:
        return Verdict(False, {}, ("totals.json is not valid JSON: %s" % e,), note, 0.0)
    want = read_json(keyed / "expected.json")
    reasons, worst = [], 0.0
    for day, v in sorted(want.items()):
        g = float(got.get(day, -1.0))
        worst = max(worst, abs(g - v))
        if abs(g - v) > 0.01:
            reasons.append("%s: expected %.2f, got %s" % (day, v, got.get(day)))
    extra = sorted(set(got) - set(want))
    if extra:
        reasons.append("days that should not exist: %s" % ", ".join(extra[:4]))
    return Verdict(not reasons,
                   {"days_expected": float(len(want)), "worst_error": worst},
                   tuple(reasons[:5]), note, 0.0)


dst_days = Generator(
    key="t3.dst_daily_totals", family="data", level="DL3",
    difficulty=_T3, loss=Loss(value=1.0, c_detect=0.6, c_undo=0.3),
    prompt="Read SPEC.md and produce what it asks for.",
    deliverables=("totals.json",),
    verifier_note=("per-day totals across a DST change; UTC-date bucketing "
                   "misfiles events near local midnight"),
    build=_b_dst, verify=_v_dst,
)


# ---------------------------------------------------------- Unicode identity

_ZW = ["​", "‌", "‍", "﻿"]


def _b_unicode(work: Path, keyed: Path, rng: random.Random) -> None:
    stems = ["café", "naïve", "Ångström", "Zoë", "Müller", "señor", "fiancée"]
    rows: List[Tuple[str, str]] = []
    seen_norm: Dict[str, str] = {}
    kept: List[Tuple[str, str]] = []

    def fold(s: str) -> str:
        s = "".join(ch for ch in s if ch not in _ZW)
        return unicodedata.normalize("NFKC", s)

    for i in range(18):
        stem = rng.choice(stems)
        variant = stem
        r = rng.random()
        if r < 0.35:                       # decomposed form: same on screen
            variant = unicodedata.normalize("NFD", stem)
        elif r < 0.6:                      # an invisible character
            pos = rng.randint(1, max(1, len(stem) - 1))
            variant = stem[:pos] + rng.choice(_ZW) + stem[pos:]
        label = "row%02d" % i
        rows.append((variant, label))
        f = fold(variant)
        if f not in seen_norm:             # first occurrence wins
            seen_norm[f] = label
            kept.append((variant, label))

    with (work / "ids.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["identifier", "label"])
        w.writerows(rows)
    (keyed / "expected.json").write_text(
        json.dumps([{"identifier": a, "label": b} for a, b in kept]),
        encoding="utf-8")
    (work / "RULES.md").write_text(
        "# Deduplicating identifiers\n\n"
        "Two identifiers are **the same identifier** when they are equal after\n"
        "both of these, in this order:\n\n"
        "1. removing any zero-width characters (U+200B, U+200C, U+200D, U+FEFF);\n"
        "2. Unicode NFKC normalisation.\n\n"
        "Some rows differ only in ways that do not show on screen.\n\n"
        "Keep the **first** occurrence of each identifier in file order, with\n"
        "its original spelling unchanged, and write `unique.json`: a JSON list\n"
        "of objects with keys `identifier` and `label`, in file order.\n",
        encoding="utf-8")


def _v_unicode(work: Path, keyed: Path) -> Verdict:
    note = ("exact list equality including order and the original spelling of "
            "each kept row. Some rows differ only by combining-character form "
            "or an invisible code point, so a byte-exact comparison keeps "
            "duplicates and a normalise-everything answer changes the spelling")
    if missing(work, "unique.json"):
        return Verdict(False, {}, ("unique.json was not produced",), note, 0.0)
    try:
        got = read_json(work / "unique.json")
    except Exception as e:
        return Verdict(False, {}, ("unique.json is not valid JSON: %s" % e,), note, 0.0)
    want = read_json(keyed / "expected.json")
    if not isinstance(got, list):
        return Verdict(False, {}, ("unique.json is not a list",), note, 0.0)
    reasons = []
    if len(got) != len(want):
        reasons.append("kept %d rows, expected %d" % (len(got), len(want)))
    for i, (a, b) in enumerate(zip(got, want)):
        if a.get("label") != b["label"]:
            reasons.append("row %d: expected label %s, got %r"
                           % (i, b["label"], a.get("label")))
            break
        if a.get("identifier") != b["identifier"]:
            reasons.append("row %d (%s): the spelling was altered; the original "
                           "must be kept" % (i, b["label"]))
            break
    return Verdict(not reasons,
                   {"rows_expected": float(len(want)), "rows_got": float(len(got))},
                   tuple(reasons), note, 0.0)


unicode_identity = Generator(
    key="t3.unicode_identity", family="data", level="DL3",
    difficulty=_T3, loss=Loss(value=1.0, c_detect=0.7, c_undo=0.3),
    prompt="Read RULES.md and produce what it asks for from ids.csv.",
    deliverables=("unique.json",),
    verifier_note=("exact list including order and original spelling; byte "
                   "comparison keeps duplicates, normalising the output "
                   "changes the spelling"),
    build=_b_unicode, verify=_v_unicode,
)

ALL = (causal_order, dst_days, unicode_identity)
