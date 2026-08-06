"""`QST` — the escalations, in one place, answerable from either surface.

`answering` already declines what it must not answer — secrets, anything that
would widen authority, owner facts, anything the plan does not settle — and
escalates it. Every one of those was written to the ledger and **none were ever
listed**, so the way to discover that a session was waiting on you was to
happen to notice.

Four rules, and three are refusals:

  * **the owner closes it, not the agent.** A later automatic answer does not
    clear an escalation: this class of question exists precisely because it must
    not be resolved automatically, and letting the agent close it would undo the
    decline that created it.
  * **an answer that reached no session is not an answer.** A stopped session
    cannot hear it. Recording it as answered would close the loop on the owner's
    side and leave the session exactly where it was — the same failure as a
    verdict's reason that reaches no session and steers nothing.
  * **the same question twice is one open item.** A looping session must not
    flood the list until the real ones are invisible.
  * **the reason it was escalated travels with it**, because "the session asked
    something" is not something anyone can act on.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ai4science.harness.agents.sarsi import ledger, task as tsk
from ai4science.harness.agents.sarsi.registry import Agent, Config

ASKED = "question"
#: Written when the OWNER answers. Deliberately distinct from
#: `answered-question`, which is the AGENT answering one it was allowed to.
CLOSED = "question-answered"


def __getattr__(name):
    """`NoSession` now lives in `session`, where `guide` raises it.

    One class, two names: `answer` refused this before `guide` did, and callers
    catch it as `questions.NoSession`. Two separate classes with the same
    meaning would mean an `except` that looks right and misses half the raises.
    Resolved lazily to keep this module free of a `session` import — it is
    imported *by* the loop that imports `session`.
    """
    if name == "NoSession":
        from ai4science.harness.agents.sarsi.session import NoSession
        return NoSession
    raise AttributeError(name)


class NotAsked(Exception):
    """No open question matches — answering one nobody asked helps nobody."""


class NotConfirmed(Exception):
    """It was typed, and nobody could look to see whether it landed.

    A DIFFERENT answer from `NotDelivered`, and the owner would do something
    different about each: that one says the session did not take the answer,
    this one says the screen could not be read. Folding the second into the
    first also meant retyping — up to `MAX_TRIES` — into a session that may
    have had the answer the first time.
    """


class NotDelivered(Exception):
    """It was typed and never appeared. Typed is not delivered.

    Observed live: the session was still on Claude Code's splash screen, the
    answer went into a terminal that was not listening, and the question closed
    anyway — the owner believing they had answered while the session sat exactly
    where it was.
    """


@dataclass(frozen=True)
class Question:
    task_id: str
    text: str
    why: str = ""
    at: str = ""
    agent_id: str = ""

    def __str__(self) -> str:
        where = f"{self.agent_id}/{self.task_id}" if self.agent_id else self.task_id
        return f"{where} asked: {self.text}" + (f"\n    ({self.why})" if self.why else "")


def open_of(config: Config, agent: Agent) -> List[Question]:
    """Escalations this agent is still waiting on the owner for."""
    asked: Dict[tuple, Question] = {}
    closed = set()
    try:
        entries = ledger.read(config, "reports")
    except Exception:
        return []
    for entry in entries:
        if entry.get("agent") != agent.id:
            continue
        state = str(entry.get("state") or "")
        if state not in (ASKED, CLOSED):
            continue
        task_id = str(entry.get("task") or "")
        text, why = _read(entry.get("evidence") or [])
        if not text:
            continue
        key = (task_id, text)
        if state == CLOSED:
            closed.add(key)
            continue
        # asked again: keep the first, so a looping session is one item
        asked.setdefault(key, Question(task_id=task_id, text=text, why=why,
                                       at=str(entry.get("at") or ""),
                                       agent_id=agent.id))
    return [q for key, q in asked.items() if key not in closed]


def across(config: Config) -> List[Question]:
    out: List[Question] = []
    for agent in config.workers():
        out.extend(open_of(config, agent))
    return sorted(out, key=lambda q: (q.agent_id, q.at))


#: How many times the answer is typed before the owner is told it did not land.
MAX_TRIES = 3


def answer(config: Config, agent: Agent, task: tsk.Task, question: str,
           reply: str, *, runtime: Optional[Any] = None,
           pane: Optional[Any] = None, now=time.time) -> None:
    """Deliver the owner's answer into the session, then close the question.

    In that order, and only in that order: closing first would record an answer
    that may never have arrived.

    When a `pane` is given the delivery is **confirmed on screen** before the
    question is closed, the same way the kickoff is — a session that is still
    booting swallows what is typed at it, and a closed question is the owner
    believing they answered.
    """
    from ai4science.harness.agents.sarsi import session as ses

    text = (question or "").strip()
    body = (reply or "").strip()
    if not body:
        raise NotAsked("an empty answer answers nothing")

    matching = [q for q in open_of(config, agent)
                if q.task_id == task.id and _same(q.text, text)]
    if not matching:
        raise NotAsked(
            f"{task.id} has no open question matching {text[:60]!r} — "
            f"`sarsi questions` lists what is actually waiting")

    if not (task.session or {}).get("name"):
        # `guide` refuses this too, in the same class; kept here because the
        # wording is about an ANSWER reaching nobody, and because a question
        # must not be marked closed on the way to finding that out.
        raise ses.NoSession(
            f"{task.id} has no session, so this answer would reach nobody. "
            f"Start one with `sarsi run {agent.id} {task.id}` first.")

    # by_owner: their word goes through even while the worker holds the wheel.
    text_in = (f"The owner answers your question.\nYou asked: {matching[0].text}\n"
               f"They say: {body}")
    for attempt in range(MAX_TRIES if pane is not None else 1):
        ses.guide(config, agent, task, text_in, runtime=runtime,
                  by_owner=True, now=now)
        if pane is None:
            break                     # nothing to read; recorded as sent
        try:
            screen = pane.capture(task.session["name"]) or ""
        except Exception as e:
            # NOT "" — that is what an empty screen gives, and it would send
            # this round the retry loop typing the same answer again at a
            # session nobody can see. Unknown is not "it did not land".
            raise NotConfirmed(
                f"the answer was typed into {task.session['name']} and its "
                f"screen could not be read ({type(e).__name__}: {e}), so "
                f"whether it landed is unknown — look yourself: "
                f"tmux attach -t {task.session['name']}")
        if _landed(screen, body):
            break
    else:
        raise NotDelivered(
            f"the answer was typed {MAX_TRIES} times into "
            f"{task.session['name']} and never appeared — the session is not "
            f"listening yet (a booting session swallows input). The question "
            f"stays open; try again once it is at its prompt.")

    ledger.append(config, "reports",
                  {"agent": agent.id, "task": task.id, "state": CLOSED,
                   "evidence": [f"Q: {matching[0].text}", f"A: {body[:300]}"]},
                  now=now)


def _landed(screen: str, body: str) -> bool:
    """Did the answer reach the screen? Matched on a distinctive fragment
    rather than the whole text, which a narrow pane wraps."""
    probe = body.strip().splitlines()[0][:40] if body.strip() else ""
    return bool(probe) and probe in screen


def _read(evidence: List[Any]) -> tuple:
    text, why = "", ""
    for line in evidence or []:
        s = str(line)
        if s.startswith("Q: "):
            text = s[3:].strip()
        elif s.startswith("escalated: "):
            why = s[len("escalated: "):].strip()
    return text, why


def _same(a: str, b: str) -> bool:
    """Loose enough that the owner need not retype punctuation exactly, strict
    enough that it cannot match a different question."""
    return a.strip().rstrip("?").casefold() == b.strip().rstrip("?").casefold()
