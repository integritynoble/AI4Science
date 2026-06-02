"""Native-harness REPL for both --mode common and --mode research.

A self-contained input()-loop that builds an AgentSession from the harness
adapter factory, streams text to stdout, handles /exit and /model, and
meters usage via the ledger.  No claude_agent_sdk dependency.

This module is intentionally free of Typer / Rich so that it can be imported
and unit-tested without a TTY.

Integration: ai4science/commands/chat.py calls run_common_repl() for BOTH
modes — common uses build_common_registry; research passes
registry_builder=build_research_registry + system_prompt=RESEARCH_PROMPT
(adding the PWM registry/solution tools the moat keeps out of common mode).
Slash commands: /help /clear /model /readonly /yes /default /cost /files /exit.
Session history is persisted per turn and reseeded via --continue / --resume.
"""
from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path
from typing import List, Optional

from ai4science.harness.adapters.factory import adapter_for, make_meter
from ai4science.harness.events import Message
from ai4science.harness.session import AgentSession
from ai4science.llm import routing


def _dispatch_slash(line: str, state: dict) -> tuple[bool, str]:
    """Handle simple slash commands by mutating `state`. Returns (handled, message).

    /model, /cost, /files are handled in the loop (they need the live session).
    """
    cmd, _, _arg = line[1:].partition(" ")
    cmd = cmd.lower().strip()
    if cmd in ("exit", "quit", "q"):
        state["exit"] = True
        return True, "bye"
    if cmd in ("help", "?"):
        return True, ("slash commands: /help /clear /model <backend> [id] "
                      "/readonly /yes /default /cost /files /exit")
    if cmd == "readonly":
        state["read_only"] = True
        return True, "read-only: ON (mutating tools blocked)"
    if cmd == "yes":
        state["auto_yes"] = True
        return True, "auto-yes: ON (tools auto-approved)"
    if cmd == "default":
        state["read_only"] = False
        state["auto_yes"] = False
        return True, "default mode (per-edit confirmation)"
    if cmd == "clear":
        state["clear"] = True
        return True, "conversation cleared"
    return False, ""


def _pick_brand(backend: Optional[str], model: Optional[str]):
    """Return (backend, model) using the orchestration pool or explicit override.

    Priority:
      1. Both backend and model explicitly supplied → use as-is.
      2. Only backend supplied → first model in AGENT_CHAINS for that backend,
         or a sensible default.
      3. Neither → walk AGENT_CHAINS["orchestration"] and pick the first brand
         whose creds are present (harness_available); fall back to
         ("gemini", "gemini-3.1-pro-preview").
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
    from ai4science.harness.adapters.factory import harness_available
    for b, m in routing.AGENT_CHAINS.get("orchestration", []):
        if harness_available(b):
            return b, m

    # Nothing reachable — fall back to Gemini.
    return "gemini", "gemini-3.1-pro-preview"


RESEARCH_PROMPT = (
    "You are AI4Science in RESEARCH mode. In addition to coding tools, you can query "
    "the PWM registry: pwm_principles / pwm_principle, pwm_benchmarks / pwm_benchmark, "
    "pwm_solutions (registered SOTA solutions + scores per benchmark), pwm_overview. "
    "Use registered Principles, Specs, Benchmarks and Solutions to ground your work — "
    "consult pwm_solutions before proposing a new solution, and build on the best "
    "registered baselines. Mainnet/testnet status is shown via each artifact's chain_status."
)


def build_common_registry(*, workspace, session_factory, enable_pwm=True,
                          enable_subagents=True, mcp_clients=None):
    """Assemble core ∪ PWM ∪ sub-agent ∪ MCP tool registry.

    Parameters
    ----------
    workspace:
        Directory passed to tools that need a workspace path.
    session_factory:
        Callable used by the ``task`` sub-agent tool to spawn child sessions.
    enable_pwm:
        If True, add the four deterministic PWM tools (pwm_status, etc.).
    enable_subagents:
        If True, add the ``task`` delegation tool.
    mcp_clients:
        Optional list of stdio MCP client objects whose tools are merged in.
    """
    from ai4science.harness.tools import default_registry
    reg = default_registry()
    if enable_pwm:
        from ai4science.harness import mcp_pwm
        for t in mcp_pwm.pwm_tools():
            reg.add(t)
    if enable_subagents:
        from ai4science.harness.subagents import make_task_tool
        reg.add(make_task_tool(session_factory=session_factory, depth=0))
    for client in (mcp_clients or []):
        from ai4science.harness.mcp_client import mcp_tools
        for t in mcp_tools(client):
            reg.add(t)
    return reg


def build_research_registry(*, workspace, session_factory, enable_pwm=True,
                            enable_subagents=True, mcp_clients=None):
    """Assemble the research registry: common core + PWM data tools.

    The research tools (pwm_solutions, pwm_principles, etc.) are added on top
    of the common registry.  Common mode does NOT get these — that's the moat.
    """
    reg = build_common_registry(workspace=workspace, session_factory=session_factory,
                                enable_pwm=enable_pwm, enable_subagents=enable_subagents,
                                mcp_clients=mcp_clients)
    from ai4science.harness.research_tools import research_tools
    for t in research_tools():
        reg.add(t)
    return reg


def run_common_repl(
    workspace: Path,
    *,
    read_only: bool = False,
    auto_yes: bool = False,
    backend: Optional[str] = None,
    model: Optional[str] = None,
    on_text=None,
    resume_history: Optional[List[Message]] = None,
    session_id: Optional[str] = None,
    registry_builder=None,
    system_prompt: Optional[str] = None,
    mode_label: str = "common",
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
    resume_history:
        Prior conversation history to seed into the session (from
        persistence.load()).  None → fresh session.
    session_id:
        Stable id for this session used by persistence.save().
        None → a new random id is generated.
    registry_builder:
        Callable with the same signature as build_common_registry used to
        construct the top-level tool registry.  None → build_common_registry.
        Children sessions always use build_common_registry (no recursion).
    system_prompt:
        Optional system prompt string seeded as the leading system Message in
        history.  None → no system turn added.
    """
    from ai4science.harness import persistence

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

    # Mutable state dict — tracks modes and slash-command flags.
    # _build_session reads read_only/auto_yes from here so toggles take effect.
    state: dict = {
        "read_only": read_only,
        "auto_yes": auto_yes,
        "exit": False,
    }

    # Per-turn token accumulator (mutated by the meter wrapper).
    turn_tokens: dict = {"total": 0}

    def _make_wrapped_meter(b: str, m: str):
        """Return a meter that accumulates into turn_tokens AND calls real meter."""
        real = make_meter(backend=b, model=m)

        def _meter(u) -> None:
            turn_tokens["total"] += getattr(u, "total", 0) or 0
            real(u)

        return _meter

    def _child_session_factory(*, subagent_type, depth):
        child_reg = build_common_registry(
            workspace=workspace, session_factory=_child_session_factory,
            enable_pwm=True, enable_subagents=False)  # children: no nested task tool
        return AgentSession(
            adapter=adapter_for(active_backend),
            model=active_model,
            backend=active_backend,
            workspace=workspace,
            read_only=state["read_only"],
            auto_yes=True,
            registry=child_reg,
            on_text=on_text,
            meter=_make_wrapped_meter(active_backend, active_model),
        )

    def _build_session() -> AgentSession:
        s = AgentSession(
            adapter=adapter_for(active_backend),
            model=active_model,
            backend=active_backend,
            workspace=workspace,
            read_only=state["read_only"],
            auto_yes=state["auto_yes"],
            confirm=_confirm,
            on_text=on_text,
            meter=_make_wrapped_meter(active_backend, active_model),
            registry=(registry_builder or build_common_registry)(
                workspace=workspace,
                session_factory=_child_session_factory,
                enable_pwm=True,
                enable_subagents=True,
            ),
        )
        # Seed the system prompt on every build (initial AND /clear rebuild) so the
        # research-mode grounding survives a /clear.
        if system_prompt:
            s.history.insert(0, Message(role="system", content=system_prompt))
        return s

    _sid = session_id or secrets.token_hex(8)

    session = _build_session()

    if resume_history:
        session.history.extend(resume_history)

    print(f"\n[harness] {mode_label} mode  backend={active_backend}  model={active_model}", flush=True)
    print(f"[harness] session {_sid}  (resume later with --resume {_sid})", flush=True)
    print("[harness] /help for commands  /exit to quit\n", flush=True)

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

            # /model needs the live session — handle inline.
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
                    session.meter = _make_wrapped_meter(new_backend, new_model)
                    active_backend, active_model = new_backend, new_model
                    print(f"[harness] switched: backend={active_backend}  model={active_model}",
                          flush=True)
                except ValueError as e:
                    print(f"[harness] error: {e}", flush=True)
                continue

            # /cost needs the live session's ledger — handle inline.
            if cmd == "cost":
                try:
                    from ai4science.llm import ledger
                    summary = ledger.summary()
                    print(f"[harness] cost: {summary}", flush=True)
                except Exception as e:
                    print(f"[harness] cost unavailable: {e}", flush=True)
                continue

            # /files lists workspace files — handle inline.
            if cmd == "files":
                try:
                    entries = sorted(os.listdir(workspace))
                    if entries:
                        print("[harness] workspace files:", flush=True)
                        for name in entries:
                            print(f"  {name}", flush=True)
                    else:
                        print("[harness] workspace is empty", flush=True)
                except Exception as e:
                    print(f"[harness] files error: {e}", flush=True)
                continue

            # /agents lists available sub-agent types.
            if cmd == "agents":
                from ai4science.harness.subagents import SUBAGENTS
                print("[harness] sub-agents:", flush=True)
                for n, p in sorted(SUBAGENTS.items()):
                    print(f"  {n}: {p['description']}", flush=True)
                continue

            # /mcp describes MCP wiring status.
            if cmd == "mcp":
                print("[harness] MCP servers: none configured "
                      "(stdio MCP wiring is config-driven; see harness/mcp_client.py)",
                      flush=True)
                continue

            # All other slash commands go through the stateless dispatcher.
            handled, msg = _dispatch_slash(line, state)
            if msg:
                print(f"[harness] {msg}", flush=True)
            if state["exit"]:
                break
            if state.get("clear"):
                state["clear"] = False
                session = _build_session()
            elif handled and cmd in ("readonly", "yes", "default"):
                # Mode toggle — update the gate IN PLACE so the new modes take
                # effect without wiping conversation history (rebuilding the
                # session would reset history to []).
                session.gate.read_only = state["read_only"]
                session.gate.auto_yes = state["auto_yes"]
            if not handled:
                # Unknown slash — fall through to the LLM as literal text.
                pass
            else:
                continue

        # Normal turn.
        try:
            from ai4science.harness import mentions
            text, images = mentions.expand(line, workspace)
            turn_tokens["total"] = 0
            result = session.run_turn(text, images=images)
            # Ensure there's a trailing newline after streamed output.
            if result and not result.endswith("\n"):
                print(flush=True)
            print(f"[tokens: {turn_tokens['total']}]", flush=True)
            persistence.save(_sid, workspace, session.history)
        except Exception as exc:
            print(f"\n[harness] turn error: {type(exc).__name__}: {exc}", flush=True)
