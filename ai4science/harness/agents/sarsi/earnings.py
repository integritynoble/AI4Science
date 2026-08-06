"""`ERN` — §13: what a run owes, and to whom.

    | 10%   | the PWM treasury pool                                       |
    | 0-5%  | the agent's author, at the fraction of the slice they chose  |
    | rest  | the LLM provider                                            |

    A run on ai4science pays no platform share.

**This computes and records. It moves nothing.** The line is the one the compute
design already draws — *the CLI dispatches and attributes; the platform settles;
the CLI must never move tokens* — and it is right here for the same reason it
was right there: a machine that can work out what is owed is safe to leave
running unattended, and a machine that can move balances unattended is a
different risk entirely. There is deliberately no function in this module that
transfers, pays, settles, mints or sells, and a test asserts there is not.

Two rules carry it, and both are rules this system already applies:

  * **unknown is not zero.** A run whose cost could not be metered records
    *nothing*, not a zero. `blast` counts unchecked commands rather than calling
    them clean; `spend` says what it could not measure. A fee ledger that wrote
    `0` for an unmeasured run would quietly assert *"this owed nothing"*, which
    is the one thing an accounting must never say by accident. The unmeasured
    runs are counted and reported, so a total is never mistaken for complete.

  * **the shares are exhaustive.** They add to the cost exactly, with the
    provider taking the remainder rather than a computed percentage — a split
    of independently-rounded percentages leaks a fraction every run, in a
    direction nobody notices until it is large.

The author's share comes out of the **provider's**, not the treasury's and not
added on top: the user pays the same either way, and what changes is who the
rest of it reaches.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ai4science.harness.agents.sarsi import ledger
from ai4science.harness.agents.sarsi.registry import Config

#: §13. The treasury's cut, and the ceiling on the author's.
TREASURY = 0.10
AUTHOR_SLICE = 0.05

#: What the APP charges and this does not. Named rather than omitted, so the
#: difference between the two products is visible in the arithmetic and not
#: only in a paragraph.
PLATFORM = 0.0

STREAM = "earnings"


@dataclass
class Split:
    cost: float = 0.0
    treasury: float = 0.0
    author: float = 0.0
    provider: float = 0.0
    platform: float = 0.0


@dataclass
class ByoSplit(Split):
    """A run on the owner's own key or subscription.

    The provider is **not owed anything here** — they were already paid, by the
    API bill or the subscription. Recording them as owed would double-count a
    bill the owner has settled, so what left in that direction is
    `paid_outside`: named, so a reader can see the whole value accounted for
    without it looking like a debt.
    """
    paid_outside: float = 0.0


@dataclass
class Owed(Split):
    agent_id: str = ""
    task_id: str = ""
    author_handle: str = ""
    at: str = ""


@dataclass
class Total(Split):
    runs: int = 0
    #: runs whose cost could not be read. NOT folded into the total as zero.
    unmeasured: int = 0

    @property
    def summary(self) -> str:
        parts = [f"{self.runs} run(s): treasury {self.treasury:g}, "
                 f"author {self.author:g}, provider {self.provider:g}"]
        if self.unmeasured:
            parts.append(f"{self.unmeasured} run(s) could not be measured, so "
                         f"this total is what was seen and not what was spent")
        return " · ".join(parts)


def split(cost: float, *, price_share: float = 0.0) -> Split:
    """The three shares of one run's metered cost.

    `price_share` is a fraction OF the author's slice, so 1.0 is 5% of the run
    and not 100% of it. Clamped here as well as refused at install, because
    that check belongs to a different program and this arithmetic should not
    depend on it having been run.
    """
    if cost is None:
        raise ValueError("a cost that is not known cannot be split — record "
                         "nothing rather than zero")
    cost = float(cost)
    if cost < 0:
        raise ValueError(f"a run cannot cost {cost} — an accounting that "
                         f"accepted a negative would let one record undo every "
                         f"fee before it")
    share = min(max(float(price_share or 0.0), 0.0), 1.0)
    treasury = cost * TREASURY
    author = cost * AUTHOR_SLICE * share
    platform = cost * PLATFORM
    # The remainder, not a fourth percentage: independently-rounded shares do
    # not add up, and the gap goes somewhere every single run.
    provider = cost - treasury - author - platform
    return Split(cost=cost, treasury=treasury, author=author,
                 provider=provider, platform=platform)


def split_byo(value: float, *, price_share: float = 0.0) -> ByoSplit:
    """The shares of a bring-your-own-key run.

    §13: *a user may use their own API key or subscription; the 10% still
    applies, computed at the PWM/token ratio.* Otherwise every run would be
    free by bringing one.

    The author still earns: their slice is for the agent being used, not for
    who paid the provider.
    """
    base = split(value, price_share=price_share)
    return ByoSplit(cost=base.cost, treasury=base.treasury,
                    author=base.author, provider=0.0,
                    platform=base.platform,
                    paid_outside=base.cost - base.treasury - base.author
                                 - base.platform)


def notional(spend, *, model: str) -> Optional[float]:
    """What a run is worth in PWM, for the fee.

    When the harness metered it, that number wins — this path exists only for
    the sessions it does not meter, which is every Claude Code one. Those have
    token counts and no price, and §13 says the fee still applies.

    `None` when there are no token counts at all. The rule does not weaken
    because there is now a way to price: a transcript that could not be read
    gives no tokens, and no tokens is not zero tokens.
    """
    priced = getattr(spend, "pwm", None)
    if priced is not None:
        return float(priced)
    counts = [getattr(spend, n, None) for n in
              ("input_tokens", "output_tokens", "cached_tokens",
               "cache_write_tokens")]
    if all(c is None for c in counts):
        return None
    from ai4science.llm import pricing
    got = pricing.price_session(model,
                                input=counts[0] or 0, output=counts[1] or 0,
                                cached=counts[2] or 0, cache_write=counts[3] or 0)
    return float(got["pwm"])


def _market_of(config: Config, agent_id: str) -> Dict[str, Any]:
    """The installed package's record: who wrote it, and what they chose.

    Attribution comes from here rather than from anything the run says about
    itself — the same reason a verdict comes from a verifier.
    """
    try:
        from ai4science.harness.agents.sarsi import market
        for row in market.installed(config):
            if row.agent_id == agent_id:
                for a in row.authors:
                    if a.get("part") == "agent":
                        return {"handle": a.get("handle") or "",
                                "share": _share_of(config, agent_id)}
                return {"handle": "", "share": _share_of(config, agent_id)}
    except Exception:
        pass
    return {"handle": "", "share": 0.0}


def _share_of(config: Config, agent_id: str) -> float:
    import json
    from ai4science.harness.agents.sarsi.registry import config_path
    try:
        path = config.path or config_path(config.root)
        raw = json.loads(open(path).read())
    except Exception:
        return 0.0
    for entry in raw.get("agents", {}).get("list", []):
        if entry.get("id") == agent_id:
            return float((entry.get("market") or {}).get("price_share") or 0.0)
    return 0.0


def record(config: Config, *, agent_id: str, task_id: str,
           cost: Optional[float], now=time.time) -> Optional[Owed]:
    """Write what this run owes. `cost=None` writes NOTHING.

    Not a zero row: a fee ledger claiming a run owed nothing when nobody could
    measure it is the accounting equivalent of `blast` reporting a clean bill
    on an unread transcript. The unmeasured run is counted separately, so a
    total can say what it could not see.
    """
    if cost is None:
        ledger.append(config, STREAM,
                      {"agent": agent_id, "task": task_id, "measured": False},
                      now=now)
        return None

    who = _market_of(config, agent_id)
    got = split(cost, price_share=who["share"])
    row = Owed(cost=got.cost, treasury=got.treasury, author=got.author,
               provider=got.provider, platform=got.platform,
               agent_id=agent_id, task_id=task_id,
               author_handle=who["handle"] if got.author else "")
    ledger.append(config, STREAM,
                  {"agent": agent_id, "task": task_id, "measured": True,
                   "cost": row.cost, "treasury": row.treasury,
                   "author": row.author, "author_handle": row.author_handle,
                   "provider": row.provider, "platform": row.platform},
                  now=now)
    return row


def from_spend(config: Config, *, agent_id: str, task_id: str,
               spend, model: str = "", now=time.time) -> Optional[Owed]:
    """Record what a run owes from what the METER said it cost.

    `Spend.pwm` is `None` when the session was not metered by us — a Claude
    Code session is not — and that is the same "unknown" this module refuses to
    write as zero. Reusing `spend`'s own word for it means one place decides
    what measured means, rather than two that can disagree.

    A run reporting its own cost would be the shape this system refuses
    everywhere else: a verdict comes from a verifier, a radius from the
    transcript, and a bill from the meter.
    """
    priced = getattr(spend, "pwm", None)
    if priced is not None:
        # The harness metered it: the provider IS owed, in PWM, and the
        # ordinary split applies.
        return record(config, agent_id=agent_id, task_id=task_id,
                      cost=priced, now=now)

    # Bring your own key. §13: the 10% still applies, computed at the
    # PWM/token ratio — otherwise every run would be free by bringing one. The
    # provider is not owed here because the API bill or the subscription
    # already paid them, so recording them as owed would double-count a bill
    # the owner has settled.
    value = notional(spend, model=model)
    if value is None:
        return record(config, agent_id=agent_id, task_id=task_id, cost=None,
                      now=now)
    who = _market_of(config, agent_id)
    got = split_byo(value, price_share=who["share"])
    row = Owed(cost=got.cost, treasury=got.treasury, author=got.author,
               provider=0.0, platform=got.platform, agent_id=agent_id,
               task_id=task_id,
               author_handle=who["handle"] if got.author else "")
    ledger.append(config, STREAM,
                  {"agent": agent_id, "task": task_id, "measured": True,
                   "cost": row.cost, "treasury": row.treasury,
                   "author": row.author, "author_handle": row.author_handle,
                   "provider": 0.0, "platform": row.platform,
                   # Named, so the whole value is accounted for without the
                   # provider's part looking like a debt this machine owes.
                   "paid_outside": got.paid_outside, "byo_key": True},
                  now=now)
    return row


def owed(config: Config) -> List[Owed]:
    """Every measured run and what it owes. A read; it changes nothing."""
    out = []
    for entry in _rows(config):
        if not entry.get("measured"):
            continue
        out.append(Owed(cost=float(entry.get("cost") or 0.0),
                        treasury=float(entry.get("treasury") or 0.0),
                        author=float(entry.get("author") or 0.0),
                        provider=float(entry.get("provider") or 0.0),
                        platform=float(entry.get("platform") or 0.0),
                        agent_id=str(entry.get("agent") or ""),
                        task_id=str(entry.get("task") or ""),
                        author_handle=str(entry.get("author_handle") or ""),
                        at=str(entry.get("at") or "")))
    return out


def total(config: Config) -> Total:
    rows = _rows(config)
    out = Total()
    for entry in rows:
        if not entry.get("measured"):
            out.unmeasured += 1
            continue
        out.runs += 1
        out.cost += float(entry.get("cost") or 0.0)
        out.treasury += float(entry.get("treasury") or 0.0)
        out.author += float(entry.get("author") or 0.0)
        out.provider += float(entry.get("provider") or 0.0)
        out.platform += float(entry.get("platform") or 0.0)
    return out


def by_author(config: Config) -> Dict[str, float]:
    """What each author is owed across every run that used their agent.

    Keyed by handle and read from the RECORDED rows, so removing the package
    does not erase what it earned — the author did the work of writing it, and
    an uninstall is the owner's decision about the future.
    """
    out: Dict[str, float] = {}
    for row in owed(config):
        if row.author_handle:
            out[row.author_handle] = out.get(row.author_handle, 0.0) + row.author
    return out


def _rows(config: Config) -> List[Dict[str, Any]]:
    try:
        return list(ledger.read(config, STREAM))
    except Exception:
        return []
