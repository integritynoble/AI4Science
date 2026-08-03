"""Recurring obligations — `abraham`'s guard against quiet accumulation.

Subscriptions, renewals and standing bookings keep costing after everyone has
forgotten them, and the agent that created them is the one least likely to
mention them again. So:

  * **a recurring obligation is its own act class.** Approving one approves
    *one schedule*, not an open-ended commitment, and it must name what it
    costs, how often, and to whom — an obligation missing any of those is not
    approvable.
  * **each one resurfaces on a cadence with what it has cost so far.** The
    running total is the number that changes the decision; the monthly price is
    the one that felt harmless when it was approved.
  * **an empty review says nothing.** Same rule as the digest: padding teaches
    the owner to skim, and a review they skim is worth nothing.
  * **cancelling keeps the record**, and stops the accrual at the cancellation
    rather than at the reading.
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ai4science.harness.agents.sarsi import ledger
from ai4science.harness.agents.sarsi.registry import Agent, Config

STORE_NAME = "recurring.json"

DAY = 86400.0
#: How often a standing obligation must be put back in front of the owner.
REVIEW_EVERY_S = 90 * DAY

_PERIOD_S = {"day": DAY, "week": 7 * DAY, "month": 30.44 * DAY,
             "quarter": 91.31 * DAY, "year": 365.25 * DAY}


class Incomplete(Exception):
    """An obligation that does not say what it costs, how often, or to whom."""


def approve(config: Config, agent: Agent, *, what: str, amount: float,
            currency: str, every: str, payee: str,
            now: Callable[[], float] = time.time) -> Dict[str, Any]:
    """Approve **one schedule**. Recorded as its own outward act class."""
    if not (every or "").strip() or every not in _PERIOD_S:
        raise Incomplete(f"a recurring obligation must say how often — 'every' "
                         f"is one of {sorted(_PERIOD_S)}")
    if not (payee or "").strip():
        raise Incomplete("a recurring obligation must name its payee")
    if amount is None:
        raise Incomplete("a recurring obligation must say what it costs")

    record = {"id": f"rec_{uuid.uuid4().hex[:8]}", "agent": agent.id,
              "what": what, "amount": float(amount), "currency": currency,
              "every": every, "payee": payee,
              "started_at": now(), "last_reviewed_at": now(),
              "cancelled_at": None}
    store = _read(agent)
    store.append(record)
    _write(agent, store)
    ledger.append(config, "outward",
                  {"agent": agent.id, "kind": "recurring", "destination": payee,
                   "digest": record["id"], "chars": len(what),
                   "outcome": "approved-schedule"}, now=now)
    return record


def all_of(config: Config, agent: Agent) -> List[Dict[str, Any]]:
    return _read(agent)


def cost_so_far(config: Config, agent: Agent, obligation_id: str, *,
                now: Callable[[], float] = time.time) -> float:
    """What this has cost since it was approved — stopping at cancellation.

    This is the number worth surfacing: the per-period price is the one that
    felt harmless when it was approved.
    """
    record = _get(agent, obligation_id)
    if record is None:
        return 0.0
    end = record.get("cancelled_at") or now()
    elapsed = max(0.0, float(end) - float(record["started_at"]))
    periods = int(elapsed // _PERIOD_S[record["every"]])
    return round(periods * float(record["amount"]), 2)


def due(config: Config, agent: Agent, *,
        now: Callable[[], float] = time.time) -> List[Dict[str, Any]]:
    stamp = now()
    return [r for r in _read(agent)
            if r.get("cancelled_at") is None
            and stamp - float(r.get("last_reviewed_at") or 0) > REVIEW_EVERY_S]


def resurface(config: Config, agent: Agent, *,
              now: Callable[[], float] = time.time) -> str:
    """What the owner is shown. Empty when nothing is due — never padded."""
    rows = due(config, agent, now=now)
    if not rows:
        return ""
    lines = ["standing obligations you approved, and what they have cost:"]
    for record in rows:
        spent = cost_so_far(config, agent, record["id"], now=now)
        lines.append(f"  {record['what']} — {record['currency']}"
                     f"{record['amount']:.2f} every {record['every']} to "
                     f"{record['payee']}; {record['currency']}{spent:.2f} so far")
    return "\n".join(lines)


def reviewed(config: Config, agent: Agent, obligation_id: str, *,
             now: Callable[[], float] = time.time) -> None:
    """The owner has seen it. Resets the cadence; does **not** cancel it."""
    store = _read(agent)
    for record in store:
        if record.get("id") == obligation_id:
            record["last_reviewed_at"] = now()
    _write(agent, store)


def cancel(config: Config, agent: Agent, obligation_id: str, *,
           now: Callable[[], float] = time.time) -> None:
    """Stops it, and keeps the record — what it cost is still answerable."""
    store = _read(agent)
    for record in store:
        if record.get("id") == obligation_id:
            record["cancelled_at"] = now()
    _write(agent, store)


def _get(agent: Agent, obligation_id: str) -> Optional[Dict[str, Any]]:
    return next((r for r in _read(agent) if r.get("id") == obligation_id), None)


def _path(agent: Agent) -> Path:
    # host-local: whose subscription, and to whom, is third-party detail that
    # abraham Rule C keeps off any shared workspace
    return agent.host / STORE_NAME


def _read(agent: Agent) -> List[Dict[str, Any]]:
    path = _path(agent)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _write(agent: Agent, store: List[Dict[str, Any]]) -> None:
    path = _path(agent)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(store, indent=2, sort_keys=True))
    try:
        path.chmod(0o600)
    except Exception:
        pass
