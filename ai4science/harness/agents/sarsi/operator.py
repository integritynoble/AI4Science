"""`AN` and `SP` — the two nodes between "a session starts" and "a session runs".

Both were found by the first live run, which had to be nursed by hand. Claude
Code's first-run folder-trust prompt swallowed the kickoff; the kickoff then sat
typed-but-unsubmitted at the `❯`. Neither is exotic — both are specified in the
session loop, and neither was implemented.

One pass, in this order, and the order is load-bearing:

| | Check | Then |
|---|---|---|
| 1 | is there a session at all? | nothing to operate |
| 2 | is it already verified? | stand down |
| 3 | **does the owner have the wheel?** | do nothing — the operator *is* the worker |
| 4 | is it mid-turn? | leave it alone; queued input is normal, not stuck |
| 5 | **is a gate on screen?** | `AN` — answer it if recognised, else abstain |
| 6 | **is a prompt stranded at the `❯`?** | `SP` — submit it, verbatim |

Two rules the code keeps rather than the prompt:

  * **`SP` submits verbatim.** It presses Enter. Nothing here retypes a stranded
    prompt — the composer writes a *new* instruction, it never edits one already
    typed, and merging the two would imply the agent may reword what was already
    committed to.
  * **`AN` answers from an allowlist, never a denylist.** A gate this loop does
    not recognise is left for the owner and reported. A guessed Yes is the one
    mistake here that nobody would notice until afterwards.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any, Optional

from ai4science.harness.agents.sarsi import ledger, task as tsk
from ai4science.harness.agents.sarsi.registry import Agent, Config

#: A live spinner, or an interrupt hint, means the session is mid-turn.
_BUSY = ("esc to interrupt", "✻", "⎿", "tokens)")

#: Gates this loop is allowed to answer, and the option to press. Recognised by
#: a phrase that only appears on that gate. Anything else waits for the owner.
_KNOWN_GATES = (
    (re.compile(r"Is this a project you created or one you trust", re.I), "1",
     "the folder-trust prompt, for a folder this worker created"),
)

#: The wider option — "and don't ask again" — is never pressed.
_STANDING_OPTION = re.compile(r"don'?t ask again|and stop asking", re.I)

_GATE_SHAPE = re.compile(r"^\s*❯?\s*1\.\s+\S", re.M)
# `[^\S\r\n]` is "whitespace that is not a line break": it must not swallow the
# newline (a bare `❯` would then "find" the next line and submit an empty
# prompt), and it must accept U+00A0 — Claude Code's TUI separates the `❯` from
# the text with a NON-BREAKING space, which a plain `[ \t]` misses. The first
# operator run reported `idle` at a visibly stranded screen for exactly that.
_PROMPT_LINE = re.compile(r"^❯[^\S\r\n]+(?P<text>\S.*)$", re.M)


@dataclass(frozen=True)
class Action:
    kind: str            # answered | submitted | abstained | busy | idle | …
    detail: str = ""


def tick(config: Config, agent: Agent, task: tsk.Task, *, pane: Any,
         now=time.time) -> Action:
    """One supervision pass over one session."""
    session = (task.session or {}).get("name")
    if not session:
        return Action("no-session")
    if task.state == tsk.VERIFIED:
        return Action("done", "the verifier has already passed this")
    if task.steering_paused:
        # Interact pauses the worker, and the operator IS the worker.
        return Action("paused", "the owner has the wheel")

    screen = pane.capture(session) or ""

    gate = _gate(screen)
    if gate is not None:
        answer, why = gate
        if answer is None:
            _report(config, agent, task, state="gate",
                    evidence=f"a gate this loop does not recognise: {why}", now=now)
            return Action("abstained", why)
        pane.send(session, answer)
        _report(config, agent, task, state="answered",
                evidence=f"pressed {answer} — {why}", now=now)
        return Action("answered", why)

    if _busy(screen):
        # A permission menu's cursor is not a prompt, and a live spinner means
        # queued input is normal rather than stuck.
        return Action("busy")

    stranded = _stranded(screen)
    if stranded:
        pane.key(session, "Enter")          # verbatim: nothing is retyped
        _report(config, agent, task, state="submitted",
                evidence=stranded[:200], now=now)
        return Action("submitted", stranded[:80])

    return Action("idle")


def run(config: Config, agent: Agent, task: tsk.Task, *, pane: Any,
        passes: int = 20, interval: float = 3.0, sleep=time.sleep) -> list:
    """Keep nudging until the session is moving on its own."""
    seen = []
    for i in range(passes):
        action = tick(config, agent, task, pane=pane)
        seen.append(action)
        if action.kind in ("no-session", "done", "paused"):
            break
        if i + 1 < passes:
            sleep(interval)
    return seen


# ── reading the screen ────────────────────────────────────────────────

def _gate(screen: str):
    """(answer, why) when a gate is on screen; (None, why) when unrecognised."""
    if not _GATE_SHAPE.search(screen):
        return None
    for pattern, answer, why in _KNOWN_GATES:
        if pattern.search(screen):
            return (answer, why)
    return (None, "an option menu this loop has no rule for")


def _busy(screen: str) -> bool:
    low = screen.lower()
    return any(marker.lower() in low for marker in _BUSY)


def _stranded(screen: str) -> Optional[str]:
    """Text typed at the `❯` and left unsent. An empty prompt is not stranded."""
    hits = _PROMPT_LINE.findall(screen)
    if not hits:
        return None
    text = hits[-1].strip()
    return text or None


def _report(config: Config, agent: Agent, task: tsk.Task, *, state: str,
            evidence: str, now) -> None:
    ledger.append(config, "reports",
                  {"agent": agent.id, "task": task.id, "state": state,
                   "evidence": [evidence]}, now=now)


# ── the real pane ─────────────────────────────────────────────────────

class TmuxPane:
    """The real one: read and type into a live tmux pane."""

    def capture(self, name: str) -> str:
        import subprocess
        try:
            out = subprocess.run(["tmux", "capture-pane", "-p", "-t", name],
                                 capture_output=True, text=True, timeout=10)
            return out.stdout if out.returncode == 0 else ""
        except Exception:
            return ""

    def send(self, name: str, text: str):
        from ai4science.harness.agents.machine import sessions
        return sessions.send_to_session(name, text)

    def key(self, name: str, key: str):
        from ai4science.harness.agents.machine import sessions
        return sessions.send_to_session(name, "", enter=False, key=key)
