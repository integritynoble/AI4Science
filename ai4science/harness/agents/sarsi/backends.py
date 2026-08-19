"""The two session backends, named — `sarsi-claude` and `sarsi-pwm`.

A session has always run one of two things. `MachineRuntime.start` launches
Anthropic's `claude` binary when the spec is `claude-code`, and
`ai4science chat --mode <spec>` for everything else. The mechanism was there;
what was missing is a **name** the owner can choose at the confirmation and
switch on an existing task.

| | `sarsi-claude` | `sarsi-pwm` |
|---|---|---|
| runs | Anthropic's `claude` binary | ai4science — **PWM Code** |
| the model | Anthropic's | any the exchange gateway fronts |
| needs installed | the `claude` CLI, logged in | nothing beyond ai4science |

`sarsi-pwm` is the default because it asks less of the owner: a supervised
session on `sarsi-claude` requires a vendor CLI installed and signed in, and on
`sarsi-pwm` it does not.

**The backend belongs to the TASK, not the agent.** One worker runs many tasks,
and *which engine ran this one* is a fact about the task — recorded with it, and
not rewritten when a later task chooses differently.

**Drivability is not granted here.** `session.DRIVABLE_SPECS` is a claim that
the supervision loop has been *seen* reading an interface. A backend does not
become drivable by appearing in this file; it becomes drivable when a live run
says so. Two strings of TUI parity made `sarsi-pwm` possible to drive — only a
real session makes it true.
"""
from __future__ import annotations

from typing import Dict

#: backend name -> the ai4science agent spec its session runs.
_SPECS: Dict[str, str] = {
    # The one backend that launches a vendor binary. `session.py` keys on this
    # exact spec name, and every market-installed agent is given it.
    "sarsi-claude": "claude-code",
    # PWM Code — the agent the owner lands in. Running it here means the
    # interface they work in, the interface a worker's session runs, and the
    # interface the supervision loop reads are one interface.
    "sarsi-pwm": "unified-LLM",
}

NAMES = tuple(_SPECS)

#: Named once. Two places that both decide the default will disagree, and the
#: one that disagrees quietly is the one that picks the wrong engine.
DEFAULT = "sarsi-pwm"


class NoSuchBackend(Exception):
    """Named a backend that does not exist, and says which do."""


def spec_for(name: str) -> str:
    """The ai4science spec a backend's session runs. Refuses rather than
    guessing: picking an engine for someone who typed a name wrong is how a
    task runs on something they did not choose."""
    key = (name or "").strip()
    if key not in _SPECS:
        raise NoSuchBackend(
            f"{key or '(none)'} is not a session backend — "
            f"{', '.join(NAMES)}")
    return _SPECS[key]


def describe(name: str) -> str:
    """One line for the confirmation block. Never raises: this text reaches a
    prompt, and a raise there would drop the REPL the owner is standing in."""
    key = (name or "").strip()
    if key == "sarsi-claude":
        return "sarsi-claude — Anthropic's claude binary; needs the CLI installed"
    if key == "sarsi-pwm":
        return "sarsi-pwm — ai4science (PWM Code); any LLM the gateway fronts"
    return f"{key or '(none)'} — not a known backend ({', '.join(NAMES)})"


def resolve(name: str = "") -> str:
    """A backend name, defaulted. Empty means the default rather than an error,
    because most callers have nothing to say and should get the default without
    having to name it."""
    return (name or "").strip() or DEFAULT
