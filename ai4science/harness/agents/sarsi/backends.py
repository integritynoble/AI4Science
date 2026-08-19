"""The two session backends, named — `sarsi-claude` and `sarsi-ai4sci`.

A session runs one of two engines, and **which one ran a given task is a fact
about that task** — recorded with it, and not rewritten when a later task
chooses differently. That sentence is the whole reason the rename below is not
a migration.

| | `sarsi-claude` | `sarsi-ai4sci` |
|---|---|---|
| runs | Anthropic's `claude` binary | ai4science |
| the model | Anthropic's | any the exchange gateway fronts |
| needs installed | the `claude` CLI, logged in | a reachable `ai4science` |

`sarsi-ai4sci` is the DEFAULT, and the reason once given for that was false.

The claim was that it "needs nothing beyond ai4science" and so "asks less of
the owner" than a backend wanting a vendor CLI installed and signed in. That
reads as though one prerequisite were free. It is not; it is merely implicit,
and an implicit prerequisite is the kind that goes unnoticed until it fails.

Measured on this fleet, 2026-08-19, and the reverse of the claim:

  * `claude` is present on all ten accounts.
  * `import ai4science` succeeds from a login shell on FOUR of them, and fails
    with `ModuleNotFoundError` on the other six — including the account named
    `ai4science`.
  * `/usr/local/bin/ai4science` is a shim beginning `#!/usr/bin/python3`, the
    system interpreter, which has no such package. Where the backend works, it
    works through a per-account venv that a LOGIN shell puts on PATH.
  * `MachineRuntime.start` launches through `tmux new-session`, which inherits
    the tmux server's environment — a non-login shell. So the launch path does
    not even get the PATH that makes those four accounts work.

The three failure modes compound: a missing package, a shim that shadows the
working one, and a launcher that discards the PATH resolving it. None announces
itself, because `start_session` reports `ok: True` either way.

DEFAULT is left as it is rather than quietly flipped — which engine a fleet
lands on by default is the owner's call, not a docstring's, and the ACP path
now bypasses this launcher for both backends anyway. What is fixed here is the
justification, which no longer claims something untrue. Whoever decides the
default next should decide it knowing the vendor CLI is the prerequisite this
fleet actually satisfies.

RENAMED, 2026-08-19 — `sarsi-pwm` -> `sarsi-ai4sci`
    The backend used to carry the product name PWM Code while the session it
    started announced `ai4sci`; the owner renamed it so the name follows the
    thing it names. A rename of a name that has been WRITTEN DOWN is two
    obligations, and only the first is a rename:

      * every task filed before today has `backend: "sarsi-pwm"` in its
        `task.json`, and those files are not rewritten. **`sarsi-pwm` therefore
        keeps resolving, forever**, as an alias. A task that recorded it
        genuinely ran it; the record is history and history is not edited. A
        record that stops reading is a task that stops running.
      * everything filed from now on records `sarsi-ai4sci`, so the corpus
        converges instead of splitting in two.

    So: both spellings are ACCEPTED, exactly one is EMITTED, and `ALIASES` is
    declared here rather than guessed at a call site. `NAMES` deliberately does
    NOT contain the alias — `console.confirm_block` picks the other backend
    with `next(n for n in NAMES if n != chosen)`, and a third entry would turn
    the owner's `b` toggle into a wrong answer, silently.

**Drivability is not granted here.** A backend does not become drivable by
appearing in this file; it becomes drivable when a live run says so. Both
backends are now driven through **OpenClaw ACP** (`driver_for`) rather than by
reading a tmux screen — see `acp.py` for why that swap is worth making.
"""
from __future__ import annotations

from typing import Dict

#: backend name -> the ai4science agent spec its session runs.
_SPECS: Dict[str, str] = {
    # The one backend that launches a vendor binary. `session.py` keys on this
    # exact spec name, and every market-installed agent is given it.
    "sarsi-claude": "claude-code",
    # ai4science itself — the agent the owner lands in. Running it here means
    # the interface they work in, the interface a worker's session runs, and
    # the interface the supervision loop reads are one interface.
    "sarsi-ai4sci": "ai4sci",
}

NAMES = tuple(_SPECS)

#: Old spellings that must keep resolving. Read-only history: a name lands here
#: when it has been written into records that will never be rewritten, and it
#: never comes back out.
ALIASES: Dict[str, str] = {
    # 2026-08-19. Every task filed before this date carries it.
    "sarsi-pwm": "sarsi-ai4sci",
}

#: backend name -> the OpenClaw agent id whose ACP runtime serves it. Named
#: here, beside the spec, because the two travel together: one says which
#: engine, the other says how it is reached.
_ACP_AGENTS: Dict[str, str] = {
    "sarsi-claude": "sarsi-claude",
    "sarsi-ai4sci": "sarsi-ai4sci",
}

#: Named once. Two places that both decide the default will disagree, and the
#: one that disagrees quietly is the one that picks the wrong engine.
DEFAULT = "sarsi-ai4sci"


class NoSuchBackend(Exception):
    """Named a backend that does not exist, and says which do."""


def canonical(name: str) -> str:
    """The current spelling of a backend name, old spellings included.

    Does NOT validate — an unknown name comes back unchanged so that the caller
    that refuses can report what was actually typed. `spec_for` is the one that
    refuses.
    """
    key = (name or "").strip()
    return ALIASES.get(key, key)


def spec_for(name: str) -> str:
    """The ai4science spec a backend's session runs. Refuses rather than
    guessing: picking an engine for someone who typed a name wrong is how a
    task runs on something they did not choose.

    Accepts an old spelling, because a stored record is a caller too — and the
    stored record is the one caller that can never be updated.
    """
    key = canonical(name)
    if key not in _SPECS:
        raise NoSuchBackend(
            f"{(name or '').strip() or '(none)'} is not a session backend — "
            f"{', '.join(NAMES)}")
    return _SPECS[key]


def acp_agent_for(name: str) -> str:
    """The OpenClaw agent id this backend is spawned as, over ACP."""
    key = canonical(name)
    if key not in _ACP_AGENTS:
        raise NoSuchBackend(
            f"{(name or '').strip() or '(none)'} is not a session backend — "
            f"{', '.join(NAMES)}")
    return _ACP_AGENTS[key]


def driver_for(name: str) -> str:
    """How a backend's session is DRIVEN — `acp` or `tmux`.

    Both backends are `acp`. Kept as a function rather than a constant because
    the answer is a property of the backend, and a machine where ACP is not
    installed needs somewhere honest to say so.
    """
    spec_for(name)                       # refuses an unknown name
    return "acp"


def next_after(name: str = "") -> str:
    """The next backend in the offer, cycling. What `b` chooses.

    EXTENSIBILITY, and a trap removed while it is still cheap.
    `console.confirm_block` picked the other one with
    `next(n for n in NAMES if n != chosen)`, which is only correct while there
    are exactly TWO backends. The moment a third motor is added that expression
    silently returns the FIRST non-matching name and `b` stops being a way to
    reach every engine — the owner presses it twice and lands back where they
    started, having never been offered the third. Adding a backend should not
    require noticing that.

    With two names this cycles between them, which is what it did before.
    """
    order = list(NAMES)
    if not order:
        return DEFAULT
    key = canonical((name or "").strip() or DEFAULT)
    if key not in order:
        return order[0]
    return order[(order.index(key) + 1) % len(order)]


def describe(name: str) -> str:
    """One line for the confirmation block. Never raises: this text reaches a
    prompt, and a raise there would drop the REPL the owner is standing in."""
    given = (name or "").strip()
    key = canonical(given)
    was = f" (recorded as {given})" if given != key and given else ""
    if key == "sarsi-claude":
        return "sarsi-claude — Anthropic's claude binary; needs the CLI installed"
    if key == "sarsi-ai4sci":
        return (f"sarsi-ai4sci — ai4science; any LLM the gateway fronts{was}")
    return f"{given or '(none)'} — not a known backend ({', '.join(NAMES)})"


def resolve(name: str = "") -> str:
    """A backend name, defaulted AND normalised to the current spelling.

    Empty means the default rather than an error, because most callers have
    nothing to say and should get the default without having to name it. This
    is the one funnel `task.create` and `task.set_backend` both pass through,
    which is what makes "accept both spellings, write one" true everywhere
    instead of true in the places somebody remembered.
    """
    return canonical((name or "").strip() or DEFAULT)
