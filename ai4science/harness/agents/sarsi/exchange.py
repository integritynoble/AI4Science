"""`EXC` — the node that earns, and never touches the owner's work.

    When it runs short, an exchange node starts: visible, bounded by a budget
    the owner sets, and never touching the owner's tasks — it is not a worker,
    holds no task list, and may not drive a session. With enough PWM the owner
    may stop it.

Four properties, three of them refusals — the right proportion for a thing that
runs on the owner's machine to make money. Every way it could quietly become
something else is closed by a code path rather than by intention:

  * **it is not a worker.** `workers()` does not offer it, `admit` refuses it,
    and `assign` refuses to drive a session for it. This is the invariant *the
    agent you talk to does not execute* with a sibling — **the thing that earns
    does not work for you.** A node that could hold a task would be an agent
    nobody granted anything to, running on the owner's machine, paid by someone
    else.
  * **it holds no task list.** Not an empty one: asking raises, because an
    empty list is a thing something can fill.
  * **it is bounded.** It will not start without a budget the owner set, and it
    stops at it. An earner with no ceiling is a machine deciding for itself how
    much of the owner's electricity to spend.
  * **it is visible.** It appears in the listings the owner already reads, as
    its own role, so a machine that is earning never looks like one that is
    idle.

It records what it supplied and **moves nothing** — the same line `earnings`
holds, for the same reason: settling is the platform's, never this machine's.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from ai4science.harness.agents.sarsi import ledger
from ai4science.harness.agents.sarsi.registry import Config, config_path

#: Its own id and its own role. NOT `worker`, and the role is what every
#: refusal keys on — a node that shared the worker role would be one rename
#: away from being handed work.
NODE_ID = "exchange-node"
ROLE = "exchange"

STREAM = "exchange"


class NotAnAgent(Exception):
    """It is a node, not an agent, and this says which thing was asked of it."""


@dataclass
class Status:
    running: bool = False
    budget: float = 0.0
    earned: float = 0.0
    why: str = ""

    @property
    def summary(self) -> str:
        if self.running:
            return (f"earning — {self.earned:g} of {self.budget:g} PWM "
                    f"supplied. It holds no tasks and drives no sessions")
        return self.why


def start(config: Config, *, budget_pwm: Optional[float],
          now=time.time) -> Status:
    """Start the node, bounded. Refuses without a budget the owner set."""
    if budget_pwm is None or float(budget_pwm) <= 0:
        raise NotAnAgent(
            "the exchange node needs a budget before it starts — an earner "
            "with no ceiling is a machine deciding for itself how much of "
            "your electricity to spend. `--budget-pwm <n>`")
    budget = float(budget_pwm)
    raw = _raw(config)
    entries = raw.setdefault("agents", {}).setdefault("list", [])
    if not any(e.get("id") == NODE_ID for e in entries):
        entries.append({"id": NODE_ID, "role": ROLE, "spec": "manager",
                        "tools": [], "ceiling": "A0"})
    _save(config, raw)
    ledger.append(config, STREAM,
                  {"event": "started", "budget": budget}, now=now)
    return status(config)


def stop(config: Config, now=time.time) -> Status:
    """The owner's, at any time. Takes it out of the roster; keeps the record."""
    raw = _raw(config)
    block = raw.setdefault("agents", {})
    block["list"] = [e for e in block.get("list", []) if e.get("id") != NODE_ID]
    raw["bindings"] = [b for b in (raw.get("bindings") or [])
                       if b.get("agentId") != NODE_ID]
    _save(config, raw)
    ledger.append(config, STREAM, {"event": "stopped"}, now=now)
    return status(config)


def supplied(config: Config, *, kind: str, pwm: float, now=time.time) -> Status:
    """Record capacity supplied to somebody else's run.

    Refused when the node is not running: a record that kept growing for a
    stopped node would credit the owner for something their machine did not do.
    """
    here = status(config)
    if not here.running:
        raise NotAnAgent(f"the exchange node is not running, so nothing was "
                         f"supplied — {here.why}")
    ledger.append(config, STREAM,
                  {"event": "supplied", "kind": str(kind),
                   "pwm": float(pwm)}, now=now)
    after = status(config)
    if not after.running:
        # Reaching the budget stops it. Recorded as its own event so the owner
        # can tell a node they stopped from one that finished.
        ledger.append(config, STREAM,
                      {"event": "stopped", "why": "reached its budget"},
                      now=now)
        _drop(config)
    return after


def status(config: Config) -> Status:
    events = _rows(config)
    if not events:
        return Status(running=False,
                      why="the exchange node has never been started here")
    budget, earned, started = 0.0, 0.0, False
    why = ""
    for e in events:
        kind = e.get("event")
        if kind == "started":
            started, budget, why = True, float(e.get("budget") or 0.0), ""
        elif kind == "stopped":
            started = False
            # Kept: "the owner stopped it" and "it finished its budget" are
            # different facts, and only the second means it did all it was
            # asked to.
            why = str(e.get("why") or "")
        elif kind == "supplied":
            earned += float(e.get("pwm") or 0.0)
    if started and earned >= budget:
        return Status(running=False, budget=budget, earned=earned,
                      why=f"it reached its budget of {budget:g} PWM "
                          f"({earned:g} supplied) and stopped")
    if not started:
        tail = f" — {earned:g} PWM supplied while it ran"
        return Status(running=False, budget=budget, earned=earned,
                      why=(f"stopped: {why}{tail}" if why
                           else f"stopped{tail}"))
    return Status(running=True, budget=budget, earned=earned)


def tasks_of(config: Config) -> List[Any]:
    """There is no task list, and this raises rather than returning `[]`.

    An empty list is a thing something can fill. Saying "it holds none" is a
    fact about a list that exists; this is the absence of one.
    """
    raise NotAnAgent(
        "the exchange node holds no task list. It is not a worker: it supplies "
        "capacity to other people's runs and never touches yours")


# ── the registry file ─────────────────────────────────────────────────

def _path(config: Config) -> Path:
    return Path(config.path) if config.path else config_path(config.root)


def _raw(config: Config) -> Dict[str, Any]:
    try:
        return json.loads(_path(config).read_text())
    except FileNotFoundError:
        raise NotAnAgent(f"no registry at {_path(config)}; run `sarsi init`")


def _save(config: Config, raw: Dict[str, Any]) -> None:
    _path(config).write_text(json.dumps(raw, indent=2, sort_keys=True))


def _drop(config: Config) -> None:
    raw = _raw(config)
    block = raw.setdefault("agents", {})
    block["list"] = [e for e in block.get("list", []) if e.get("id") != NODE_ID]
    _save(config, raw)


def _rows(config: Config) -> List[Dict[str, Any]]:
    try:
        return list(ledger.read(config, STREAM))
    except Exception:
        return []
