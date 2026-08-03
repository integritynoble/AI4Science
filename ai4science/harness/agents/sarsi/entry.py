"""Where you are standing inside a worker.

Entering a worker used to put you nowhere: a board, and every message a fresh
start. Being *in* a task is what makes plain words mean something — "use the
staging host" is an instruction about the work in front of you, and without a
cursor it is a sentence with nowhere to go.

The cursor is stored per `(surface, account)` and on disk:

  * **per surface**, because the same worker read from Telegram on a phone and
    from the CLI on the machine are two places to stand. One cursor would move
    the phone when the laptop was used.
  * **on disk**, because it is where you are standing, not a variable in one
    process. A restart that forgets it is a restart that puts you back at the
    board you had already left.

It is deliberately a *pointer*, not a state machine: it holds a task id and
nothing else, so it can never disagree with the task it names. A cursor on a
task that has since been archived resolves to nothing rather than to a stale
copy of it.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from ai4science.harness.agents.sarsi import task as tsk
from ai4science.harness.agents.sarsi.registry import Agent, Config

CURSOR_NAME = "cursor.json"


def _path(agent: Agent):
    return agent.agent_dir / CURSOR_NAME


def _read(agent: Agent) -> dict:
    try:
        raw = json.loads(_path(agent).read_text())
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def current(config: Config, agent: Agent, *, surface: str) -> Optional[str]:
    """The task this surface is standing in, or None.

    Resolved against the live board every time: a cursor naming a task that has
    been archived, or one that never existed, is nowhere rather than somewhere
    stale.
    """
    task_id = _read(agent).get(surface)
    if not task_id:
        return None
    task = tsk.get(config, agent, task_id)
    if task is None or task.state == tsk.ARCHIVED:
        return None
    return task_id


def stand_in(config: Config, agent: Agent, task_id: Optional[str], *,
             surface: str) -> None:
    """Move this surface's cursor. `None` steps back out to the board."""
    data = _read(agent)
    if task_id is None:
        data.pop(surface, None)
    else:
        data[surface] = task_id
    path = _path(agent)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")
    try:
        path.chmod(0o600)
    except Exception:
        pass


# ── the record against the machine ────────────────────────────────────

@dataclass
class Reconciliation:
    """What the task records claim, beside what tmux actually has."""
    running: int = 0
    #: task ids whose record names a terminal that is not there
    missing: List[str] = field(default_factory=list)
    #: live sessions of this agent that no task claims
    unclaimed: List[str] = field(default_factory=list)
    #: tmux could not be asked at all — NOT the same as "nothing is running"
    unknown: bool = False

    @property
    def disagrees(self) -> bool:
        return bool(self.missing or self.unclaimed)

    @property
    def summary(self) -> str:
        if self.unknown:
            return (f"{self.running} task(s) hold a session record; tmux could "
                    f"not be asked, so whether they are running is unknown")
        parts = [f"{self.running} running"]
        if self.missing:
            parts.append(f"{len(self.missing)} record(s) point at a terminal "
                         f"that is gone")
        if self.unclaimed:
            parts.append(f"{len(self.unclaimed)} terminal(s) no task claims: "
                         + ", ".join(self.unclaimed))
        return "; ".join(parts)


def _live_names() -> Optional[set]:
    from ai4science.harness.agents.machine import sessions
    names = sessions.live_session_names()
    return None if names is None else set(names)


def reconcile(config: Config, agent: Agent, *,
              live: Optional[Callable[[], Optional[set]]] = None) -> Reconciliation:
    """Ask tmux what is actually running, and say where it disagrees.

    Session records outlive the process that wrote them, so a board read from
    the records alone reports state that was true at some point in the past.

    The `unknown` case is load-bearing: if the tmux server is down, every record
    looks dead. Announcing "3 terminals are gone" would be alarming and wrong,
    so an unanswerable question is reported as unanswered.
    """
    out = Reconciliation()
    if not agent.is_worker:
        return out

    try:
        names = (live or _live_names)()
    except Exception:
        names = None
    if names is None:
        out.unknown = True

    claimed = set()
    # every task, archived included: a session belonging to a closed task is
    # claimed by it, and calling it unclaimed sends the owner looking for a task
    # that is right there
    for task in (tsk.all_of(config, agent)
                 + tsk.all_of(config, agent, archived=True)):
        name = (task.session or {}).get("name")
        if not name:
            continue
        claimed.add(name)
        out.running += 1
        if names is not None and name not in names:
            out.missing.append(task.id)

    if names is not None:
        prefix = f"{agent.id}-"
        out.unclaimed = sorted(n for n in names
                               if n.startswith(prefix) and n not in claimed)
    return out


def enter(config: Config, agent: Agent, *, surface: str,
          live: Optional[Callable[[], Optional[set]]] = None) -> str:
    """What the owner sees on entering this worker.

    Three outcomes, and the empty one is the one that matters: a worker holding
    nothing **asks what you want done** rather than showing an empty board. A
    board with no rows is a dead end; a question is a way out of it.
    """
    from ai4science.harness.agents.sarsi import chat

    if not agent.is_worker:
        return chat.handle(config, agent, "self model", surface=surface)

    # The record against the machine, before anything is reported from either.
    state = reconcile(config, agent, live=live)
    note = f"\n{state.summary}" if (state.disagrees or state.unknown) else ""

    rows = tsk.all_of(config, agent)
    if not rows:
        return (f"[{agent.id}] no tasks — what would you like done?{note}\n"
                f"  tell me in one sentence:  /new <goal>\n"
                f"  I draft a plan, sarsi-claude agrees it, and nothing runs "
                f"until you release it.")

    here = current(config, agent, surface=surface)
    if here:
        task = tsk.get(config, agent, here)
        return (f"[{agent.id}] you are in {task.id}{note}\n"
                + chat.handle(config, agent, f"/{task.id}", surface=surface)
                + "\n\n/tasks steps back out to the board")
    # No cursor yet: show the board rather than guessing which one they meant.
    return chat.handle(config, agent, "/tasks", surface=surface) + note
