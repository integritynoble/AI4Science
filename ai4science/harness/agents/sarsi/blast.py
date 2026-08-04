"""`BLR` — what the plan said it would touch, against what it touched.

The plan already declares a working directory for evidence. The same
declaration answers a second question: *did it stay there?* The session's own
transcript records every `Write` and `Edit` with its `file_path`, so what was
written is **read**, not inferred — the same source `spend` reads, asked a
different question.

One refusal carries the whole value:

  **`Bash` is opaque, and opaque is never reported as clean.**

A transcript with forty shell commands and two writes tells us about the two.
Answering "nothing outside the radius" on that evidence would be a confident
claim about the forty, and this system has produced enough of those already —
a narrated `PASS` read as a verdict, `0 tokens` for an hour-long session,
"nothing visible was supplied" about work that was done. So a report carries
three parts and always the third:

  * what was written **inside** the declared paths,
  * what **escaped** them, named,
  * and how much **could not be checked at all**.

`escaped is False` therefore means *nothing observed escaped*. Only
`confident is True` means there was nothing left unobserved to worry about.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ai4science.harness.agents.sarsi import task as tsk
from ai4science.harness.agents.sarsi.registry import Agent, Config

#: Tools that CHANGE a named file. A radius is about what was changed — counting
#: `Read` would flag every session that looked at its own source.
_WRITERS = ("Write", "Edit", "NotebookEdit", "MultiEdit")

#: Tools that can change anything and say nothing about what.
_OPAQUE = ("Bash", "BashOutput", "KillShell")


@dataclass
class Radius:
    inside: List[str] = field(default_factory=list)
    outside: List[str] = field(default_factory=list)
    #: acts that could change a file without naming one
    unchecked: int = 0
    #: could the transcript be read at all?
    read: bool = True
    declared: List[str] = field(default_factory=list)

    @property
    def escaped(self) -> bool:
        """Something OBSERVED went outside. Not the same as "it stayed in"."""
        return bool(self.outside)

    @property
    def confident(self) -> bool:
        """Was there anything left unobserved? Only this may be read as clean."""
        return self.read and self.unchecked == 0

    @property
    def summary(self) -> str:
        if not self.read:
            return ("no record of what it touched — the session transcript "
                    "could not be read, so this is not a clean bill")
        parts = []
        if self.outside:
            parts.append(f"{len(self.outside)} file(s) written OUTSIDE the "
                         f"declared paths: " + ", ".join(self.outside[:5]))
        else:
            parts.append(f"nothing observed outside the declared paths "
                         f"({len(self.inside)} write(s) inside)")
        if self.unchecked:
            parts.append(f"{self.unchecked} shell command(s) could not be "
                         f"checked — they name no file, so this is not a "
                         f"clean bill")
        return " · ".join(parts)


def declared(agent: Agent, task: tsk.Task) -> List[Path]:
    """The paths this task is allowed to change.

    The evidence root, plus anything the plan additionally declared. Declared,
    never inferred — the same rule the evidence root follows, for the same
    reason: a path the agent touched must not be able to authorise itself.
    """
    # every evidence root, which always includes the task's own folder — the
    # session runs there, and writing where it runs is not an escape
    roots = list(tsk.evidence_roots(agent, task))
    for extra in (task.may_touch or []):
        try:
            roots.append(Path(str(extra)).expanduser().resolve())
        except OSError:
            continue
    return roots


def acts_of(cwd: str) -> List[Dict[str, Any]]:
    """Every tool use in this working directory's transcript.

    Raises when it cannot be read, so the caller can tell "it touched nothing"
    from "we have no idea what it touched".
    """
    from ai4science.harness.agents.machine import sessions

    path = sessions._transcript_path(str(cwd))
    if not path:
        raise FileNotFoundError(f"no Claude Code transcript for {cwd}")
    out: List[Dict[str, Any]] = []
    for file in sorted(Path(path).parent.glob("*.jsonl")):
        try:
            handle = open(file, errors="replace")
        except OSError:
            continue
        with handle:
            for line in handle:
                try:
                    entry = json.loads(line)
                except Exception:
                    continue
                content = (entry.get("message") or {}).get("content")
                if not isinstance(content, list):
                    continue
                for part in content:
                    if (isinstance(part, dict)
                            and part.get("type") == "tool_use"):
                        out.append({"name": part.get("name"),
                                    "input": part.get("input") or {}})
    return out


def check(config: Config, agent: Agent, task: tsk.Task, *,
          acts: Optional[Callable[[str], List[Dict[str, Any]]]] = None) -> Radius:
    """What it wrote, against what it was allowed to write."""
    roots = declared(agent, task)
    out = Radius(declared=[str(r) for r in roots])

    cwd = (task.session or {}).get("cwd")
    if not cwd:
        for record in (task.past_sessions or []):
            if record.get("cwd"):
                cwd = record["cwd"]
                break
    if not cwd:
        out.read = False
        return out

    try:
        entries = (acts or acts_of)(cwd)
    except Exception:
        out.read = False
        return out

    for entry in entries:
        name = str(entry.get("name") or "")
        if name in _OPAQUE:
            # It can change anything and names nothing. Counted, never ignored.
            out.unchecked += 1
            continue
        if name not in _WRITERS:
            continue
        path = (entry.get("input") or {}).get("file_path")
        if not path:
            out.unchecked += 1
            continue
        if _within(str(path), roots):
            out.inside.append(str(path))
        else:
            out.outside.append(str(path))
    return out


def _within(path: str, roots: List[Path]) -> bool:
    try:
        resolved = Path(path).expanduser().resolve()
    except OSError:
        return False
    for root in roots:
        if resolved == root or root in resolved.parents:
            return True
    return False
