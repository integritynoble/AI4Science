"""`TRI` — "who should do this?", answered by the manager.

`sarsi-machine` is the agent you talk to when you do not know which worker a
demand belongs to. It has exactly one power here: **it suggests**. It does not
create the task, and that is not a policy setting — it is the invariant the
whole design rests on, that *the agent you talk to does not execute*. Nothing in
this module writes a task, and `worker.admit` refuses the manager outright, so
routing cannot become a back door to the thing routing exists to avoid.

Evidence, strongest first:

  * **precedent** — a worker that has already *verified* similar work. A result,
    not a claim, which is why it outranks everything else. Work merely *held* is
    not precedent: holding a similar task proves nothing about finishing one.
  * **declared tools** — what the roster says it has.
  * **its name**, last and weakest.

Two refusals matter more than the ranking:

  * **it does not pick when nothing distinguishes them.** Routing personal work
    to `work`, or professional work to `abraham`, is a scope mistake with real
    consequences — and "I cannot tell" is a better answer than a confident wrong
    one, because the owner can act on it.
  * **every suggestion says why**, naming the task it cites. A ranking with no
    reason is a guess wearing a number, and a number cannot be checked.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

from ai4science.harness.agents.sarsi import task as tsk
from ai4science.harness.agents.sarsi.registry import Config

#: Weights, ordered by how much the evidence is worth. Precedent is a finished
#: result; a tool is a declaration; a name is a coincidence of wording.
BY_PRECEDENT = 10
#: What the roster says the agent is FOR — stronger than a tool it happens to
#: hold, because a tool is a capability and this is a purpose.
BY_ABOUT = 4
BY_TOOL = 3
BY_NAME = 1

#: Words too common to distinguish one worker from another.
_STOP = {"the", "a", "an", "and", "or", "to", "for", "of", "in", "on", "with",
         "my", "our", "this", "that", "it", "is", "be", "do", "run", "make",
         "get", "put", "handle", "thing", "please", "up", "out", "at", "by"}


@dataclass(frozen=True)
class Candidate:
    agent_id: str
    score: int
    why: str


@dataclass
class Suggestion:
    candidates: List[Candidate] = field(default_factory=list)
    best: Optional[Candidate] = None
    #: two or more candidates that cannot be separated
    tied: List[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        if self.best is not None:
            return (f"{self.best.agent_id} — {self.best.why}\n"
                    f"  hand it over: sarsi do {self.best.agent_id} \"<goal>\"")
        if self.tied:
            return (f"{' and '.join(self.tied)} look equally likely — which "
                    f"did you mean?\n  nothing was created; say the word and "
                    f"I will not guess between them")
        return ("I cannot tell from that which worker it belongs to. Say more "
                "about what it involves, or name the worker yourself — "
                "guessing between them is a scope mistake, not a coin toss")


def suggest(config: Config, demand: str) -> Suggestion:
    """Who this demand most likely belongs to, and why. Creates nothing."""
    text = (demand or "").strip()
    if not text:
        raise ValueError("there is no demand to route")

    words = _words(text)
    out: List[Candidate] = []
    for agent in config.workers():          # the manager drives nothing
        score, why = _score(config, agent, words)
        if score > 0:
            out.append(Candidate(agent_id=agent.id, score=score, why=why))

    out.sort(key=lambda c: (-c.score, c.agent_id))
    result = Suggestion(candidates=out)
    if not out:
        return result
    top = out[0].score
    joint = [c for c in out if c.score == top]
    if len(joint) > 1:
        # Reported as a tie rather than resolved by sort order: a stable
        # alphabetical winner would look like a judgment and be an accident.
        result.tied = [c.agent_id for c in joint]
        return result
    result.best = out[0]
    return result


def _score(config: Config, agent, words: set):
    reasons: List[str] = []
    score = 0

    cited = _precedent(config, agent, words)
    if cited is not None:
        score += BY_PRECEDENT
        reasons.append(f"it verified {cited.id} before — \"{cited.goal}\"")

    about = [a for a in (agent.about or []) if a.lower() in words]
    if about:
        score += BY_ABOUT * len(about)
        reasons.append(f"this is what it is for ({', '.join(about)})")

    tools = [t for t in (agent.tools or []) if t.lower() in words]
    if tools:
        score += BY_TOOL * len(tools)
        reasons.append(f"the roster gives it {', '.join(tools)}")

    if agent.id.lower() in words:
        score += BY_NAME
        reasons.append(f"the demand says {agent.id!r}")

    return score, "; ".join(reasons)


def _precedent(config: Config, agent, words: set):
    """The most recent VERIFIED task of this agent that shares real words.

    Verified, not held: holding a similar task proves nothing about being able
    to finish one, and a board full of started work would otherwise read as
    experience.
    """
    best = None
    for task in (tsk.all_of(config, agent)
                 + tsk.all_of(config, agent, archived=True)):
        if task.state != tsk.VERIFIED and \
                str((task.verdict or {}).get("state") or "").upper() != "PASS":
            continue
        if _words(task.goal) & words:
            if best is None or task.updated_at > best.updated_at:
                best = task
    return best


def _words(text: str) -> set:
    return {w for w in re.findall(r"[a-z0-9.+-]{3,}", (text or "").lower())
            if w not in _STOP}
