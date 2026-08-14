"""What answers a prompt: ai4science's own LLM layer, and nothing else.

The point of the adapter is that this file contains no reference to Claude, to
Anthropic, or to any credential belonging to a coding agent. It resolves a
backend the way the rest of ai4science does — `llm.openai_compat` for every
OpenAI-compatible endpoint — and asks it for a completion.

That covers the case the requirement is really about. `resolve_base()` honours
`AI4SCIENCE_<BACKEND>_API_BASE`, so pointing the `openai` backend at a local
server makes the whole path credential-free:

    AI4SCIENCE_OPENAI_API_BASE=http://localhost:11434/v1
    AI4SCIENCE_OPENAI_MODEL=qwen3.6:27b
    OPENAI_API_KEY=<any non-empty string; a local server ignores it>

Measured on the GPU box, 2026-08-14: `is_available` True, a round trip in 12.4s
against ollama's qwen3.6:27b, no network egress and no cloud account. That is
the executor "needing only ai4science" in the literal sense the plan asks for,
rather than in the sense of a config field that says so.

**A model is not chosen here.** `openai_compat.default_model` reads
`AI4SCIENCE_<BACKEND>_MODEL`, and passing an explicit model from a routing chain
would override the operator's setting with a cloud model id that a local server
does not have — `gpt-5.5` against ollama is a 404, and it would look like the
adapter was broken rather than mis-pointed. The operator names the model; this
file does not second-guess it.
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional, Sequence, Tuple

#: Tried in order when no backend is named. Only OpenAI-compatible backends are
#: listed: this is the first cut, and it is better to say so than to route to a
#: backend whose turn shape has not been exercised here.
_PREFERRED = ("openai", "qwen", "deepseek")


class NoBackend(RuntimeError):
    """No LLM backend is reachable, and the message says how to give it one."""


def resolve_backend() -> str:
    """Which backend serves this session.

    `AI4SCIENCE_ACP_BACKEND` wins when set, so an operator can pin one rather
    than depend on discovery order.
    """
    from ai4science.llm import openai_compat as _oc

    named = (os.environ.get("AI4SCIENCE_ACP_BACKEND") or "").strip()
    if named:
        if not _oc.is_available(named):
            raise NoBackend(
                "AI4SCIENCE_ACP_BACKEND=%r, but that backend is not reachable: "
                "it needs both a base URL and a key. Set "
                "AI4SCIENCE_%s_API_BASE and a key env for it."
                % (named, named.upper()))
        return named
    for backend in _PREFERRED:
        if _oc.is_available(backend):
            return backend
    raise NoBackend(
        "no OpenAI-compatible LLM backend is reachable on this machine, so "
        "this adapter has nothing to run a turn on. The cheapest fix needs no "
        "account: point it at a local server, e.g.\n"
        "  AI4SCIENCE_OPENAI_API_BASE=http://localhost:11434/v1\n"
        "  AI4SCIENCE_OPENAI_MODEL=<a model that server has>\n"
        "  OPENAI_API_KEY=local\n"
        "Tried: %s" % ", ".join(_PREFERRED))


def describe() -> Dict[str, str]:
    """Backend and model, for the session banner and for the record.

    Never raises: a session that cannot run a turn should still start and say
    why, rather than failing the handshake with a JSON-RPC error the operator
    has to go and decode.
    """
    from ai4science.llm import openai_compat as _oc

    try:
        backend = resolve_backend()
    except NoBackend as e:
        return {"backend": "", "model": "", "base": "", "error": str(e)}
    return {"backend": backend, "model": _oc.default_model(backend),
            "base": _oc.resolve_base(backend), "error": ""}


def complete(messages: Sequence[Dict[str, str]],
             *, timeout: int = 600) -> Tuple[str, Dict]:
    """One turn. Returns (text, usage)."""
    from ai4science.llm import openai_compat as _oc

    backend = resolve_backend()
    return _oc.chat(backend, list(messages), model=None, timeout=timeout)


def system_prompt(cwd: Optional[str] = None) -> str:
    """The session's opening instruction.

    Short on purpose. A long persona written here would be a second, competing
    source of truth against the agent's charter, which is the brain's to set.
    """
    lines = [
        "You are ai4science, a scientific research assistant running as an "
        "executor under a planning agent.",
        "Answer the task you are given. Be concrete, say what you did not "
        "check, and never report a result you did not obtain.",
    ]
    if cwd:
        lines.append("The working directory for this session is %s." % cwd)
    return " ".join(lines)
