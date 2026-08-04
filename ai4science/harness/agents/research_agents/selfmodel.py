"""What an agent knows about its own competence, and what it refuses to say.

Four refusals, from the built self-model contract:

  1. every line is observed          — a claim traces to a run
  2. unmeasured is reported as unmeasured, never zero and never dropped
  3. the limits line is always present
  4. no path from reading to authority

The second is the one this module is mostly about, because it is the one that
fails quietly. A dimension with no measurement is easy to render as `0.0`, and a
`0.0` in a table is read as *measured and bad* rather than *never run*. Those
two are opposite facts and only one of them is true, so `observe()` is the only
way a number enters and `report()` prints `unmeasured` for everything else.

The third fails quietly in a different way: an agent that lists its dimensions
and omits its limits has written an advertisement. So `report()` appends the
limits line whether or not the caller asked, and there is no flag to turn it off.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


class Unobserved(Exception):
    """Raised when a caller asks for a value that was never measured."""


@dataclass(frozen=True)
class Dimension:
    """One thing an agent is scored on, and the measurement behind it."""

    key: str
    title: str
    #: How it is measured. Prose, but concrete — the thing a reader checks the
    #: number against. "PSNR against the paired full-dose scan, per vendor".
    measure: str
    higher_is_better: bool = True
    #: What this dimension is routinely confused with. Optional, and worth
    #: filling: most of the damage in these fields is one metric standing in for
    #: another. "detectability" is not "fidelity"; "discrimination" is not
    #: "calibration".
    not_to_be_confused_with: str = ""
    #: If set, a value on this dimension is meaningless without one on that one,
    #: and `report()` says so. Fidelity without detectability, discrimination
    #: without calibration.
    requires: str = ""


@dataclass
class Observation:
    value: float
    evidence: str
    at: float
    n: int = 1
    interval: Optional[Tuple[float, float]] = None


class SelfModel:
    """The dimensions an agent is scored on, and what has actually been run."""

    def __init__(self, agent: str, dimensions: Tuple[Dimension, ...],
                 limits: Tuple[str, ...]):
        if not limits:
            raise ValueError("%s: a self-model with no limits line is an "
                             "advertisement" % agent)
        self.agent = agent
        self.dimensions: Dict[str, Dimension] = {d.key: d for d in dimensions}
        self.limits = limits
        self._obs: Dict[str, Observation] = {}

    # ------------------------------------------------------------- recording

    def observe(self, key: str, value: float, *, evidence: str, n: int = 1,
                interval: Optional[Tuple[float, float]] = None,
                now: Optional[float] = None) -> None:
        """Record a measurement. `evidence` is required and may not be empty —
        a number whose provenance is a sentence nobody wrote is not observed."""
        if key not in self.dimensions:
            raise KeyError("%s has no dimension %r" % (self.agent, key))
        if not (evidence or "").strip():
            raise ValueError("%s.%s: a value with no evidence is not an "
                             "observation" % (self.agent, key))
        self._obs[key] = Observation(float(value), evidence.strip(),
                                     time.time() if now is None else now,
                                     n, interval)

    def value(self, key: str) -> float:
        """The measured value, or raise. Never a default — a caller that wants a
        number for an unrun dimension has to say so, out loud, at its own call
        site."""
        if key not in self._obs:
            raise Unobserved("%s.%s has never been measured" % (self.agent, key))
        return self._obs[key].value

    def measured(self, key: str) -> bool:
        return key in self._obs

    @property
    def unmeasured(self) -> List[str]:
        return [k for k in self.dimensions if k not in self._obs]

    # ------------------------------------------------------------- reporting

    def report(self) -> str:
        """Every dimension, measured or not, then the limits. In that order and
        with no way to omit either half."""
        L = ["%s — what it can do, and how that was measured:" % self.agent, ""]
        for key, d in self.dimensions.items():
            ob = self._obs.get(key)
            if ob is None:
                L.append("  %-28s unmeasured" % d.title)
                L.append("  %-28s   (would be: %s)" % ("", d.measure))
                continue
            val = "%.4g" % ob.value
            if ob.interval:
                val += " [%.4g, %.4g]" % ob.interval
            if ob.n > 1:
                val += "  n=%d" % ob.n
            L.append("  %-28s %s" % (d.title, val))
            L.append("  %-28s   %s" % ("", ob.evidence))
            if d.requires and not self.measured(d.requires):
                L.append("  %-28s   ⚠ %s is unmeasured, and this number cannot be "
                         "read without it" % ("", self.dimensions[d.requires].title))
        L.append("")
        L.append("limits:")
        for line in self.limits:
            L.append("  - %s" % line)
        return "\n".join(L)

    def paired_gaps(self) -> List[str]:
        """Dimensions whose partner is missing. The imaging case this exists for:
        a fidelity gain reported with no detectability number is the failure mode
        the design is most worried about, and it should be findable without
        reading the whole report."""
        out = []
        for key, d in self.dimensions.items():
            if d.requires and self.measured(key) and not self.measured(d.requires):
                out.append("%s reported without %s" % (d.title,
                                                       self.dimensions[d.requires].title))
        return out

    # ---------------------------------------------------------- refusal (4)

    def authority(self) -> None:
        """Reading the self-model never widens what the agent may do.

        There is deliberately no method here that returns a permission, a
        ceiling, or a grant. This one exists to be the place someone looks before
        adding one."""
        raise NotImplementedError(
            "a self-model confers no authority — reading a capability never "
            "granted the right to use it")
