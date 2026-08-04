"""What a night of autonomous research may cost, and where it stops.

The product promise is that the second function "is off until the owner turns it
on, and reaching the budget stops the loop rather than asking for more". Both
halves are here, and the second is the one worth writing carefully: a budget that
asks for more when exhausted is a budget that will be extended at 3 a.m. by
whoever is least equipped to say no.

So `spend()` raises, `remaining()` reaches zero, and there is no `extend()`.
Raising the ceiling is the owner's act, performed by constructing a new budget —
which leaves a trace, because a new object is a decision and a mutated field is
not.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


class BudgetExhausted(Exception):
    """The loop stops. It does not ask."""


class Budget:
    """A standing, revocable allowance for one agent's autonomous function."""

    def __init__(self, agent: str, *, units: float, unit: str = "gpu-hour",
                 note: str = ""):
        if units <= 0:
            raise ValueError("%s: a budget of %r authorises nothing; leave the "
                             "autonomous function off instead" % (agent, units))
        self.agent = agent
        self.units = float(units)
        self.unit = unit
        self.note = note
        self._spent = 0.0
        self._log: List[Dict[str, object]] = []

    # ------------------------------------------------------------------ state

    @property
    def spent(self) -> float:
        return self._spent

    def remaining(self) -> float:
        return max(0.0, self.units - self._spent)

    def exhausted(self) -> bool:
        return self.remaining() <= 0.0

    # ----------------------------------------------------------------- spend

    def would_fit(self, cost: float) -> bool:
        return cost <= self.remaining()

    def spend(self, cost: float, *, what: str) -> float:
        """Charge `cost` for `what`, or raise.

        Refuses to part-spend: a run that needs four hours and is given the two
        that remain produces a half-trained model and a whole bill. Better to
        stop with the budget intact and say what would not fit."""
        cost = float(cost)
        if cost < 0:
            raise ValueError("a negative cost is a refund, not a spend")
        if cost > self.remaining():
            raise BudgetExhausted(
                "%s: %s needs %.3g %s and %.3g remain of %.3g. The loop stops "
                "here — raising this is the owner's, and the agent has no way to "
                "do it." % (self.agent, what, cost, self.unit,
                            self.remaining(), self.units))
        self._spent += cost
        self._log.append({"what": what, "cost": cost})
        return self.remaining()

    # ------------------------------------------------------------------ view

    def ledger(self) -> List[Dict[str, object]]:
        return list(self._log)

    def report(self) -> str:
        L = ["%s: %.3g of %.3g %s spent, %.3g left"
             % (self.agent, self._spent, self.units, self.unit, self.remaining())]
        if self.note:
            L.append("  (%s)" % self.note)
        for row in self._log:
            L.append("  %-44s %.3g" % (row["what"], row["cost"]))
        if self.exhausted():
            L.append("  exhausted — the loop stopped rather than asking for more")
        return "\n".join(L)


class Switch:
    """Off until the owner turns it on. The agent cannot reach the switch.

    Modelled as an object rather than a boolean so that the refusal has somewhere
    to live: `agent_turn_on()` exists and always raises, which is more useful
    than the method simply being absent — an absent method invites someone to
    add one."""

    def __init__(self, agent: str):
        self.agent = agent
        self._on = False
        self._budget: Optional[Budget] = None
        self._by: str = ""

    @property
    def on(self) -> bool:
        return self._on and self._budget is not None and not self._budget.exhausted()

    @property
    def budget(self) -> Optional[Budget]:
        return self._budget

    def owner_turn_on(self, budget: Budget, *, by: str = "owner") -> None:
        self._on, self._budget, self._by = True, budget, by

    def owner_turn_off(self) -> None:
        self._on = False

    def agent_turn_on(self, *_a, **_k):
        raise PermissionError(
            "%s cannot turn on its own autonomous function, extend its budget, or "
            "raise it. That is the one decision the owner kept when they turned "
            "the rest over." % self.agent)

    # An agent asking for more is a request, not a change. It goes where every
    # other question goes — to the owner, through attention — and returns nothing.
    agent_extend = agent_turn_on
    agent_raise = agent_turn_on

    def require_on(self) -> Budget:
        if not self.on:
            why = ("it has never been turned on" if not self._on
                   else "its budget is exhausted")
            raise PermissionError("%s: autonomous work refused — %s"
                                  % (self.agent, why))
        return self._budget
