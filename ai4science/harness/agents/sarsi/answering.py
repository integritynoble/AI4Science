"""Answering the session's questions — instead of waking the owner for each one.

Claude Code asks things while it works: *which directory*, *tests first?*,
*which of these two approaches*. Before this, every one stopped the loop and
waited for a person, which makes an unattended agent a thing that pages you
every few minutes.

An agent may answer, and only from **what it already holds**: the goal, the
plan and its criteria, the directive's scope, and what the owner has actually
said. That is the whole rule, and the rest follows from it.

| It may not answer | Because |
|---|---|
| anything the workspace does not settle | guessing *for* the owner and guessing *as* the owner are the same act |
| an **owner fact** — salary, start date, a reference | it asks rather than invents; a question is not a licence to invent |
| a request for a **secret** | that is the vault's question, asked its way, with its record |
| anything that would **widen what the session may do** | authority is decided at the gate, and a clarification that grants permission is not a clarification |

And every answer is **recorded with the question that prompted it**. Answering
on someone's behalf is delegation, and delegation nobody can see is
indistinguishable from an agent doing as it pleases.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Optional

from ai4science.harness.agents.sarsi import ledger, ownerlog, task as tsk
from ai4science.harness.agents.sarsi.registry import Agent, Config

#: The token the model must return when the workspace does not settle it.
REFUSAL = "ASK-THE-OWNER"

_QUESTION = re.compile(r"([^\n?]{8,200}\?)")
#: An option menu is the gate's business, not this node's.
_MENU = re.compile(r"^\s*❯?\s*\d\.\s+\S", re.M)

#: Questions this node refuses outright, whatever a model would say.
_SECRET_WORDS = re.compile(r"\b(password|api[- ]?key|token|secret|credential|"
                           r"passphrase)\b", re.I)
_AUTHORITY_WORDS = re.compile(r"\b(sudo|root|disable|bypass|force|--no-verify|"
                              r"skip the check|chmod 777)\b", re.I)

_CONTRACT = (
    "You are answering a question that another agent's coding session has asked "
    "mid-task.\n"
    "Answer ONLY if the answer is settled by the material below — the goal, the "
    "plan's criteria, the scope, or what the owner said.\n"
    f"If it is not settled there, reply with exactly {REFUSAL} and nothing "
    "else. Do not guess, do not choose on the owner's behalf, and do not "
    "invent a fact about them.\n"
    "Otherwise reply with the answer alone, in one or two sentences."
)


@dataclass(frozen=True)
class Answered:
    answer: Optional[str] = None
    escalate: str = ""


def question_on(screen: str) -> Optional[str]:
    """The question a session is asking, if it is asking one.

    An option menu is **not** one: that is a permission gate, and answering it
    here would route around the single place authority is decided.
    """
    text = screen or ""
    if _MENU.search(text):
        return None
    hits = _QUESTION.findall(text)
    return hits[-1].strip() if hits else None


def answer(config: Config, agent: Agent, task: tsk.Task, *, question: str,
           model: Callable[[str], str], now=None) -> Answered:
    from ai4science.harness.agents.sarsi import specs

    q = (question or "").strip()

    if _SECRET_WORDS.search(q):
        return _escalate(config, agent, task, q,
                         "this asks for a secret — the vault answers that, its "
                         "own way, with its own record")
    if _AUTHORITY_WORDS.search(q):
        return _escalate(config, agent, task, q,
                         "this would widen what the session may do; authority is "
                         "decided at the gate, not in an answer")
    if _asks_an_owner_fact(q, specs.OWNER_FACTS):
        return _escalate(config, agent, task, q,
                         "this is an owner fact, not something to work out — it "
                         "is asked, never invented")

    prompt = build_prompt(config, agent, task, question=q)
    try:
        reply = (model(prompt) or "").strip()
    except Exception as e:
        return _escalate(config, agent, task, q, f"could not be answered: {e}")

    if not reply or reply.upper().startswith(REFUSAL):
        return _escalate(config, agent, task, q,
                         "nothing in the plan, the scope or what you have said "
                         "settles this")

    ledger.append(config, "reports",
                  {"agent": agent.id, "task": task.id, "state": "answered-question",
                   "evidence": [f"Q: {q}", f"A: {reply[:300]}"]})
    return Answered(answer=reply)


def build_prompt(config: Config, agent: Agent, task: tsk.Task, *,
                 question: str) -> str:
    lines = [_CONTRACT, "", f"THE QUESTION: {question}", "",
             f"GOAL: {task.goal}"]
    if task.criteria:
        lines.append("THE PLAN'S CRITERIA:")
        lines += [f"  - {c}" for c in task.criteria]
    scope = (task.directive or {}).get("scope") or []
    if scope:
        lines.append("SCOPE — what this task may touch:")
        lines += [f"  - {s}" for s in scope]
    said = ownerlog.said(config, agent, limit=8)
    if said:
        lines.append("WHAT THE OWNER SAID (authoritative for what they want):")
        lines += [f"  - {e.get('text', '')}" for e in said]
    return "\n".join(lines)


def _asks_an_owner_fact(question: str, owner_facts) -> bool:
    low = question.lower()
    words = {f.replace("_", " ") for f in owner_facts}
    words |= {"salary", "start date", "reference", "notice period", "visa"}
    return any(w in low for w in words)


def _escalate(config: Config, agent: Agent, task: tsk.Task, question: str,
              why: str) -> Answered:
    text = f"{agent.id} needs you: {why}\n  the session asked: {question}"
    ledger.append(config, "reports",
                  {"agent": agent.id, "task": task.id, "state": "question",
                   "evidence": [f"Q: {question}", f"escalated: {why}"]})
    return Answered(answer=None, escalate=text)
