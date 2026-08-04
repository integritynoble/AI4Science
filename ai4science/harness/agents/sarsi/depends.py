"""`DEP` — one task waiting on another, across agents.

`funding` drafting an application that needs `work`'s benchmark numbers is the
case. Without this the owner is the scheduler: they hold the ordering in their
head and start the second task when they remember the first one finished.

**Satisfied means verified.** Not stopped, not archived, not "the session said
it was done" — archiving is how a task is *closed*, and closing is not
succeeding. Treating it as satisfaction would let an abandoned task release
everything queued behind it, which is the failure this exists to prevent
happening quietly.

Two refusals, both at **declaration** time, because a task that can never run
must say so while somebody is still looking at it:

  * **an unknown dependency** — waiting forever on nothing looks exactly like
    patience;
  * **a cycle** — two tasks each waiting on the other never run, and silently
    never running is the worst outcome this board can produce.

And nothing here starts anything. When a dependency clears, the waiting task
becomes startable and stays where it is: `run` is the owner's opt-in, and it is
the only line between "I asked a question" and "I authorised work".
"""
from __future__ import annotations

from typing import Iterable, List, Optional, Tuple

from ai4science.harness.agents.sarsi import task as tsk
from ai4science.harness.agents.sarsi.registry import Agent, Config


class Unknown(Exception):
    """A dependency names something that is not there."""


class Cycle(Exception):
    """These tasks wait on each other and none of them would ever run."""


def parse_ref(ref: str, *, default_agent: str) -> Tuple[str, str]:
    """`work/tsk_abc` -> ("work", "tsk_abc"); a bare id uses this agent."""
    text = str(ref or "").strip()
    if "/" in text:
        agent_id, _, task_id = text.partition("/")
        return agent_id.strip(), task_id.strip()
    return default_agent, text


def resolve(config: Config, ref: str, *, default_agent: str):
    """(agent, task) for a reference, or None when either is missing."""
    agent_id, task_id = parse_ref(ref, default_agent=default_agent)
    agent = config.agents.get(agent_id)
    if agent is None:
        return None
    # archived included: a task filed away is still a task, and its verdict
    # still stands
    found = tsk.get(config, agent, task_id)
    return (agent, found) if found is not None else None


def satisfied(config: Config, agent: Agent, task: tsk.Task) -> List[str]:
    """The references this task waits on that are NOT yet verified."""
    waiting: List[str] = []
    for ref in (task.depends_on or []):
        got = resolve(config, ref, default_agent=agent.id)
        if got is None:
            # It vanished after being declared. Still waiting, and honestly so:
            # inventing satisfaction here would start work on absent evidence.
            waiting.append(ref)
            continue
        _, other = got
        if other.state != tsk.VERIFIED and not _was_verified(other):
            waiting.append(ref)
    return waiting


def _was_verified(task: tsk.Task) -> bool:
    """It passed before it was filed away. Closing a record does not unmake a
    verdict, so an archived-but-verified task still satisfies."""
    verdict = task.verdict or {}
    return str(verdict.get("state") or "").upper() == "PASS"


def check(config: Config, agent: Agent, refs: Iterable[str], *,
          task_id: Optional[str] = None) -> List[str]:
    """Validate a set of dependencies, or raise. Returns them normalised."""
    out: List[str] = []
    for ref in refs or []:
        got = resolve(config, ref, default_agent=agent.id)
        if got is None:
            raise Unknown(
                f"{ref!r} names no task on this machine — a dependency on "
                f"something that does not exist waits forever, and waiting "
                f"forever looks exactly like patience")
        other_agent, other = got
        normalised = f"{other_agent.id}/{other.id}"
        if task_id and other.id == task_id:
            raise Cycle(f"{task_id} cannot wait on itself")
        if task_id and _reaches(config, other_agent, other, task_id):
            raise Cycle(
                f"{normalised} already waits on {task_id}, directly or through "
                f"another task — neither would ever run")
        out.append(normalised)
    return out


def _reaches(config: Config, agent: Agent, task: tsk.Task, target: str,
             seen: Optional[set] = None) -> bool:
    """Does this task wait, at any depth, on `target`?"""
    seen = seen if seen is not None else set()
    key = f"{agent.id}/{task.id}"
    if key in seen:
        return False                  # already walked; not a path to target
    seen.add(key)
    for ref in (task.depends_on or []):
        got = resolve(config, ref, default_agent=agent.id)
        if got is None:
            continue
        other_agent, other = got
        if other.id == target:
            return True
        if _reaches(config, other_agent, other, target, seen):
            return True
    return False


def blocked(config: Config, agent: Agent) -> List[str]:
    """Task ids this worker holds that are waiting on something else."""
    return [t.id for t in tsk.all_of(config, agent)
            if t.depends_on and satisfied(config, agent, t)]
