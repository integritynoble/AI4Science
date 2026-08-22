"""Saying something — the generative half of the chat door. [plan v3 §7.0]

Measured 2026-08-21: `chat.py` never called a model at all. Every `llm`/`model`
match in it resolved to `selfmodel`, not inference, and a question got a fixed
line back — *"that is a question I cannot answer on this door."* On the surface
people actually type into, the worker could file work and list work and could
not answer a sentence.

So `CHAT` mode is not a relaxation of a generative path. It **creates** one
where there was none, which is why the three constraints below are structural
rather than stylistic:

  * **the self-model goes first.** A question about the agent is answered from
    `selfmodel.py`'s evidence-backed claims and never from generation. The
    self-model is *measured*; a model asked to describe itself will narrate,
    and narration is the thing the evidence discipline exists to keep out of
    self-report. That ordering lives in `chat.py`, ahead of this module.
  * **answering is not acting.** This returns a string. It has no task store,
    no session, no ledger write, and nothing it returns is parsed for an
    instruction — creation stays explicit at `/new`. The door gains the ability
    to *say* things and never the ability to *do* them.
  * **an unmeasured prerequisite is a stated unknown.** The contract asks for
    `I-DO-NOT-KNOW` rather than a confident guess, and the caller turns that
    into a plain admission. "I do not know" is a correct answer, and the
    measured self-model is what makes it available instead of guessable.

When no engine is reachable this returns `None` and the door says so. A door
that silently answers nothing is the failure that made this necessary.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from ai4science.harness.agents.sarsi.registry import Agent, Config

#: What the model returns instead of guessing.
UNKNOWN = "I-DO-NOT-KNOW"

#: Set to 0/false to keep the door mute — no model is called, and a question
#: gets the honest "no engine here" answer instead. The test suite sets it,
#: because a test that reaches the network is a test that measures the network.
_ENV_FLAG = "SARSI_CHAT_LLM"

_CONTRACT = (
    "You are {agent} — the persistent brain that holds tasks, "
    "plans and memory, and directs the transient coding sessions that do the "
    "work. You are talking to your owner on the {surface} door.\n"
    "\n"
    "Answer the question below in one short paragraph, grounded in the "
    "workspace context when it is relevant. Plain prose, no preamble.\n"
    "\n"
    "Rules:\n"
    "  - You are ANSWERING, not acting. You cannot create, start, stop, "
    "archive or edit anything in this reply, and you must not claim you have. "
    "If the owner wants work filed, tell them the exact command: /new <goal>.\n"
    f"  - If the workspace does not settle it and you do not know, reply with "
    f"exactly {UNKNOWN} and nothing else. Do not invent a fact about the "
    "owner, the machine, or work you have not been shown.\n"
    "  - Do not describe your own competence or authority here; that is "
    "measured elsewhere and reported from evidence."
)


def build_prompt(agent_id: str, question: str, *, context: str = "",
                 surface: str = "cli") -> str:
    """Exactly what the model is asked. Built here so a replay can rebuild it."""
    parts = [_CONTRACT.format(agent=agent_id, surface=surface)]
    if context:
        parts.append(context.rstrip())
    parts.append(f"THE QUESTION: {question.strip()}")
    return "\n\n".join(parts)


def engine() -> Optional[Callable[[str], str]]:
    """The cheapest reachable text engine, or None.

    Deliberately the API path only. Spawning a coding CLI to answer `why?`
    would reintroduce, on the fast path, the exact cost this mode exists to
    avoid — and an executor process is an executor whatever it is asked for.
    """
    import os
    if os.environ.get(_ENV_FLAG, "1").strip().lower() in ("0", "false", "no", "off"):
        return None
    try:
        from ai4science.llm import openai_compat as _oc
    except Exception:
        return None
    for backend in ("openai", "comparegpt"):
        try:
            if _oc.is_available(backend):
                def call(prompt: str, _b=backend) -> str:
                    text, _ = _oc.chat(_b, [{"role": "user", "content": prompt}])
                    return text
                return call
        except Exception:
            continue
    return None


def available() -> bool:
    return engine() is not None


def answer(config: Config, agent: Agent, question: str, *, context: str = "",
           surface: str = "cli",
           model: Optional[Callable[[str], str]] = None) -> Optional[str]:
    """One generative turn, or None when there is nothing to answer with.

    `None` means *no engine, or the engine declined* — both of which the caller
    must report rather than paper over. A blank string is never returned as an
    answer.
    """
    q = (question or "").strip()
    if not q:
        return None
    call = model or engine()
    if call is None:
        return None
    try:
        out = (call(build_prompt(agent.id, q, context=context,
                                 surface=surface)) or "").strip()
    except Exception:
        return None
    if not out or out.upper().startswith(UNKNOWN):
        return None
    return out
