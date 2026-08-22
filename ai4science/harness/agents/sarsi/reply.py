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

from dataclasses import dataclass
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


#: Tried in order. A locally served model first — it is free and on this host,
#: and the fast path is the one place that matters most.
BACKENDS = ("qwen_local", "deepseek", "qwen", "openai")


def engine() -> Optional[Callable[[str], str]]:
    """The cheapest reachable text engine, or None.

    Deliberately the API path only. Spawning a coding CLI to answer `why?`
    would reintroduce, on the fast path, the exact cost this mode exists to
    avoid — and an executor process is an executor whatever it is asked for.

    Every *configured* backend is tried, because `is_available()` checks that a
    key and a base URL exist, not that either works. Measured on this host: it
    returned True for a placeholder key (`sk-unused…bridge`) and the call came
    back `HTTP 401`. So configuration is a candidate list, not an answer, and
    when the whole list fails the caller is told what each one said.
    """
    import os
    if os.environ.get(_ENV_FLAG, "1").strip().lower() in ("0", "false", "no", "off"):
        return None
    try:
        from ai4science.llm import openai_compat as _oc
    except Exception:
        return None
    live = []
    for backend in BACKENDS:
        try:
            if _oc.is_available(backend):
                live.append(backend)
        except Exception:
            continue
    if not live:
        return None

    def call(prompt: str) -> str:
        failures = []
        for backend in live:
            try:
                text, _ = _oc.chat(backend, [{"role": "user", "content": prompt}])
                if text:
                    return text
                failures.append(f"{backend}: returned nothing")
            except Exception as e:
                failures.append(f"{backend}: {type(e).__name__}: {str(e)[:120]}")
        raise RuntimeError("; ".join(failures))

    return call


def available() -> bool:
    return engine() is not None


@dataclass(frozen=True)
class Said:
    """What came back, or precisely why nothing did."""
    text: str = ""
    why: str = ""          #: set when `text` is empty — the reason, not a shrug

    def __bool__(self) -> bool:
        return bool(self.text)


def answer(config: Config, agent: Agent, question: str, *, context: str = "",
           surface: str = "cli",
           model: Optional[Callable[[str], str]] = None) -> Said:
    """One generative turn, or the reason there was none.

    The reason is returned rather than collapsed, because the three cases are
    different facts and the owner needs to be told which one happened:

      * **no engine configured** — nothing to ask;
      * **the engine failed** — it was asked and the call did not work. Live,
        `is_available()` returned True for a placeholder key and the call came
        back `HTTP 401`; the door reported "no engine is reachable", which was
        the wrong sentence about a real, fixable problem;
      * **the model declined** — it was asked, it answered, and the answer was
        "I do not know". That is a correct outcome and reads as one.
    """
    q = (question or "").strip()
    if not q:
        return Said(why="there was no question in that")
    call = model or engine()
    if call is None:
        return Said(why="no model engine is configured here")
    try:
        out = (call(build_prompt(agent.id, q, context=context,
                                 surface=surface)) or "").strip()
    except Exception as e:
        return Said(why=f"the model engine here did not answer: "
                        f"{type(e).__name__}: {str(e)[:160]}")
    if out.upper().startswith(UNKNOWN):
        return Said(why="I do not know — nothing I hold settles that")
    if not out:
        return Said(why="the model engine returned nothing")
    return Said(text=out)
