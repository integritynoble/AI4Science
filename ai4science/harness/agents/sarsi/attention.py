"""`ATT` — is anything waiting on the owner?

Everything that went wrong on the live runs went wrong **silently**: a gate the
supervision loop had no rule for, Claude Code's first-run trust dialog, a
session finishing a turn having written nothing. Catching any of it took a human
watching `tmux`. A worker that cannot answer *"is anything waiting on you?"*
makes the owner the monitor — which is the job the worker exists to remove.

Nothing here is new information. Gates are on the pane, `awaiting` is on the
task, so are the retry count and the stale flag, and the session record says
which terminal it believes in. They were simply never read together.

Three rules:

  * **it is about the owner, not about progress.** A busy session is not on this
    list. A list that includes healthy work teaches the owner to skim it, and a
    skimmed list is the same as no list.
  * **a gate carries the actual command.** "A gate is waiting" tells the owner to
    go and look; the command tells them whether they need to.
  * **it never reports a blockage it cannot see.** A pane that will not read is
    reported as a session whose terminal is gone — not as idle, and not as fine.
    Reporting state that was true when it was written is how a board lies.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, List, Optional

from ai4science.harness.agents.sarsi import operator as op, task as tsk
from ai4science.harness.agents.sarsi.registry import Agent, Config

#: Most blocking first. A gate stops work *now*; a stale plan stops the next
#: decision. The order is the whole value of the list — the owner reads down it
#: until they run out of time, so what they read first has to be what matters.
ORDER = ("gate", "unclaimed", "orphan", "grant", "question", "over-budget",
         "exhausted", "attended", "undelivered", "handoff", "proposal",
         "dead-session", "drift", "stale")

#: States in which nothing is steering the session any more. A terminal still
#: running past one of these is an ORPHAN — the reverse of a dead session, and
#: the more dangerous of the two: nobody is driving it and it still holds
#: whatever the task was granted.
ENDED_STATES = (tsk.VERIFIED, tsk.OFF, tsk.REFUSED, tsk.ARCHIVED)

#: The command a gate is asking about, as Claude Code renders it: an indented
#: block above the "Do you want to proceed?" line.
_COMMAND = re.compile(r"^\s{2,}(?P<cmd>\S.*)$", re.M)


@dataclass(frozen=True)
class Item:
    kind: str
    task_id: str
    detail: str
    agent_id: str = ""
    action: str = ""

    def __str__(self) -> str:
        where = f"{self.agent_id}/{self.task_id}" if self.agent_id else self.task_id
        return f"{self.kind}: {where} — {self.detail}"


@dataclass
class Attention:
    items: List[Item] = field(default_factory=list)

    @property
    def summary(self) -> str:
        if not self.items:
            return "nothing is waiting on you"
        counts: dict = {}
        for item in self.items:
            counts[item.kind] = counts.get(item.kind, 0) + 1
        parts = [f"{counts[k]} {k}" for k in ORDER if k in counts]
        return f"{len(self.items)} waiting on you: " + ", ".join(parts)

    def __bool__(self) -> bool:
        return bool(self.items)


def needs(config: Config, agent: Agent, *, pane: Optional[Any] = None,
          live: Optional[Any] = None) -> Attention:
    """What is waiting on the owner across everything this worker holds.

    `live` lists the tmux sessions that actually exist. **Left as `None` it
    asks the real machine**, which is right in the CLI and a trap in a test: a
    session some other process started here will be reported as this agent's.
    Tests inject it.

    It is what lets a terminal NO task claims be reported — the reverse of a dead-session record, and the more
    dangerous one: something is running, still holding whatever it was granted,
    and the board shows nothing at all.
    """
    if not agent.is_worker:
        # It drives nothing, so it can be blocked on nothing.
        return Attention()
    items: List[Item] = []
    for task in tsk.all_of(config, agent):          # archived is not waiting
        items.extend(_for_task(config, agent, task, pane=pane))
    items.extend(_unclaimed(config, agent, live))
    items.extend(_proposal(config, agent))
    items.extend(_handoff(config, agent))
    items.sort(key=lambda i: (ORDER.index(i.kind) if i.kind in ORDER
                              else len(ORDER), i.task_id))
    return Attention(items=items)


def across(config: Config, *, pane: Optional[Any] = None,
           live: Optional[Any] = None) -> Attention:
    """The same question across every worker — the fleet view."""
    items: List[Item] = []
    for agent in config.workers():
        for item in needs(config, agent, pane=pane, live=live).items:
            items.append(Item(kind=item.kind, task_id=item.task_id,
                              detail=item.detail, agent_id=agent.id,
                              action=item.action))
    items.sort(key=lambda i: (ORDER.index(i.kind) if i.kind in ORDER
                              else len(ORDER), i.agent_id, i.task_id))
    return Attention(items=items)


def _proposal(config: Config, agent: Agent) -> List[Item]:
    """A house rule the agent has asked for and cannot adopt itself.

    Listed because a proposal nobody sees is a proposal nobody signs — it would
    sit there looking exactly like an agent that never asked.
    """
    from ai4science.harness.agents.sarsi import rules as rl
    try:
        held = rl.pending(config, agent)
    except Exception:
        return []
    if not held:
        return []
    return [Item("proposal", "",
                 f"it asks for a standing house rule: {held['rule']!r} "
                 f"— because {held.get('because', '')}",
                 action=f"sarsi rules {agent.id} --sign   (or --discard)")]


def _handoff(config: Config, agent: Agent) -> List[Item]:
    """Work another worker finished and thinks this one should carry on.

    It creates nothing until the owner accepts, so an unseen handoff is one
    that never happens — and the worker that raised it has no way to chase.
    """
    from ai4science.harness.agents.sarsi import relay
    try:
        held = relay.pending(config, agent)
    except Exception:
        return []
    if not held:
        return []
    return [Item("handoff", "",
                 f"{held['from_agent']} finished {held['from_task']} and asks "
                 f"this one to: {held['goal']!r} — because {held['because']}",
                 action=f"sarsi handoff {agent.id} --accept   (or --decline)")]


def _unclaimed(config: Config, agent: Agent, live) -> List[Item]:
    """Live terminals of this agent that no task points at.

    When tmux cannot be asked this reports NOTHING — it cannot see them, so it
    must neither claim there are none nor invent any. An unreachable tmux is
    `enter`'s business, where it is stated as unknown rather than as news.
    """
    from ai4science.harness.agents.sarsi import entry

    state = entry.reconcile(config, agent, live=live)
    return [Item("unclaimed", "",
                 f"session {name} is running and no task claims it — it still "
                 f"holds whatever it was granted",
                 action=f"tmux attach -t {name}   (then kill it, or find its "
                        f"task)")
            for name in state.unclaimed]


# ── one task ──────────────────────────────────────────────────────────

def _for_task(config: Config, agent: Agent, task: tsk.Task, *,
              pane: Optional[Any]) -> List[Item]:
    from ai4science.harness.agents.sarsi import retry as rty

    out: List[Item] = []

    from ai4science.harness.agents.sarsi import questions as qst
    for question in qst.open_of(config, agent):
        if question.task_id == task.id:
            out.append(Item("question", task.id,
                            f"the session asked: {question.text}"
                            + (f" ({question.why})" if question.why else ""),
                            action=f"sarsi answer {agent.id} {task.id} "
                                   f"\"{question.text}\" \"<your answer>\""))

    if task.awaiting:
        out.append(Item("grant", task.id,
                        "not granted: " + ", ".join(task.awaiting),
                        action=f"sarsi grant {agent.id} {task.id} "
                               f"\"{task.awaiting[0]}\""))

    if _over_budget(config, agent, task):
        out.append(Item("over-budget", task.id,
                        "it ran past the budget its plan declared and was "
                        "stopped — the plan and history are intact",
                        action=f"sarsi plan {agent.id} {task.id}"))

    if int(task.retries or 0) >= rty.MAX_RETRIES:
        verdict = task.verdict or {}
        reason = (verdict.get("why") or verdict.get("reason")
                  or "no reason recorded")
        out.append(Item("exhausted", task.id,
                        f"handed back {task.retries} times and still fails: {reason}",
                        action=f"sarsi plan {agent.id} {task.id}"))

    if task.kickoff_undelivered:
        out.append(Item("undelivered", task.id,
                        "its first instruction was typed and never appeared on "
                        "screen",
                        action=f"tmux attach -t {(task.session or {}).get('name', '')}"))

    drifted = tsk.criteria_drift(agent, task)
    if drifted:
        # The owner would otherwise learn about it only from a verdict's note,
        # and `sarsi plan` renders the FILE — so the board and the plan would
        # disagree in front of them with nothing to explain it.
        which = ", ".join(str(i + 1) for i in drifted)
        if task.released_at is not None or task.plan_owner_edited:
            # Not blocked: judging goes on against what the owner released.
            # Saying "refused" here would send them to `adopt` to unblock a run
            # that is not blocked, which is how adopting became a habit.
            detail = (f"{task.plan_version}.md was edited after you released "
                      f"this — phase {which} reads differently there. Verdicts "
                      f"still apply what you released; adopt only if you want "
                      f"the file to become the standard")
        else:
            detail = (f"{task.plan_version}.md was edited after this task "
                      f"was attached — phase {which} reads differently "
                      f"there, and judging is refused until you settle "
                      f"which one is the standard")
        out.append(Item("drift", task.id, detail,
                        action=f"sarsi adopt {agent.id} {task.id}"))

    if task.plan_stale:
        out.append(Item("stale", task.id,
                        "its plan no longer matches what is being done; its "
                        "criteria are withheld",
                        action=f"sarsi ask {agent.id} \"/edit {task.id} 1 "
                               f"<criterion>\""))

    from ai4science.harness.agents.sarsi import session as _ses
    name = (task.session or {}).get("name")
    if name and not _ses.drivable(agent.spec):
        # It is running an interface this loop cannot read, so it will make no
        # progress on its own. Saying so is the difference between a session
        # waiting for its owner and one that is simply slow.
        out.append(_attended(agent, task, name, pane))
    elif name and pane is not None:
        out.extend(_from_pane(agent, task, name, pane))
    return out


def _over_budget(config: Config, agent: Agent, task: tsk.Task) -> bool:
    """Was this task stopped for running past its budget?

    Read from the ledger rather than recomputed: the session is gone by then,
    so the numbers that justified stopping cannot be measured again.
    """
    from ai4science.harness.agents.sarsi import ledger
    try:
        entries = ledger.read(config, "reports")
    except Exception:
        return False
    for entry in reversed(entries):
        if entry.get("agent") == agent.id and entry.get("task") == task.id:
            state = str(entry.get("state") or "")
            if state == "over-budget":
                return True
            if state in ("verified", "retried", "steered"):
                return False          # it moved on
    return False


#: A block of numbered options — the one shape worth pointing at on an
#: interface nobody has parsed. It says a choice is probably on screen; it says
#: nothing about what the options mean, and neither does the item.
_CHOICE = re.compile(r"^\s*❯?\s*1[.)]\s+\S", re.M)

#: How much of a pane belongs in a line about what is waiting. A pane is a
#: screenful; an attention item is a line.
_SCREEN_LINES = 8
_SCREEN_CHARS = 400


def _attended(agent: Agent, task: tsk.Task, name: str, pane: Any) -> Item:
    """An attended session, and — when it can be read — what is on its screen.

    The loop cannot *drive* this interface, and that is the reason it will make
    no progress on its own. It is not a reason to leave the owner guessing:
    `capture-pane` is read-only, and the danger that argued for standing back
    was blind *typing*, not looking. So this looks, and reports what it saw
    without claiming to know what it means.
    """
    head = (f"{agent.id} runs the {agent.spec!r} interface, which the "
            f"supervision loop cannot read — it needs you")
    action = f"tmux attach -t {name}"
    if pane is None:
        return Item("attended", task.id, head, action=action)

    try:
        screen = pane.capture(name)
    except Exception:
        screen = None
    if screen is None:
        # Unknown is not "nothing is waiting". An attended session whose pane
        # will not read may be gone, and that is the more urgent fact.
        return Item("attended", task.id,
                    f"{head}. Its pane could not be read, so whether it is "
                    f"waiting, working or gone is unknown", action=action)

    tail = _screen_tail(screen)
    if not tail:
        return Item("attended", task.id, f"{head}. Its screen is blank",
                    action=action)
    # Hedged, and only on a shape: naming what the options MEAN would be the
    # same over-claim as driving them.
    hint = (" It looks like it is showing a numbered choice."
            if _CHOICE.search(screen) else "")
    return Item("attended", task.id, f"{head}.{hint} On its screen:\n{tail}",
                action=action)


#: Furniture: a rule of box-drawing characters, or an empty input prompt. Seen
#: live — keeping the last N lines of a real gate kept the INPUT BOX (two
#: rules, a status bar, a bare `❯`) and pushed the question and the command it
#: was asking about off the top. Dropping a line that is only box-drawing
#: characters is filtering decoration, not interpreting content: it says
#: nothing, in any interface.
_CHROME = re.compile(r"^[\s─━═\-_|│┃┆┊]*$|^\s*❯\s*$")


def _screen_tail(screen: str) -> str:
    """The last few lines that have anything on them, newest kept.

    Trimmed from the FRONT when it is too long: what a session is waiting for
    is at the bottom of its pane, so a cap taken off the end would drop exactly
    the part worth reading.
    """
    lines = [line.rstrip() for line in (screen or "").splitlines()
             if line.strip() and not _CHROME.match(line)]
    kept = lines[-_SCREEN_LINES:]
    while kept and len("\n".join(kept)) > _SCREEN_CHARS:
        kept.pop(0)
    return "\n".join(f"    {line}" for line in kept)


def _from_pane(agent: Agent, task: tsk.Task, name: str, pane: Any) -> List[Item]:
    """What the session's own screen says. Unreadable is an answer, not a gap."""
    ended = task.state in ENDED_STATES
    try:
        screen = pane.capture(name)
    except Exception:
        screen = None
    if screen is None:
        if ended:
            # The task is over and so is its terminal: the record and the machine
            # agree, nothing is running, nothing holds a grant. Closing the stale
            # record is tidiness, and this list is for what needs the OWNER.
            return []
        # A live task whose terminal will not answer. Saying so beats both
        # "idle" and silence — the owner can see it is gone; the record cannot.
        return [Item("dead-session", task.id,
                     f"its record points at session {name}, which is not there",
                     action=f"sarsi stop {agent.id} {task.id}")]

    if task.state in ENDED_STATES:
        # Observed on the other fleet: a session sat running for two hours after
        # its task had FAILED, holding a grant at A2, and nothing reported it.
        return [Item("orphan", task.id,
                     f"its task is {task.state} but session {name} is still "
                     f"running, holding whatever it was granted",
                     action=f"sarsi stop {agent.id} {task.id}")]

    gate = op._gate(screen, planning=not task.plan_agreed)
    if gate is not None and gate[0] is None:
        # A gate the loop will not answer: the owner's, by construction.
        return [Item("gate", task.id,
                     f"{gate[1]}{_command(screen)}",
                     action=f"tmux attach -t {name}")]
    return []


def _command(screen: str) -> str:
    """The command the gate is about, when the screen shows one.

    Reported as ` — asking about: <cmd>` so the owner can decide from the list
    whether they need to attach at all. Absent rather than guessed: a gate whose
    subject cannot be read says nothing rather than something plausible.
    """
    head = screen.split("Do you want to proceed", 1)[0]
    lines = [m.group("cmd").strip() for m in _COMMAND.finditer(head)]
    lines = [ln for ln in lines if not ln.lower().startswith(("bash command",
                                                              "hook "))]
    if not lines:
        return ""
    text = " ".join(lines)
    return f" — asking about: {text[:200]}"
