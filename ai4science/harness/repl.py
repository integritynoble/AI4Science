"""Native-harness REPL for --mode common.

A self-contained input()-loop that builds an AgentSession from the harness
adapter factory, streams text to stdout, handles /exit and /model, and
meters usage via the ledger.  No claude_agent_sdk dependency.

This module is intentionally free of Typer / Rich so that it can be imported
and unit-tested without a TTY.

Integration point: ai4science/commands/chat.py calls run_common_repl() when
``mode == "common"`` and the harness path has been selected.  The current
chat.py still uses claude_agent_sdk for ALL modes; a follow-up wiring task
should:
  1. Remove the ClaudeAgent.is_available() gate when mode == "common".
  2. Call run_common_repl() instead of _run_chat() for common mode.
See DONE_WITH_CONCERNS note in Task 10 report.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from ai4science.harness.adapters.factory import adapter_for, make_meter
from ai4science.harness.session import AgentSession
from ai4science.llm import routing


def _pick_brand(backend: Optional[str], model: Optional[str]):
    """Return (backend, model) using the orchestration pool or explicit override.

    Priority:
      1. Both backend and model explicitly supplied → use as-is.
      2. Only backend supplied → first model in AGENT_CHAINS for that backend,
         or a sensible default.
      3. Neither → walk AGENT_CHAINS["orchestration"] and pick first reachable;
         fall back to ("anthropic", "claude-opus-4-8").
    """
    if backend and model:
        return backend, model

    if backend:
        # Find the model for this backend in the orchestration chain.
        for b, m in routing.AGENT_CHAINS.get("orchestration", []):
            if b == backend:
                return backend, m
        # Backend not in orchestration chain — use a default model.
        return backend, "claude-opus-4-8"

    # Auto-detect: first reachable backend in the orchestration chain.
    for b, m in routing.AGENT_CHAINS.get("orchestration", []):
        if routing.backend_available(b):
            return b, m

    # Nothing reachable — fall back to Anthropic / Opus 4.8.
    return "anthropic", "claude-opus-4-8"


def run_common_repl(
    workspace: Path,
    *,
    read_only: bool = False,
    auto_yes: bool = False,
    backend: Optional[str] = None,
    model: Optional[str] = None,
    on_text=None,
) -> None:
    """Run the native-harness REPL until EOF or /exit.

    Parameters
    ----------
    workspace:
        Directory the agent can read/write (subject to read_only).
    read_only:
        If True, mutating tools are blocked at the permission gate.
    auto_yes:
        If True, all tool calls are auto-approved (no prompt).
    backend:
        Override the LLM backend (e.g. "anthropic", "openai", "gemini").
        None → auto-picked from the orchestration chain.
    model:
        Override the model id.  None → picked alongside backend.
    on_text:
        Callable[[str], None] invoked for each text delta.  Defaults to
        writing to stdout without a newline.
    """
    if on_text is None:
        def on_text(t: str) -> None:
            sys.stdout.write(t)
            sys.stdout.flush()

    def _confirm(name: str, args: dict, preview: str) -> bool:
        # Per-edit confirmation (Claude-Code style). Skipped by the gate when
        # auto_yes or read_only. Without this, mutating tools are blocked in
        # default mode. NOTE: bash is confirm-gated here precisely because its
        # `cmd` is NOT path-sandboxed (see permissions.py) — the human approval
        # IS the bash sandbox in Plan 1.
        try:
            ans = input(f"\n[harness] allow {name}?  {preview}\n  [y/N] ").strip().lower()
        except EOFError:
            return False
        return ans in ("y", "yes")

    active_backend, active_model = _pick_brand(backend, model)

    def _build_session() -> AgentSession:
        return AgentSession(
            adapter=adapter_for(active_backend),
            model=active_model,
            backend=active_backend,
            workspace=workspace,
            read_only=read_only,
            auto_yes=auto_yes,
            confirm=_confirm,
            on_text=on_text,
            meter=make_meter(backend=active_backend, model=active_model),
        )

    session = _build_session()

    print(f"\n[harness] common mode  backend={active_backend}  model={active_model}", flush=True)
    print("[harness] /exit to quit  /model <backend> [model] to switch\n", flush=True)

    while True:
        try:
            line = input("> ").strip()
        except EOFError:
            print("\n[harness] EOF — exiting", flush=True)
            break
        except KeyboardInterrupt:
            print("\n[harness] Ctrl-C — type /exit to quit", flush=True)
            continue

        if not line:
            continue

        if line.startswith("/"):
            cmd, _, arg = line[1:].partition(" ")
            cmd = cmd.lower().strip()
            arg = arg.strip()

            if cmd in ("exit", "quit", "q"):
                print("[harness] bye", flush=True)
                break

            if cmd == "model":
                # /model <backend> [model-id]  or just /model (show current)
                if not arg:
                    print(f"[harness] current: backend={active_backend}  model={active_model}",
                          flush=True)
                    print("[harness] usage: /model <backend> [model-id]", flush=True)
                    continue
                parts = arg.split(None, 1)
                new_backend = parts[0]
                new_model = parts[1] if len(parts) > 1 else None
                try:
                    new_backend, new_model = _pick_brand(new_backend, new_model)
                    new_adapter = adapter_for(new_backend)
                    session.set_brand(new_adapter, new_model, new_backend)
                    session.meter = make_meter(backend=new_backend, model=new_model)
                    active_backend, active_model = new_backend, new_model
                    print(f"[harness] switched: backend={active_backend}  model={active_model}",
                          flush=True)
                except ValueError as e:
                    print(f"[harness] error: {e}", flush=True)
                continue

            if cmd in ("help", "?"):
                print("[harness] slash commands: /exit  /model <backend> [model-id]  /help",
                      flush=True)
                continue

            # Unknown slash — let it fall through to the LLM as literal text
            # rather than silently swallowing it.

        # Normal turn.
        try:
            result = session.run_turn(line)
            # Ensure there's a trailing newline after streamed output.
            if result and not result.endswith("\n"):
                print(flush=True)
        except Exception as exc:
            print(f"\n[harness] turn error: {type(exc).__name__}: {exc}", flush=True)
