"""What a claimed improvement has to survive before it is one.

The imaging agent already scores candidates on held-out scenes through the
control plane and takes the best. That is right, and it is not enough for a
result anyone should act on: the best of N runs is the commonest way a real
improvement claim turns out to be nothing, and it is the easiest thing for an
autonomous agent to do without intending to. It keeps the run that looked good.

So a candidate here does not become an improvement by winning. It becomes one by
surviving six checks, and `Improvement.verdict()` reports which it failed rather
than returning a bare False — a refusal a researcher cannot act on has refused
nothing.

The seed rule is the load-bearing one. In one of these fields a defended,
statistically corrected effect is **+0.023 against a ±0.027 seed spread** — the
effect is smaller than the noise of a single run. Against that, "it improved"
means nothing without the whole seed set, and `seeds` holds every one, including
the ones that went the wrong way.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

#: When nothing clears the bar, this is the correct output — not silence, and
#: not the best of a bad set. A fortnight of these is a real result about the
#: method rather than a failure of the agent.
NO_CHANGE = "no-change"


@dataclass
class SeedResult:
    seed: int
    baseline: float
    candidate: float

    @property
    def delta(self) -> float:
        return self.candidate - self.baseline

    @property
    def positive(self) -> bool:
        return self.delta > 0


@dataclass
class Improvement:
    """One candidate, and the evidence for it."""

    agent: str
    candidate: str
    metric: str
    #: Every seed run, not the ones that helped.
    seeds: List[SeedResult] = field(default_factory=list)
    baseline_reproduced: bool = False
    #: Was the comparison made on data the candidate was never chosen against?
    held_out: bool = False
    #: How many things were tried in the campaign this candidate came from.
    comparisons: int = 1
    #: p-value, already corrected for `comparisons` if the domain uses one.
    corrected_p: Optional[float] = None
    #: Why it is better. A number with no mechanism is a lead, not a finding.
    mechanism: str = ""
    #: The independent verifier's call, on evidence, without the agent's summary.
    verifier_passed: Optional[bool] = None
    #: Dimensions whose partner is missing (from SelfModel.paired_gaps()).
    paired_gaps: Tuple[str, ...] = ()
    alpha: float = 0.05

    # --------------------------------------------------------------- numbers

    @property
    def n(self) -> int:
        return len(self.seeds)

    @property
    def mean_delta(self) -> Optional[float]:
        return (sum(s.delta for s in self.seeds) / self.n) if self.seeds else None

    @property
    def spread(self) -> Optional[float]:
        """Sample standard deviation of the per-seed delta."""
        if self.n < 2:
            return None
        m = self.mean_delta
        return math.sqrt(sum((s.delta - m) ** 2 for s in self.seeds) / (self.n - 1))

    @property
    def seeds_positive(self) -> int:
        return sum(1 for s in self.seeds if s.positive)

    @property
    def smaller_than_noise(self) -> Optional[bool]:
        """The check this whole module exists for. True when the effect is
        smaller than the run-to-run spread it was measured against."""
        m, sd = self.mean_delta, self.spread
        if m is None or sd is None:
            return None
        return abs(m) < sd

    # --------------------------------------------------------------- verdict

    def failures(self) -> List[str]:
        out: List[str] = []
        if not self.baseline_reproduced:
            out.append("the baseline was never reproduced here — the comparison "
                       "is against a number from a paper, not a run")
        if not self.held_out:
            out.append("not held out — the candidate was chosen against the data "
                       "it is being judged on")
        if self.n < 2:
            out.append("fewer than two seeds: %d. A single run cannot tell an "
                       "effect from its own noise" % self.n)
        else:
            if self.smaller_than_noise:
                out.append("the effect (%.4g) is smaller than the seed spread "
                           "(%.4g) — this is the seed lottery, not a result"
                           % (self.mean_delta, self.spread))
            if self.seeds_positive != self.n:
                # Not a failure by itself — it is honest, and must be *said*.
                pass
        if self.comparisons > 1 and self.corrected_p is None:
            out.append("%d things were tried and no corrected statistic was "
                       "reported" % self.comparisons)
        if self.corrected_p is not None and self.corrected_p > self.alpha:
            out.append("corrected p = %.3g, above alpha = %.3g"
                       % (self.corrected_p, self.alpha))
        if not self.mechanism.strip():
            out.append("no mechanism — a number with no account of why is a lead "
                       "for a person to follow, not a finding")
        if self.verifier_passed is not True:
            out.append("the independent verifier did not pass it"
                       if self.verifier_passed is False
                       else "the independent verifier has not judged it")
        for gap in self.paired_gaps:
            out.append("%s — the partner metric is unmeasured, and this one "
                       "cannot be read without it" % gap)
        return out

    def survives(self) -> bool:
        return not self.failures()

    def verdict(self) -> Dict[str, object]:
        f = self.failures()
        return {"agent": self.agent, "candidate": self.candidate,
                "metric": self.metric, "survives": not f,
                "mean_delta": self.mean_delta, "spread": self.spread,
                "seeds": "%d/%d positive" % (self.seeds_positive, self.n),
                "failures": f}

    # ---------------------------------------------------------------- render

    def report(self) -> str:
        L = ["%s / %s on %s" % (self.agent, self.candidate, self.metric)]
        if self.seeds:
            L.append("  %d seeds, %d positive — every seed below, including the "
                     "ones that went the wrong way:"
                     % (self.n, self.seeds_positive))
            for s in sorted(self.seeds, key=lambda s: s.seed):
                L.append("    seed %-5d %8.4g → %8.4g   %+.4g"
                         % (s.seed, s.baseline, s.candidate, s.delta))
            m, sd = self.mean_delta, self.spread
            L.append("    mean %+.4g%s" % (m, ("  spread %.4g" % sd) if sd else ""))
        else:
            L.append("  no seeds run — unmeasured")
        f = self.failures()
        if f:
            L.append("  NOT an improvement:")
            L += ["    - %s" % x for x in f]
        else:
            L.append("  survives every check — %s" % self.mechanism)
        return "\n".join(L)


def no_change(agent: str, *, because: str) -> Dict[str, object]:
    """The honest output when nothing cleared the bar."""
    return {"agent": agent, "candidate": NO_CHANGE, "survives": False,
            "failures": [], "why": because,
            "note": "no candidate was adopted; this is a result about the method, "
                    "not a failure of the run"}
