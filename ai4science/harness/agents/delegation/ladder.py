"""The standardized harness ladder HG0-HG3, and the Harness Scaling Curve.

v1.2 §16.3 defines `HSC_m = {(k, HLIS(m, HG_k))}` and says the curve itself
should remain a primary result because it exposes saturation and non-monotonic
behaviour. It is a specification: the ladder is described and not built, so no
curve has been measured.

This builds the first four rungs concretely, from mechanisms that already exist
in this package, so that one frozen model can be run across them and the curve
computed rather than drawn.

    HG0  the model, bounded tools, an evidence log. One attempt. NO acceptance
         step -- the run hands back whatever it produced.
    HG1  + persistent state, and a criterion registered before the work exists,
         accepted by a separate process. Still one attempt.
    HG2  + a snapshot before the first mutation, and a retry on independent
         rejection with the failed check named.
    HG3  + failure classification, an evidence-based competence model, and
         routing across executors.

Each rung is strictly a superset of the one below, which is the property that
makes the curve interpretable: a difference between rungs is attributable to the
mechanism that was added.

**HG0 needs care.** A harness with no acceptance step cannot report success at
all -- everything it produces is asserted. So HG0's score is computed by the
benchmark's own verifier from outside, which is exactly what a contemporary
leaderboard does, and is the honest baseline: it is the configuration today's
benchmarks measure.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class Rung:
    """One generation of the standardized ladder."""

    k: int
    name: str
    mechanisms: Tuple[str, ...]
    #: Registers acceptance criteria before the work, and accepts elsewhere.
    acceptance: bool
    #: Snapshots before mutating and can restore.
    reversible: bool
    max_attempts: int
    #: Classifies failures and may move work to another executor.
    routes: bool
    note: str


LADDER: Tuple[Rung, ...] = (
    Rung(0, "HG0",
         ("the model", "bounded tools", "an evidence log"),
         acceptance=False, reversible=False, max_attempts=1, routes=False,
         note="What a contemporary leaderboard measures. One attempt, and "
              "whatever comes back is the answer, because nothing here can "
              "accept or refuse it."),
    Rung(1, "HG1",
         ("persistent state", "a criterion registered before the work",
          "acceptance in a separate process"),
         acceptance=True, reversible=False, max_attempts=1, routes=False,
         note="The rung that makes any claim reportable. It does not make the "
              "model better; it makes the result checkable, so wrong work stops "
              "being returned as done."),
    Rung(2, "HG2",
         ("a snapshot before the first mutation", "restore on rejection",
          "one retry with the failed check named"),
         acceptance=True, reversible=True, max_attempts=3, routes=False,
         note="The first rung that can convert a detected failure into a "
              "correction, and therefore the first that needs the model to "
              "cooperate."),
    Rung(3, "HG3",
         ("failure classification by kind", "an evidence-based competence model",
          "routing across executors"),
         acceptance=True, reversible=True, max_attempts=4, routes=True,
         note="Retrying becomes re-routing: a specification failure returns to "
              "the contract, and the second failure of one executor is called "
              "capability rather than bad luck."),
)

BY_NAME: Dict[str, Rung] = {r.name: r for r in LADDER}


# --------------------------------------------------------------------------
# The delegation surface, and the score v1.2 computes from it
# --------------------------------------------------------------------------

#: Weight per difficulty band. v1.2 §13.2 requires w_t to increase with T and to
#: be predeclared. Doubling per band is the simplest rule that does that, and it
#: is fixed here before any run.
W_T: Dict[str, float] = {"T0": 1.0, "T1": 2.0, "T2": 4.0, "T3": 8.0,
                         "T4": 16.0, "T5": 32.0, "T6": 64.0}

#: Weight per intervention budget, increasing as required human cognition falls.
V_H: Dict[str, float] = {"H0": 6.0, "H1": 5.0, "H2": 4.0, "H3": 3.0,
                         "H4": 2.0, "H5": 1.0}


def delegation_surface_score(surface: Dict[Tuple[str, str], float]) -> float:
    """A_DI from §13.2: the w_t v_h weighted mean of S_A(T,H)."""
    num = den = 0.0
    for (t, h), s in surface.items():
        w = W_T.get(t, 1.0) * V_H.get(h, 1.0)
        num += w * s
        den += w
    return (num / den) if den else 0.0


def frontier(surface: Dict[Tuple[str, str], float], h: str, p: float) -> Optional[str]:
    """F_A(H,p) = the hardest band held at reliability p -- reported beside any
    scalar, because a scalar must never hide the T/H tradeoff."""
    bands = [t for (t, hh), s in surface.items() if hh == h and s >= p]
    return max(bands, key=lambda b: list(W_T).index(b)) if bands else None


@dataclass
class RungResult:
    rung: str
    episodes: int
    #: (band, budget) -> verified success rate
    surface: Dict[Tuple[str, str], float] = field(default_factory=dict)
    #: Work handed back as done that the benchmark rejects.
    false_completions: int = 0
    held_back: int = 0
    attempts: int = 0
    seconds: float = 0.0

    @property
    def a_di(self) -> float:
        return delegation_surface_score(self.surface)

    @property
    def hlis_di(self) -> float:
        """HLIS restricted to the delegation coordinate.

        NOT a full HLIS. v1.2's HLIS is a geometric mean over C, I, DI and SA
        (plus O for organizations); only DI is instrumented here. Reported under
        its own name so it is never mistaken for the whole score.
        """
        return 100.0 * self.a_di


@dataclass
class Curve:
    """The Harness Scaling Curve, and the summaries v1.2 derives from it."""

    model: str
    rungs: List[RungResult] = field(default_factory=list)
    ladder_id: str = "dli-ladder/HG0-HG3@2026-08-25"

    def hsc(self) -> List[Tuple[int, float]]:
        return [(BY_NAME[r.rung].k, r.hlis_di) for r in self.rungs]

    @property
    def hil_ceiling(self) -> float:
        return max((v for _, v in self.hsc()), default=0.0)

    @property
    def hil_auc(self) -> float:
        vals = [v for _, v in self.hsc()]
        return sum(vals) / len(vals) if vals else 0.0

    @property
    def harness_gain(self) -> float:
        vals = dict(self.hsc())
        return self.hil_ceiling - vals.get(0, 0.0)

    @property
    def harnessability(self) -> float:
        return max(0.0, self.harness_gain)

    def hil_score_v12(self) -> float:
        """The composite exactly as v1.2 §14.3 proposes it."""
        return (0.55 * self.hil_auc + 0.35 * self.hil_ceiling
                + 0.10 * self.harnessability)

    def report(self) -> str:
        L = ["Harness Scaling Curve", "=" * 21, "",
             "model:  %s" % self.model, "ladder: %s" % self.ladder_id, "",
             "%-5s %-9s %8s %8s %10s %9s %8s"
             % ("rung", "episodes", "A_DI", "HLIS_DI", "false-done", "held", "attempts"),
             "-" * 66]
        for r in self.rungs:
            L.append("%-5s %-9d %8.3f %8.1f %10d %9d %8d"
                     % (r.rung, r.episodes, r.a_di, r.hlis_di,
                        r.false_completions, r.held_back, r.attempts))
        L += ["", "curve: " + " -> ".join("HG%d %.1f" % kv for kv in self.hsc()), "",
              "HIL-Ceiling   %6.1f" % self.hil_ceiling,
              "HIL-AUC       %6.1f" % self.hil_auc,
              "Harness Gain  %6.1f" % self.harness_gain,
              "HIL-Score     %6.1f   (v1.2 §14.3: .55 AUC + .35 Ceiling + .10 Harnessability)"
              % self.hil_score_v12(),
              "",
              "HLIS_DI is the delegation coordinate only. A full HLIS is a",
              "geometric mean over C, I, DI and SA; the other three are not",
              "instrumented here, so this is a curve through one coordinate."]
        return "\n".join(L)
