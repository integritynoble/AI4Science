"""What a delegation task is, and what a run of one produces.

DLI-Bench measures **delegation**, not capability: how much of a stated task
comes back done, under a declared budget of human cognitive help, verified by
something that did not perform the work.

Three objects carry that.

  * :class:`Difficulty` --- eight coordinates, reported as a vector and never
    only as a band. The band T0--T6 is a label for reporting; the vector is the
    measurement. Aggregating first and measuring second loses the two
    coordinates that actually bind, which are ``verification`` and ``cost of
    error``.
  * :class:`TaskSpec` --- one problem, its withheld answer key, and the budget
    it is being run under.
  * :class:`Episode` --- one attempt, with every intervention typed and
    timestamped. This is the row a frontier is computed from.

The rule the whole suite exists to enforce is in :mod:`.verify`: the thing that
decides whether a task succeeded is never the thing that performed it.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

# --------------------------------------------------------------------------
# Difficulty
# --------------------------------------------------------------------------

#: The eight coordinates, in the order they are reported.
#:
#: Duration is deliberately absent. A ten-minute task can be cognitively harder
#: than a ten-hour repetitive one, so horizon counts *dependent steps*, not
#: wall-clock.
COORDINATES: Tuple[str, ...] = (
    "horizon",        # L: number/depth of dependent steps
    "coordination",   # C: dependency complexity between steps
    "uncertainty",    # U: missing information at the start
    "ambiguity",      # A: how underspecified the requested outcome is
    "tooling",        # X: tool/environment diversity
    "verification",   # V: how hard it is to check the result
    "novelty",        # N: distance from a known procedure
    "change",         # E: environmental change during execution
)

#: The two coordinates that bind delegation, as opposed to making work hard.
#:
#: Kept separately because they must survive banding: a report that gives only
#: a T band has thrown away the part that determines whether the result can be
#: checked and whether being wrong can be undone.
BINDING: Tuple[str, ...] = ("verification", "risk")


@dataclass(frozen=True)
class Difficulty:
    """Where a task sits, on eight axes rated 0--4.

    ``band`` is derived, not stored, so it can never disagree with the vector
    it summarises.
    """

    horizon: int = 0
    coordination: int = 0
    uncertainty: int = 0
    ambiguity: int = 0
    tooling: int = 0
    verification: int = 0
    novelty: int = 0
    change: int = 0

    def __post_init__(self) -> None:
        for c in COORDINATES:
            v = getattr(self, c)
            if not isinstance(v, int) or not (0 <= v <= 4):
                raise ValueError("%s must be an int in 0..4, got %r" % (c, v))

    def vector(self) -> Dict[str, int]:
        return {c: getattr(self, c) for c in COORDINATES}

    @property
    def band(self) -> str:
        """The T0--T6 reporting band.

        Thresholds are predeclared here rather than fitted per task, so the
        band cannot be chosen to flatter a result. ``novelty`` is weighted
        because it is what separates T5 (the method is unknown) from T4 (the
        method is known and hard): a task nobody has a procedure for is a
        different kind of task, not a longer one.
        """
        v = self.vector()
        if v["novelty"] >= 4:
            return "T5"
        if v["change"] >= 3 and v["horizon"] >= 4:
            return "T6"
        weight = (v["horizon"] + v["coordination"] + v["uncertainty"]
                  + v["ambiguity"] + v["tooling"] + v["novelty"])
        if weight <= 2:
            return "T0"
        if weight <= 5:
            return "T1"
        if weight <= 10:
            return "T2"
        if weight <= 15:
            return "T3"
        return "T4"

    @staticmethod
    def band_index(band: str) -> int:
        return int(band[1:])


# --------------------------------------------------------------------------
# Intervention budgets and depth
# --------------------------------------------------------------------------

#: H0--H5, most autonomous first. The written policy for each is in
#: :mod:`.policy`; these are only the labels.
BUDGETS: Tuple[str, ...] = ("H0", "H1", "H2", "H3", "H4", "H5")


def budget_index(h: str) -> int:
    if h not in BUDGETS:
        raise ValueError("unknown budget %r; expected one of %s" % (h, list(BUDGETS)))
    return BUDGETS.index(h)


#: Critical Intervention Depth: the highest task decision a human supplied.
#:
#: This exists to close a loophole that counting cannot. Ten factual
#: clarifications and one message saying "use algorithm X, that is the
#: solution" are one and ten by count, and the wrong way round by cognition.
CID_MEANING: Dict[int, str] = {
    0: "governance or administrative only -- no cognitive contribution",
    1: "missing fact, or a clarification the evidence did not contain",
    2: "local correction of one action",
    3: "strategy for a subproblem",
    4: "strategy for the overall task",
    5: "the core solution insight, or a missing expert step",
    6: "the problem or mission itself, supplied after the agent stalled",
}


@dataclass(frozen=True)
class Intervention:
    """One thing a human did during an episode.

    ``cognitive`` is the field that decides whether this counts against the
    delegation level. Authorising an action the agent had already chosen is
    governance and does not; telling it which action to choose is cognition and
    does. Both are logged, because a system that looks undelegable purely
    because policy requires signatures is being measured wrongly, and so is one
    that looks delegable because its rescues were phrased as chat.
    """

    kind: str                 # approval | information | planning | correction | rescue | permission
    cognitive: bool
    cid: int
    raised_at: str            # ISO 8601, when the agent surfaced the need
    responded_at: str         # ISO 8601, when the human acted
    minutes: float = 0.0      # human's own cost, their clock
    note: str = ""

    KINDS = ("approval", "information", "planning", "correction", "rescue", "permission")

    def __post_init__(self) -> None:
        if self.kind not in self.KINDS:
            raise ValueError("unknown intervention kind %r" % (self.kind,))
        if self.cid not in CID_MEANING:
            raise ValueError("cid must be 0..6, got %r" % (self.cid,))
        if self.cid > 0 and not self.cognitive:
            raise ValueError(
                "cid=%d is a cognitive contribution but cognitive=False. "
                "CID0 is the only depth a governance action can have."
                % self.cid)
        if self.cognitive and self.cid == 0:
            raise ValueError(
                "cognitive=True with cid=0 is contradictory: if it contributed "
                "no task decision it was not cognitive assistance.")

    @property
    def t_delta_seconds(self) -> float:
        """Authorization latency for this one intervention.

        The term the H-scale is invariant to, and the one that decides whether
        a delegated task finishes today. It is two timestamps; the reason it is
        usually missing from deployed systems is that nobody added the column.
        """
        a = datetime.fromisoformat(self.raised_at.replace("Z", "+00:00"))
        b = datetime.fromisoformat(self.responded_at.replace("Z", "+00:00"))
        d = (b - a).total_seconds()
        if d < 0:
            raise ValueError("responded_at precedes raised_at")
        return d


# --------------------------------------------------------------------------
# Tasks
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Loss:
    """What being wrong costs on this task, relative to being right.

    Present because a frontier that thresholds on success probability alone
    prices failure at zero. The reliability a class *requires* is not the
    evaluator's to choose: it follows from these numbers.
    """

    value: float = 1.0          # V: value of a verified success
    c_detect: float = 0.0       # cost of noticing the failure
    c_undo: float = 0.0         # cost of undoing it
    c_residual: float = 0.0     # harm that no expenditure undoes; inf if unbounded

    @property
    def rho(self) -> float:
        if self.value <= 0:
            raise ValueError("value must be positive")
        return (self.c_detect + self.c_undo + self.c_residual) / self.value

    @property
    def p_star(self) -> float:
        """Minimum reliability at which this task may be delegated at all.

        ``rho/(1+rho)``, which goes to 1 as residual harm grows without bound --
        a class no attainable reliability delegates.
        """
        r = self.rho
        if math.isinf(r):
            return 1.0
        return r / (1.0 + r)


@dataclass(frozen=True)
class TaskSpec:
    """One delegation problem, as handed to the system under test.

    ``prompt`` is what the agent sees. ``answer_key`` names files that must
    never reach the sandbox -- an agent that can read the ground truth can copy
    it into its own output and pass any reference-free judge.
    """

    task_id: str
    family: str               # software | data | research | planning | document | tools
    level: str                # DL0..DL6, DLOmega -- the level this task is evidence for
    difficulty: Difficulty
    prompt: str
    loss: Loss = field(default_factory=Loss)
    #: Files the agent is expected to produce, relative to its workspace.
    deliverables: Tuple[str, ...] = ()
    #: Paths in the keyed workspace that do NOT exist in the agent's workspace.
    #: The ground truth. Staging one of these makes the run meaningless.
    answer_key: Tuple[str, ...] = ()
    #: Paths present in BOTH workspaces on purpose: inputs the agent needs and
    #: could tamper with, kept in the keyed copy so scoring reads the original.
    #: A corpus the agent may edit is a corpus the agent may shrink, and a
    #: benchmark that then times it is measuring the edit.
    pinned_inputs: Tuple[str, ...] = ()
    #: What the human is allowed to say at each budget, beyond the standing
    #: policy. Task-specific because some tasks genuinely have external facts
    #: the agent cannot obtain.
    permitted_information: Tuple[str, ...] = ()
    #: Free-text statement of what the verifier checks and what it cannot.
    #: Required: a benchmark that does not say what its verifier misses is
    #: reporting an instrument reading as a quantity.
    verifier_note: str = ""
    seed: int = 0

    def __post_init__(self) -> None:
        if not self.verifier_note:
            raise ValueError(
                "%s: verifier_note is required. State what the check "
                "establishes and what it cannot -- an unstated false-pass rate "
                "is the bias this suite exists to avoid." % self.task_id)


# --------------------------------------------------------------------------
# Episodes
# --------------------------------------------------------------------------

#: Outcomes. ``escalated`` is deliberately not ``failed``: an agent that
#: correctly reports it cannot proceed did not complete the task, and also did
#: not incur the loss. It costs human load rather than reliability.
OUTCOMES: Tuple[str, ...] = ("success", "failure", "escalated", "refused", "error")

#: Where acceptance happened. alpha0 is inadmissible: a result accepted by
#: whatever produced it is an assertion, not a level.
ACCEPTANCE_LOCI: Dict[str, str] = {
    "alpha0": "the performing system -- INADMISSIBLE",
    "alpha1": "a test declared before the work, which the performer cannot edit",
    "alpha2": "a separate process with its own credential and enforced write set",
    "alpha3": "a party that did not build the system",
}


@dataclass
class Episode:
    """One attempt at one task under one budget."""

    task_id: str
    system: str                       # what was tested, including version
    budget: str                       # H0..H5
    band: str                         # T band of the task
    family: str
    outcome: str
    acceptance_locus: str             # alpha0..alpha3
    verifier_id: str
    interventions: List[Intervention] = field(default_factory=list)
    #: Acceptance events inside the episode, and how many of their criteria the
    #: system itself wrote. sigma is the ratio, and it rises with the level by
    #: construction unless something structurally prevents it.
    acceptance_events: int = 1
    self_authored_criteria: int = 0
    agent_replans: int = 0
    wall_seconds: float = 0.0
    compute_cost: float = 0.0
    verifier_false_pass_rate: Optional[float] = None
    notes: str = ""

    def __post_init__(self) -> None:
        if self.outcome not in OUTCOMES:
            raise ValueError("unknown outcome %r" % (self.outcome,))
        if self.acceptance_locus not in ACCEPTANCE_LOCI:
            raise ValueError("unknown acceptance locus %r" % (self.acceptance_locus,))
        if self.budget not in BUDGETS:
            raise ValueError("unknown budget %r" % (self.budget,))
        if self.self_authored_criteria > self.acceptance_events:
            raise ValueError("self_authored_criteria exceeds acceptance_events")

    # -- derived quantities ------------------------------------------------

    @property
    def succeeded(self) -> bool:
        return self.outcome == "success"

    @property
    def sigma(self) -> float:
        """Share of acceptance events whose criterion the system itself wrote."""
        if self.acceptance_events <= 0:
            return 0.0
        return self.self_authored_criteria / self.acceptance_events

    @property
    def cognitive_interventions(self) -> List[Intervention]:
        return [i for i in self.interventions if i.cognitive]

    @property
    def max_cid(self) -> int:
        """The deepest help a human gave. Zero if none was cognitive."""
        return max((i.cid for i in self.interventions), default=0)

    @property
    def t_delta_total(self) -> float:
        return sum(i.t_delta_seconds for i in self.interventions)

    @property
    def human_minutes(self) -> float:
        return sum(i.minutes for i in self.interventions)

    def load(self) -> float:
        """Human load in seconds: the observable that replaces HCIL.

        ``sum over interventions of (T_delta + human cost)``. Every term is a
        subtraction of two timestamps or a figure the human reports about their
        own clock. Nothing here is a counterfactual, which was the objection to
        dividing by "the cognitive effort the task required".
        """
        return sum(i.t_delta_seconds + i.minutes * 60.0 for i in self.interventions)

    def admissible(self) -> Tuple[bool, str]:
        """Whether this episode may count toward a level at all."""
        if self.acceptance_locus == "alpha0":
            return False, "accepted by the system that performed it"
        if self.outcome == "error":
            return False, "harness error, not a result about the system"
        return True, ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["sigma"] = round(self.sigma, 4)
        d["max_cid"] = self.max_cid
        d["t_delta_seconds"] = round(self.t_delta_total, 3)
        d["load_seconds"] = round(self.load(), 3)
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)
