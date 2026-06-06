"""Execute a prompt through an agent's routed LLM (design point 10).

Resolves the agent → (backend, model, reasoning) via routing, dispatches to the
backend executor, and returns the text + token usage + the Route used (so usage
can later be priced and attributed to the provider's wallet).

  anthropic → `claude -p --output-format json` (subscription)
  openai    → codex/ChatGPT subscription via the Responses API (CodexAdapter,
              pure HTTP — works on Windows); falls back to `codex exec` CLI, then
              the OpenAI api-key path
  gemini    → OpenAI-compatible Gemini endpoint (comparegpt key)
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from typing import Dict, NamedTuple, Optional

from ai4science.llm import routing


class AgentResult(NamedTuple):
    text: str
    usage: Dict[str, Optional[int]]      # {"input": .., "output": .., "total": ..}
    route: Optional[routing.Route]
    error: Optional[str]
    cost: Dict[str, float] = {}          # {"usd_official", "usd_billed", "pwm"}


def _run_anthropic(model: str, prompt: str, reasoning: str, timeout: int):
    claude = shutil.which("claude")
    if not claude:
        raise RuntimeError("`claude` CLI not on PATH")
    proc = subprocess.run(
        [claude, "-p", "--model", model, "--output-format", "json", prompt],
        capture_output=True, text=True, timeout=timeout, check=False,
        stdin=subprocess.DEVNULL,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"claude exited {proc.returncode}: {proc.stderr[-200:]}")
    d = json.loads(proc.stdout)
    u = d.get("usage", {}) or {}
    inp = ((u.get("input_tokens") or 0) + (u.get("cache_read_input_tokens") or 0)
           + (u.get("cache_creation_input_tokens") or 0))
    out = u.get("output_tokens")
    return d.get("result", ""), {
        "input": inp or None, "output": out,
        "total": (inp + (out or 0)) or None,
    }


def _oc_executor(backend: str):
    """Executor for an OpenAI-compatible backend (deepseek/qwen via Vertex,
    openai by api-key, …)."""
    def _run(model: str, prompt: str, reasoning: str, timeout: int):
        from ai4science.llm import openai_compat as oc
        text, u = oc.chat(backend, [{"role": "user", "content": prompt}],
                          model=model or None, timeout=timeout)
        return text, {"input": u.get("prompt_tokens"),
                      "output": u.get("completion_tokens"),
                      "total": u.get("total_tokens")}
    return _run


def _run_codex_responses(model: str, prompt: str, reasoning: str, timeout: int):
    """One-shot via the codex/ChatGPT subscription Responses API (CodexAdapter).

    Pure HTTP, so it works on every OS — unlike `codex exec`, whose npm shim
    fails to launch on Windows (WinError 193). This is the same path codex MODE
    uses; preferred whenever a codex subscription login exists.
    """
    from ai4science.harness.adapters.codex import CodexAdapter
    from ai4science.harness.events import Message, TextDelta, Usage
    parts = []
    usage = {"input": None, "output": None, "total": None}
    for ev in CodexAdapter().stream([Message(role="user", content=prompt)], [],
                                    model=model, reasoning=reasoning or "medium"):
        if isinstance(ev, TextDelta):
            parts.append(ev.text)
        elif isinstance(ev, Usage):
            usage = {"input": ev.input, "output": ev.output, "total": ev.total}
    return "".join(parts).strip(), usage


def _run_codex_exec(codex: str, model: str, prompt: str, reasoning: str, timeout: int):
    """One-shot via the `codex exec` CLI subprocess (POSIX; fails on Windows)."""
    fd, last = tempfile.mkstemp(suffix=".txt"); os.close(fd)
    try:
        proc = subprocess.run(
            [codex, "exec", "-m", model,
             "-c", f'model_reasoning_effort="{reasoning}"',
             "--skip-git-repo-check", "--output-last-message", last, prompt],
            capture_output=True, text=True, timeout=timeout, check=False,
            stdin=subprocess.DEVNULL,
        )
        text = ""
        try:
            text = open(last, encoding="utf-8").read().strip()
        except OSError:
            pass
        if not text and proc.returncode != 0:
            raise RuntimeError(f"codex exited {proc.returncode}: {proc.stdout[-200:]}")
        total = None
        m = re.search(r"tokens used[\s:]+([\d,]+)", proc.stdout, re.I)
        if m:
            total = int(m.group(1).replace(",", ""))
        return text, {"input": None, "output": None, "total": total}
    finally:
        try:
            os.unlink(last)
        except OSError:
            pass


def _run_openai(model: str, prompt: str, reasoning: str, timeout: int):
    # 1. Codex subscription via the Responses API (CodexAdapter) — pure HTTP,
    #    works on Windows. Same path as codex MODE; preferred when logged in.
    from ai4science.harness.adapters import codex_creds
    if codex_creds.codex_available():
        return _run_codex_responses(model, prompt, reasoning, timeout)
    # 2. The `codex exec` CLI subprocess (POSIX hosts without subscription creds
    #    resolvable by codex_creds but with the CLI logged in).
    codex = shutil.which("codex")
    if codex:
        return _run_codex_exec(codex, model, prompt, reasoning, timeout)
    # 3. OpenAI api-key path if a key is configured (point 5: api-key execution).
    from ai4science.llm import openai_compat as oc
    if oc.is_available("openai"):
        return _oc_executor("openai")(model, prompt, reasoning, timeout)
    raise RuntimeError("no codex subscription, no `codex` CLI, and no OPENAI_API_KEY "
                       "(run `codex login` or `ai4science login`)")


def _run_gemini(model: str, prompt: str, reasoning: str, timeout: int):
    from ai4science.llm import gemini
    text, u = gemini.chat([{"role": "user", "content": prompt}], model=model, timeout=timeout)
    return text, {
        "input": u.get("prompt_tokens"), "output": u.get("completion_tokens"),
        "total": u.get("total_tokens"),
    }


_EXECUTORS = {
    "anthropic": _run_anthropic,
    "openai": _run_openai,
    "gemini": _run_gemini,
    "deepseek": _oc_executor("deepseek"),
    "qwen": _oc_executor("qwen"),
}


def run_agent(agent: str, prompt: str, timeout: int = 300) -> AgentResult:
    """Run a prompt through the agent's routed LLM. Never raises — errors are
    returned in AgentResult.error so callers (and workflows) can fall back."""
    route = routing.resolve(agent)
    if route is None:
        return AgentResult("", {}, None, f"no reachable LLM for agent {agent!r}")
    fn = _EXECUTORS.get(route.backend)
    if fn is None:
        return AgentResult("", {}, route, f"no executor for backend {route.backend!r}")
    try:
        text, usage = fn(route.model, prompt, route.reasoning, timeout)
        from ai4science.llm import pricing
        cost = pricing.price_call(route.model, usage, route.price_multiplier)
        return AgentResult(text, usage, route, None, cost)
    except Exception as e:
        return AgentResult("", {}, route, f"{type(e).__name__}: {e}")
