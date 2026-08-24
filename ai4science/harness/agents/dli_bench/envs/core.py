"""Stepped environments, for the levels a static task cannot pose.

DL0 through DL3 are tasks: a prompt, a workspace, a verdict. DL4 and above are
not, and the reason is structural rather than a matter of size.

  * **DL4** needs a run long enough that the plan has to change inside it, with
    a failure the brief did not mention and a budget that makes the choice of
    what to try a real one.
  * **DL6** needs the *priorities* to move while the agent is working, so that
    continuing the stated plan is the wrong behaviour. A static file cannot pose
    a mission, because a mission is defined by what it does when conditions
    change.
  * **DLOmega** needs a world with opportunities the agent was not pointed at,
    some of which are worthless and some of which unlock others. Nothing is
    delegated except the charter.

So these are environments the agent *acts in*. The contract:

  * hidden state lives in the environment object and is never in an
    observation. :meth:`Environment.observe` returns a dict, and the test
    ``test_observations_never_leak_hidden_state`` walks it;
  * every action is recorded, with what it cost, so scoring reads a transcript
    rather than the agent's account of itself;
  * scheduled events fire on action count, not on wall clock, so a run is
    reproducible and a slow agent is not a different experiment;
  * scoring happens after the run, against the hidden state, in code the agent
    never touched.

The agent may be in-process (a callable, which is how the reference policies
run) or out of process behind :mod:`.server`. The environment cannot tell, and
that is the point: the boundary is the observation, not the process.
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from ..verify import Verdict


class ActionError(RuntimeError):
    """The agent asked for something the environment does not offer.

    Raised rather than silently ignored: an environment that accepts an unknown
    action and does nothing teaches an agent that the action worked.
    """


@dataclass
class Event:
    """Something the world does on its own, at a fixed action count."""

    at_action: int
    kind: str
    detail: Dict[str, Any] = field(default_factory=dict)
    fired: bool = False


@dataclass
class Record:
    """One action, as scoring will see it."""

    n: int
    action: str
    args: Dict[str, Any]
    cost: float
    result_summary: str
    events_fired: Tuple[str, ...] = ()


class Environment:
    """Base class. Subclasses declare ACTIONS and implement ``_do``."""

    #: name -> one-line description, shown to the agent in the brief.
    ACTIONS: Dict[str, str] = {}
    #: What each action costs from the budget.
    COST: Dict[str, float] = {}
    name = "environment"

    def __init__(self, seed: int, budget: float) -> None:
        self.rng = random.Random(seed)
        self.seed = seed
        self.budget = float(budget)
        self.spent = 0.0
        self.n = 0
        self.transcript: List[Record] = []
        self.events: List[Event] = []
        self.closed = False
        self._setup()

    # -- subclass hooks ---------------------------------------------------

    def _setup(self) -> None:                      # pragma: no cover - abstract
        raise NotImplementedError

    def _observe(self) -> Dict[str, Any]:          # pragma: no cover - abstract
        raise NotImplementedError

    def _do(self, action: str, args: Dict[str, Any]) -> Tuple[Any, str]:
        raise NotImplementedError                  # pragma: no cover - abstract

    def _apply_event(self, ev: Event) -> None:
        pass

    def score(self) -> Verdict:                    # pragma: no cover - abstract
        raise NotImplementedError

    # -- the loop ---------------------------------------------------------

    def brief(self) -> str:
        """What the agent is told. Never mentions the hidden state."""
        lines = ["Actions available:"]
        for a, d in self.ACTIONS.items():
            lines.append("  %-22s %-4s  %s" % (a, "%.1f" % self.COST.get(a, 0.0), d))
        lines.append("")
        lines.append("Budget: %.1f. Each action costs what is shown. When the "
                     "budget is gone the run ends." % self.budget)
        return "\n".join(lines)

    def observe(self) -> Dict[str, Any]:
        o = dict(self._observe())
        o["budget_remaining"] = round(self.budget - self.spent, 4)
        o["actions_taken"] = self.n
        return o

    def act(self, action: str, **args: Any) -> Dict[str, Any]:
        if self.closed:
            return {"error": "the run has ended", "budget_remaining": 0.0}
        if action not in self.ACTIONS:
            raise ActionError("%r is not an action here; available: %s"
                              % (action, sorted(self.ACTIONS)))
        cost = float(self.COST.get(action, 0.0))
        if self.spent + cost > self.budget:
            self.closed = True
            return {"error": "budget exhausted", "budget_remaining": 0.0}

        self.n += 1
        self.spent += cost
        fired = self._fire_events()
        try:
            result, summary = self._do(action, args)
        except ActionError as e:
            result, summary = {"error": str(e)}, "refused: %s" % e
        self.transcript.append(Record(self.n, action, dict(args), cost, summary, fired))
        out = result if isinstance(result, dict) else {"result": result}
        out["budget_remaining"] = round(self.budget - self.spent, 4)
        if fired:
            # The world tells the agent that something happened. It does not
            # say what it means -- an environment that explains its own events
            # has supplied the diagnosis, which is CID3 help from the scenery.
            out["notice"] = ["the situation changed: %s" % f for f in fired]
        return out

    def _fire_events(self) -> Tuple[str, ...]:
        fired = []
        for ev in self.events:
            if not ev.fired and self.n >= ev.at_action:
                ev.fired = True
                self._apply_event(ev)
                fired.append(ev.kind)
        return tuple(fired)

    # -- what scoring reads ----------------------------------------------

    def actions_of(self, *names: str) -> List[Record]:
        return [r for r in self.transcript if r.action in names]

    def transcript_json(self) -> str:
        return "\n".join(json.dumps({
            "n": r.n, "action": r.action, "args": r.args, "cost": r.cost,
            "summary": r.result_summary, "events": list(r.events_fired),
        }, sort_keys=True) for r in self.transcript)

    @property
    def meaningful_actions(self) -> int:
        """Actions that changed or probed the world.

        Observation alone is not work: an agent that calls ``observe`` two
        hundred times has not taken two hundred meaningful actions, and a
        minimum-action bar counted that way would be free.
        """
        free = {a for a, c in self.COST.items() if c == 0.0}
        return sum(1 for r in self.transcript if r.action not in free)


Policy = Callable[["Environment"], None]


def run(env: Environment, policy: Policy) -> Environment:
    """Drive an environment with an in-process policy. Used by the tests."""
    policy(env)
    return env
