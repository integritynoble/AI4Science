"""What should happen, given the mode and a line — and nothing else.

This module never prints, never calls a model and never touches a terminal or a
subprocess. `repl.py` performs what this decides. That split is the point: the
defects that survived longest in this REPL — an unknown slash silently becoming
a prompt, the supervision loop spinning on a fact it already knew, a bare launch
dying on its first turn — were all in code reachable only by running the whole
thing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

#: The marker the ai4science TUI already uses. Kept identical so the prompt in
#: a mode reads as the same prompt, one level in — not as a different program.
MARKER = "❯ "


@dataclass(frozen=True)
class Mode:
    """Where the user is standing. Frozen: `route` returns a new one.

    A mutated-in-place mode cannot be compared before and after, and the
    invariant most worth testing here — entering costs nothing — is exactly a
    before-and-after comparison.
    """
    kind: str = "top"          # top | agent | task
    name: str = ""             # agent id or task id
    pending: Optional[str] = None   # a goal awaiting confirmation


@dataclass(frozen=True)
class Action:
    """One thing for `repl.py` to do. `kind` decides which fields are read."""
    kind: str                  # answer|say|confirm|create|guide|attach|enter|leave|noop
    text: str = ""
    goal: str = ""
    agent: Any = None
    task: Any = None
    session: str = ""


def prompt_label(mode: Mode) -> str:
    """What the prompt says. The label is not decoration — it is what makes
    'plain text becomes a goal' acceptable, because a mode that does not show
    itself is a trap."""
    if mode.kind == "agent":
        return f"{mode.name} {MARKER}"
    if mode.kind == "task":
        return f"{mode.name} (guided) {MARKER}"
    return MARKER


_COMMAND_WORD = re.compile(r"^/([A-Za-z][A-Za-z0-9_-]*)(\s|$)")


def _is_slash(line: str) -> bool:
    """An attempt at a slash, or a sentence that starts with a path?

    `/sarsi-worker` is an attempt. `/home/grace/x is missing` is a sentence, and
    refusing it would be worse than the bug this fixes. The separator is
    structure: a name is one word, a path has slashes or dots inside it.
    """
    if not _COMMAND_WORD.match(line or ""):
        return False
    first = line.split()[0]
    return "/" not in first[1:] and "." not in first[1:]


def route(line: str, mode: Mode, deps: dict) -> tuple:
    """Given where the user is and what they typed, what should happen."""
    line = (line or "").strip()
    if not line:
        return Action("noop"), mode

    if _is_slash(line):
        name, _, rest = line[1:].partition(" ")
        rest = rest.strip()

        if name.lower() == "back":
            if mode.kind == "top":
                return Action("say", text="already at the top"), mode
            return Action("leave"), Mode()

        kind, detail = deps["resolve"](name)

        if kind == "roster":
            return Action("enter", text=f"now addressing {name}"), \
                Mode(kind="agent", name=name)
        if kind == "both":
            return Action("enter",
                          text=f"{detail}. entered the worker; "
                               f"the chat spec is /agent {name}"), \
                Mode(kind="agent", name=name)
        if kind == "task":
            return Action("enter", text=f"guided on {name}"), \
                Mode(kind="task", name=name)
        if kind == "spec":
            # Not a mode: a chat spec is WHO ANSWERS, not somewhere to stand.
            return Action("say", text=f"chat agent is now {name}"), mode

        return Action("say", text=deps.get("unknown", lambda l: f"/{name} is not "
                                           "a command, and it was NOT sent to "
                                           "the model")(line)), mode

    return Action("answer", text=line), mode
