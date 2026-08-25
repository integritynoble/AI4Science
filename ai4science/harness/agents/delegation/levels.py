"""One agent per delegation level, each refusing what is above it.

A level is a claim about what a system sustains, and a label anyone can print.
The difference between the two is whether the system *declines* work above the
level it claims. So each agent here is a configuration with declared limits, and
each refuses out-of-band work with a reason naming the level that would be
needed.

    DL0  instruction-bound   the human supplies the operation; the agent performs it
    DL1  goal-bound, short   a small goal; the agent picks 2-5 operations
    DL2  task-bound          a multi-step task; state persists, a check is
                             registered before the work, acceptance is
                             independent, failure retries
    DL3  outcome-bound       an outcome and constraints; the agent constructs the
                             strategy, routes across executors, and escalates
                             rather than guessing

Two properties hold for every level, because they are not capabilities that
higher levels earn:

  * **acceptance is never the doer's.** Even DL0 does not grade itself. What
    changes with level is who *writes* the criterion, not who applies it.
  * **an irreversible class is refused unattended at every level.** That floor
    is not lifted by being more capable.

What genuinely differs is how much of the task the human still supplies, and a
higher-level agent given a lower-level task is fine -- the refusal runs the
other way.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .compress import Library
from .contract import Contract, read_task
from .executor import CompetenceModel, Executor
from .loop import DelegationAgent, Outcome

BANDS: Tuple[str, ...] = ("T0", "T1", "T2", "T3", "T4", "T5", "T6", "TOmega")


@dataclass(frozen=True)
class LevelSpec:
    """What one level's agent may do, and what it must refuse."""

    level: str
    highest_band: str
    human_supplies: str
    agent_supplies: str
    #: May the agent derive its own acceptance criteria, or must they be given?
    derives_criteria: bool
    #: Attempts before it stops. One means no retry loop at all.
    max_attempts: int
    #: May it choose between executors on evidence?
    routes: bool
    #: May it escalate, or must it either finish or fail?
    escalates: bool
    #: Intervention budget the level is evidence for.
    budget: str
    note: str

    def accepts(self, band: str) -> Tuple[bool, str]:
        if band not in BANDS:
            return False, "unknown difficulty band %r" % band
        if BANDS.index(band) <= BANDS.index(self.highest_band):
            return True, ""
        need = next((s.level for s in ORDER if BANDS.index(s.highest_band)
                     >= BANDS.index(band)), "an environment-level agent")
        return False, ("%s is a %s task and this is the %s agent, which is "
                       "evidence only up to %s. %s would be needed. Refusing "
                       "rather than attempting it and reporting a level it did "
                       "not reach." % (band, band, self.level, self.highest_band, need))


SPECS: Dict[str, LevelSpec] = {
    "DL0": LevelSpec(
        level="DL0", highest_band="T0",
        human_supplies="the operation, explicitly",
        agent_supplies="correct execution of it",
        derives_criteria=False, max_attempts=1, routes=False, escalates=False,
        budget="H5-H4",
        note="Not delegation, and not useless: deterministic execution, "
             "extraction and tool invocation are worth having. What DL0 lacks "
             "is task control -- the human is still the planner."),
    "DL1": LevelSpec(
        level="DL1", highest_band="T1",
        human_supplies="a small goal, and the acceptance criterion",
        agent_supplies="a short plan of two to five operations",
        derives_criteria=False, max_attempts=1, routes=False, escalates=True,
        budget="H3-H2",
        note="The transition from DL0 is that the human states an outcome "
             "rather than a step. A prompt that names the file to edit has "
             "quietly become a DL0 task in a longer sentence."),
    "DL2": LevelSpec(
        level="DL2", highest_band="T2",
        human_supplies="the task",
        agent_supplies="the plan, the state that survives it, and a criterion "
                       "registered before the work exists",
        derives_criteria=True, max_attempts=3, routes=False, escalates=True,
        budget="H2-H1",
        note="The first level at which delegation is economically meaningful. "
             "The human no longer specifies the next action, and a failure is "
             "caught by something that did not perform the work."),
    "DL3": LevelSpec(
        level="DL3", highest_band="T3",
        human_supplies="an outcome and its constraints",
        agent_supplies="the strategy, the executor choice, and the decision to "
                       "ask rather than guess",
        derives_criteria=True, max_attempts=4, routes=True, escalates=True,
        budget="H1-H2",
        note="The defining change is the transfer of procedural responsibility: "
             "the human says what must be true at the end and nothing about "
             "how."),
}

ORDER: Tuple[LevelSpec, ...] = tuple(SPECS[k] for k in ("DL0", "DL1", "DL2", "DL3"))


class CriteriaOnly:
    """Supplies acceptance criteria and refuses to do the work.

    The register must be filled by something other than the executor, and that
    something must not also be a candidate to execute. Its cost is prohibitive
    so the router never scores it, and it raises if called anyway -- a guard
    rather than a preference, because the first version relied on the score and
    the router picked it regardless.
    """

    name = "criteria-source"

    def __init__(self, inner) -> None:
        self.inner = inner

    def capabilities(self):
        return {"name": self.name, "cost": 1e9, "kind": "criteria-only"}

    def propose_criteria(self, contract, workspace):
        return self.inner.propose_criteria(contract, workspace)

    def execute(self, contract, workspace, feedback):
        raise RuntimeError("the criteria source does not execute work")


class LevelAgent:
    """A delegation agent pinned to one level, refusing above it."""

    def __init__(self, level: str, executors: Sequence[Executor],
                 criteria_source: Optional[Executor] = None,
                 library: Optional[Library] = None,
                 competence: Optional[CompetenceModel] = None) -> None:
        if level not in SPECS:
            raise ValueError("no such level %r; have %s" % (level, sorted(SPECS)))
        self.spec = SPECS[level]
        self.executors = list(executors)
        self.criteria_source = criteria_source
        self.library = library
        self.competence = competence or CompetenceModel()

    # -- the level's own boundary -----------------------------------------

    def would_accept(self, band: str) -> Tuple[bool, str]:
        return self.spec.accepts(band)

    def describe(self) -> str:
        s = self.spec
        return "\n".join([
            "%s -- %s" % (s.level, {"DL0": "instruction-bound",
                                    "DL1": "goal-bound",
                                    "DL2": "task-bound",
                                    "DL3": "outcome-bound"}[s.level]),
            "  human supplies : %s" % s.human_supplies,
            "  agent supplies : %s" % s.agent_supplies,
            "  highest band   : %s   (anything above is refused)" % s.highest_band,
            "  intervention   : %s" % s.budget,
            "  derives its own acceptance criteria : %s" % ("yes" if s.derives_criteria else "no"),
            "  retries on an independent rejection : %s" % ("up to %d attempts" % s.max_attempts
                                                            if s.max_attempts > 1 else "no"),
            "  chooses between executors on evidence : %s" % ("yes" if s.routes else "no"),
            "  escalates rather than guessing        : %s" % ("yes" if s.escalates else "no"),
            "",
            "  %s" % s.note,
            "",
            "  At every level: acceptance is never the doer's, and an",
            "  irreversible class is refused unattended. Those are not",
            "  capabilities a higher level earns.",
        ])

    # -- running -----------------------------------------------------------

    def run(self, task_id: str, statement: str, workspace: Path, store: Path,
            band: Optional[str] = None,
            declared_loss: Optional[Dict[str, float]] = None,
            class_key: Optional[str] = None, human=None) -> Outcome:
        if band is not None:
            ok, why = self.would_accept(band)
            if not ok:
                out = Outcome(task_id=task_id, accepted=False, attempts=0)
                out.refused = why
                out.contract = read_task(task_id, statement, workspace, declared_loss)
                out.trace.append("refused before starting: %s" % why)
                return out

        execs: List[Executor] = list(self.executors)
        if self.criteria_source is not None:
            # Attached at every level, because acceptance is never the doer's --
            # what changes with the level is who WRITES the criterion, not who
            # applies it. Wrapped so the router cannot pick it to DO the work:
            # unwrapped, it was chosen as an executor and its solver then did
            # the task carelessly, which failed DL0 and DL1 for a reason that
            # had nothing to do with either level.
            execs.insert(0, CriteriaOnly(self.criteria_source))

        agent = DelegationAgent(
            executors=execs if execs else None,
            competence=self.competence,
            library=self.library if self.spec.derives_criteria else None,
            max_attempts=self.spec.max_attempts,
            human=human if self.spec.escalates else None)
        if not self.spec.routes:
            # One executor only. Routing is a DL3 capability, and an agent that
            # quietly used it would be claiming a level it does not hold.
            agent.executors = [e for e in agent.executors][:2]
            agent.router.executors = [e for e in agent.router.executors][:2]
        return agent.run(task_id, statement, workspace, store,
                         declared_loss=declared_loss, class_key=class_key)
