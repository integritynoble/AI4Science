"""DL5 -- discovery, where the solution method is not known in advance.

The hard part of benchmarking this level is that a famous unsolved problem has
no ground truth, and a solved one has an answer in the training data. The way
out is a **sealed** task: the evaluator knows the mechanism because the
evaluator generated it, and the agent has never seen it because it did not
exist until the seed was drawn.

The graded question is not "did it fit the data". Any flexible model fits data.
It is **does it predict outside the range it was given** -- because only a
correct mechanism extrapolates, and memorising cannot. The bar is set against a
nearest-neighbour baseline computed on the same split, so the threshold is a
property of the instance rather than a number someone chose.

A stated mechanism is also collected, and is deliberately *not* machine-graded:
grading prose here would need a judge, and a judge is another verifier whose
false-pass rate nobody knows. The extrapolation error is the finding; the
statement is evidence for a human reading the result.
"""
from __future__ import annotations

import json
import math
import random
from pathlib import Path

from ..spec import Difficulty, Loss
from ..verify import Verdict, missing, read_json
from .base import Generator

#: Mechanism families. Each is a closed form with parameters drawn per seed, so
#: two seeds are two different laws rather than two samples of one.
FAMILIES = ("damped_wave", "inverse_square_pair", "saturating_growth",
            "regime_switch")


def _law(kind: str, p: dict):
    if kind == "regime_switch":
        # Two mechanisms and a boundary, all three of which have to be
        # recovered. The three single-form families are recognisable on sight
        # by anything that has seen a physics textbook, and a frontier executor
        # passes all of them; this one cannot be matched to a remembered shape,
        # because the shape depends on a latent boundary that is not in the
        # observable. Everything else about the task is unchanged: one fixed
        # rule, the same noise, the same extrapolation bar.
        lo = _law(p["lo_kind"], p["lo"])
        hi = _law(p["hi_kind"], p["hi"])
        u, v, t = p["u"], p["v"], p["t"]
        return lambda a, b: lo(a, b) if (u * a + v * b) < t else hi(a, b)
    if kind == "damped_wave":
        return lambda a, b: p["A"] * math.exp(-p["lam"] * a) * math.sin(p["k"] * b) + p["c"]
    if kind == "inverse_square_pair":
        return lambda a, b: p["G"] / ((a - p["x0"]) ** 2 + (b - p["y0"]) ** 2 + p["eps"]) + p["c"]
    return lambda a, b: p["L"] / (1.0 + math.exp(-p["k"] * (a - p["m"]))) + p["B"] * b + p["c"]


def _params(kind: str, rng: random.Random) -> dict:
    if kind == "regime_switch":
        singles = ("damped_wave", "inverse_square_pair", "saturating_growth")
        lo_kind, hi_kind = rng.sample(singles, 2)
        return {"lo_kind": lo_kind, "lo": _params(lo_kind, rng),
                "hi_kind": hi_kind, "hi": _params(hi_kind, rng),
                "u": round(rng.uniform(0.5, 1.5), 3),
                "v": round(rng.uniform(0.5, 1.5), 3),
                "t": round(rng.uniform(4.0, 7.0), 3)}
    if kind == "damped_wave":
        return {"A": round(rng.uniform(2, 6), 3), "lam": round(rng.uniform(0.1, 0.5), 3),
                "k": round(rng.uniform(0.8, 2.5), 3), "c": round(rng.uniform(-2, 2), 3)}
    if kind == "inverse_square_pair":
        return {"G": round(rng.uniform(5, 25), 3), "x0": round(rng.uniform(-1, 1), 3),
                "y0": round(rng.uniform(-1, 1), 3), "eps": 0.5,
                "c": round(rng.uniform(-1, 1), 3)}
    return {"L": round(rng.uniform(4, 10), 3), "k": round(rng.uniform(0.6, 2.0), 3),
            "m": round(rng.uniform(1, 4), 3), "B": round(rng.uniform(-1.5, 1.5), 3),
            "c": round(rng.uniform(-2, 2), 3)}


def _regime_of(p, a, b):
    return (p["u"] * a + p["v"] * b) >= p["t"]


def _both_regimes_present(p, points, floor=0.15):
    """A boundary that is on one side of every observation is not discoverable,
    and a task that grades an undiscoverable boundary is unfair rather than
    hard. Checked on the actual points, not argued from the ranges.
    """
    n = len(points)
    hot = sum(1 for q in points if _regime_of(p, q[0], q[1]))
    return floor <= hot / n <= 1.0 - floor


def _b_law(work: Path, keyed: Path, rng: random.Random) -> None:
    kind = rng.choice(FAMILIES)
    p = _params(kind, rng)
    f = _law(kind, p)

    # Training range. The agent may measure anywhere inside it.
    lo, hi = 0.0, 5.0
    train = []
    for _ in range(400):
        a, b = rng.uniform(lo, hi), rng.uniform(lo, hi)
        noise = rng.gauss(0, 0.02 * max(1.0, abs(f(a, b))))
        train.append({"a": round(a, 5), "b": round(b, 5), "y": round(f(a, b) + noise, 6)})
    if kind == "regime_switch":
        # Redraw the boundary until both regimes are genuinely represented in
        # what the agent gets to see. Without this the instance sometimes hands
        # over a single regime and grades the other one.
        for _ in range(200):
            if _both_regimes_present(p, [(t["a"], t["b"]) for t in train]):
                break
            p["t"] = round(rng.uniform(4.0, 7.0), 3)
        else:                                  # pragma: no cover - safety valve
            raise RuntimeError("could not place a discoverable boundary")
        f = _law(kind, p)
        for t in train:
            noise = rng.gauss(0, 0.02 * max(1.0, abs(f(t["a"], t["b"]))))
            t["y"] = round(f(t["a"], t["b"]) + noise, 6)
    (work / "observations.json").write_text(json.dumps(train), encoding="utf-8")

    # The held-out grid is OUTSIDE the training box on at least one coordinate.
    grid = []
    for _ in range(120):
        if rng.random() < 0.5:
            a, b = rng.uniform(hi, hi + 3.0), rng.uniform(lo, hi)
        else:
            a, b = rng.uniform(lo, hi), rng.uniform(hi, hi + 3.0)
        grid.append({"a": round(a, 5), "b": round(b, 5)})
    (work / "predict_at.json").write_text(json.dumps(grid), encoding="utf-8")

    truth = [round(f(g["a"], g["b"]), 6) for g in grid]

    # The baseline the candidate must beat: nearest neighbour in the training
    # set. It is what memorising achieves, and it is computed on this instance
    # rather than assumed.
    def nn(a, b):
        best, bd = None, None
        for t in train:
            d = (t["a"] - a) ** 2 + (t["b"] - b) ** 2
            if bd is None or d < bd:
                bd, best = d, t["y"]
        return best

    nn_pred = [nn(g["a"], g["b"]) for g in grid]
    nn_rmse = math.sqrt(sum((x - y) ** 2 for x, y in zip(nn_pred, truth)) / len(truth))
    spread = math.sqrt(sum((t - sum(truth) / len(truth)) ** 2 for t in truth) / len(truth))

    (keyed / "truth.json").write_text(json.dumps(
        {"kind": kind, "params": p, "y": truth,
         "nn_rmse": nn_rmse, "spread": spread}), encoding="utf-8")
    (work / "GOAL.md").write_text(
        "# Goal\n\n`observations.json` holds measurements `(a, b, y)` from a "
        "process with one fixed generating rule. The measurements are noisy at "
        "about 2%.\n\n"
        "1. Work out the rule.\n"
        "2. Write `mechanism.txt` stating it in whatever form you find clearest.\n"
        "3. Write `predictions.json`: a JSON list of numbers, one for each entry "
        "of `predict_at.json`, in the same order.\n\n"
        "The points in `predict_at.json` lie **outside** the range you were "
        "measured over. Interpolating the observations will not reach them.\n",
        encoding="utf-8")


def _v_law(work: Path, keyed: Path) -> Verdict:
    note = ("root-mean-square error on 120 held-out points OUTSIDE the "
            "training box, against a nearest-neighbour baseline computed on "
            "this same instance. Passing requires 25% of the baseline error or "
            "less. The stated mechanism in mechanism.txt is collected but NOT "
            "machine-graded: grading it would need a judge, and a judge is "
            "another verifier with an unknown false-pass rate")
    if missing(work, "predictions.json"):
        return Verdict(False, {}, ("predictions.json was not produced",), note, 0.0)
    key = read_json(keyed / "truth.json")
    truth = key["y"]
    try:
        got = read_json(work / "predictions.json")
        got = [float(x) for x in got]
    except Exception as e:
        return Verdict(False, {}, ("predictions.json unreadable: %s" % e,), note, 0.0)
    if len(got) != len(truth):
        return Verdict(False, {"n_expected": float(len(truth)), "n_got": float(len(got))},
                       ("expected %d predictions, got %d" % (len(truth), len(got)),),
                       note, 0.0)
    rmse = math.sqrt(sum((a - b) ** 2 for a, b in zip(got, truth)) / len(truth))
    bar = 0.25 * key["nn_rmse"]
    stated = (work / "mechanism.txt").exists()
    reasons = []
    if rmse > bar:
        reasons.append("extrapolation RMSE %.4g exceeds the bar %.4g (25%% of the "
                       "%.4g nearest-neighbour baseline)" % (rmse, bar, key["nn_rmse"]))
    if not stated:
        reasons.append("mechanism.txt was not written; the rule must be stated, "
                       "not only used")
    return Verdict(not reasons,
                   {"extrapolation_rmse": rmse, "baseline_rmse": key["nn_rmse"],
                    "bar": bar, "target_spread": key["spread"],
                    "mechanism_stated": float(stated)},
                   tuple(reasons), note, 0.0)


hidden_law = Generator(
    key="t5.hidden_law", family="research", level="DL5",
    difficulty=Difficulty(horizon=3, uncertainty=4, ambiguity=2, tooling=2,
                          verification=2, novelty=4),
    loss=Loss(value=1.0, c_detect=0.3),
    prompt="Read GOAL.md.",
    deliverables=("predictions.json", "mechanism.txt"),
    verifier_note=("held-out extrapolation error against a per-instance "
                   "nearest-neighbour baseline; the stated mechanism is "
                   "recorded but not machine-graded"),
    build=_b_law, verify=_v_law,
)

ALL = (hidden_law,)
