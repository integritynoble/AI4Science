"""`BAL` — the non-exchangeable starting balance.

    Everyone starts with a small non-exchangeable balance to pay it — spendable
    on fees, never sellable, and visibly distinct so it cannot leak into the
    exchangeable supply.

I held this back through the rest of the economy build on the grounds that it
*holds a balance*, and holding a balance raises custody. That was half right,
and the half it got wrong is the whole design:

  **what made a balance dangerous was that it could MOVE.**

This one cannot. It is granted once, it can only ever be spent *down*, and the
only thing it can be spent on is a fee this machine already computes. So it is
not money held in custody — it is a fee credit that can only be destroyed, and
the single property that has to hold is that it never becomes anything else.

Four refusals keep it there:

  * **there is no function that moves it.** Not "not implemented" — absent, and
    a test fails if one appears. No transfer, sell, withdraw, convert, redeem.
  * **it is granted once.** A balance that can be topped up on request is an
    infinite one, and every fee after the first would be free.
  * **it cannot go negative.** Spending more than is there is refused, never
    overdrawn: an overdraft is a loan, and a loan is the custody question
    coming back in through the side.
  * **a debit must name the fee it pays.** A spend with no fee behind it is
    this balance being used as money, which is the one thing it is not.

And paying from it **does not erase the fee**. The treasury is owed exactly what
it was owed; what changes is the record of how it was covered. The two ledgers
stay apart for that reason — one says what is owed and one says what this credit
covered, and they have to be able to disagree or nobody could tell an unpaid fee
from a paid one.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List

from ai4science.harness.agents.sarsi import ledger
from ai4science.harness.agents.sarsi.registry import Config

#: "A small non-exchangeable balance." Enough to cover the 10% on early runs
#: while the owner decides whether to bring a key or start the exchange node.
STARTING = 25.0

STREAM = "balance"


class Refused(Exception):
    """The balance was not changed, and this says why."""


@dataclass
class Entry:
    pwm: float = 0.0
    fee_for: str = ""
    at: str = ""


@dataclass
class Balance:
    granted: bool = False
    remaining: float = 0.0
    spent: float = 0.0
    #: Always False, and present rather than implied. A reader checking whether
    #: a figure may be sold should find an answer, not an absence.
    exchangeable: bool = False

    @property
    def summary(self) -> str:
        if not self.granted:
            return ("no starting balance has been granted on this machine yet "
                    "— `sarsi balance --grant`")
        return (f"{self.remaining:g} PWM remaining of {STARTING:g} "
                f"(non-exchangeable: spendable on fees, never sellable, and "
                f"kept apart from anything that is) · {self.spent:g} spent on "
                f"fees")


def grant(config: Config, now=time.time) -> Balance:
    """The one grant this machine gets. A second is refused."""
    here = of(config)
    if here.granted:
        raise Refused(
            f"this machine has already had its starting balance — it is "
            f"granted once. A balance that could be topped up on request is an "
            f"infinite one, and every fee after the first would be free. "
            f"{here.remaining:g} PWM remain")
    ledger.append(config, STREAM,
                  {"event": "granted", "pwm": STARTING}, now=now)
    return of(config)


def spend(config: Config, *, pwm: float, fee_for: str,
          now=time.time) -> Balance:
    """Spend some of it on a fee. The only way it goes down, and the only way
    it changes at all.

    `fee_for` names the task whose fee this covers. A debit with nothing behind
    it is the balance being used as money, which is exactly what it is not.
    """
    if not str(fee_for or "").strip():
        raise Refused("a spend must name the fee it pays — this balance is "
                      "spendable on fees and on nothing else, and a debit with "
                      "no fee behind it is it being used as money")
    amount = float(pwm)
    if amount < 0:
        raise Refused("a negative spend is a credit wearing a debit's name")

    here = of(config)
    if not here.granted:
        raise Refused("there is no starting balance on this machine yet — "
                      "`sarsi balance --grant`")
    if amount > here.remaining:
        raise Refused(
            f"only {here.remaining:g} PWM remain and this fee is {amount:g}. "
            f"Refused rather than overdrawn: an overdraft is a loan, and a "
            f"loan is a question about custody that this credit exists to "
            f"avoid")

    ledger.append(config, STREAM,
                  {"event": "spent", "pwm": amount,
                   "fee_for": str(fee_for)}, now=now)
    return of(config)


def of(config: Config) -> Balance:
    """What is left, and what it is. A read."""
    granted = False
    total = 0.0
    spent = 0.0
    for row in _rows(config):
        if row.get("event") == "granted":
            granted = True
            total += float(row.get("pwm") or 0.0)
        elif row.get("event") == "spent":
            spent += float(row.get("pwm") or 0.0)
    return Balance(granted=granted, remaining=max(0.0, total - spent),
                   spent=spent, exchangeable=False)


def history(config: Config) -> List[Entry]:
    """Every fee this credit covered. Kept apart from what was OWED — see
    `earnings` — because those two must be able to disagree, or an unpaid fee
    and a paid one would read the same."""
    return [Entry(pwm=float(r.get("pwm") or 0.0),
                  fee_for=str(r.get("fee_for") or ""),
                  at=str(r.get("at") or ""))
            for r in _rows(config) if r.get("event") == "spent"]


def _rows(config: Config) -> List[Dict[str, Any]]:
    try:
        return list(ledger.read(config, STREAM))
    except Exception:
        return []
