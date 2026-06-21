"""Native-harness REPL for both --mode common and --mode research.

A self-contained input()-loop that builds an AgentSession from the harness
adapter factory, streams text to stdout, handles /exit and /model, and
meters usage via the ledger.  No claude_agent_sdk dependency.

This module is intentionally free of Typer / Rich so that it can be imported
and unit-tested without a TTY.

Integration: ai4science/commands/chat.py resolves --mode against the agent
registry and calls run_common_repl() with mode_label + the spec's system_prompt
(as a fallback). The active AgentSpec — resolved inside run_common_repl from
mode_label — drives the tool registry and grounding prompt for the session.
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
from ai4science.harness.agents import registry as agent_registry
from ai4science.harness.agents.context import BuildContext
from ai4science.harness.agents.registry import build_registry_for
from ai4science.harness.events import Message
from ai4science.harness.session import AgentSession
from ai4science.harness.pwm_gate import PwmGate, BASE_TOOLS
from ai4science.llm import routing, pricing


def _shortcwd(p) -> str:
    import os
    try:
        s = str(p); h = os.path.expanduser("~")
        return ("~" + s[len(h):]) if s.startswith(h) else s
    except Exception:
        return str(p)


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
                      "/agent [name|specific <q>] /login /whoami /feedback <text> "
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


def make_confirm(read_input, mode_label: str):
    """Per-edit confirmation with `a(lways)` (Claude Code / SDK-path parity).

    `read_input(prompt, mode)` supplies the answer (tui.read_input in the
    REPL; injectable for tests). Answering `a` allows THIS tool name for the
    rest of the session. NOTE: bash is confirm-gated because its `cmd` is NOT
    path-sandboxed (see permissions.py) — the human approval IS the bash
    sandbox in Plan 1 (read-only commands are auto-allowed by the gate and
    never reach here).
    """
    always: set = set()

    def _confirm(name: str, args: dict, preview: str) -> bool:
        if name in always:
            return True
        from ai4science.harness import tui
        options = ["Yes",
                   f"Yes, and don't ask again for {name} this session",
                   "No, and tell the agent what to do differently (esc)"]
        question = f"⏺ {name}\n  {preview}\n\nDo you want to proceed?"
        try:
            idx = tui.ask_choice(question, options,
                                 read_input=read_input, mode=mode_label or "chat")
        except EOFError:
            return False
        if idx == 1:                 # Yes, and don't ask again
            always.add(name)
            return True
        return idx == 0              # Yes (else No)

    return _confirm


def _clean_turn_error(exc) -> str:
    """One-line, human-readable turn error (no traceback)."""
    s = str(exc).strip()
    name = type(exc).__name__
    return f"{name}: {s}" if s else name


def _turn_cost_for(backend: str, model: str, usage):
    """(pwm, wallet) for one Usage — the same pricing path make_meter uses."""
    try:
        _src, _pid, wallet, mult = routing._select_source(backend)
        u = {"input": usage.input, "output": usage.output, "total": usage.total}
        cost = pricing.price_call(model, u, price_multiplier=mult)
        return float(cost.get("pwm") or 0.0), wallet
    except Exception:
        return 0.0, None


def _next_available_brand(current: Optional[str]):
    """First orchestration brand whose creds resolve and that isn't `current`.
    Returns (backend, model) or None. Used to self-heal when an auto-detected
    brand fails a turn (e.g. the default openai key 401s → fall back to gemini)."""
    from ai4science.harness.adapters.factory import harness_available
    for b, m in routing.AGENT_CHAINS.get("orchestration", []):
        if b != current and harness_available(b):
            return b, m
    return None


# The `/model` menu is AGENT-scoped, as (label, backend, model_id) entries:
#  • Vendor agents are locked to one provider — Claude → Anthropic, Codex → OpenAI
#    (keyed by the spec's default_backend).
#  • Every other agent gets the cross-provider flagship menu and can switch freely.
# Selecting an entry switches BOTH backend and model.
_LOCKED_MENU = {
    "anthropic": [("Opus 4.8", "anthropic", "claude-opus-4-8"),
                  ("Sonnet 4.6", "anthropic", "claude-sonnet-4-6"),
                  ("Haiku 4.5", "anthropic", "claude-haiku-4-5")],
    "openai":    [("ChatGPT 5.5", "openai", "gpt-5.5"),
                  ("ChatGPT 5.5 Codex", "openai", "gpt-5.5-codex")],
}
_FLAGSHIP_MENU = [("Opus 4.8", "anthropic", "claude-opus-4-8"),
                  ("ChatGPT 5.5", "openai", "gpt-5.5"),
                  ("Gemini 3.1 Pro", "gemini", "gemini-3.1-pro-preview")]

# Typed shortcuts (`/model haiku`, `/model gpt`, …) → model id, resolved within
# whatever menu the active agent allows.
_TYPED_ALIASES = {
    "opus": "claude-opus-4-8", "opus-4-8": "claude-opus-4-8", "fable": "claude-opus-4-8",
    "sonnet": "claude-sonnet-4-6", "haiku": "claude-haiku-4-5",
    "gpt": "gpt-5.5", "chatgpt": "gpt-5.5", "gpt-5.5": "gpt-5.5", "gpt5.5": "gpt-5.5",
    "codex": "gpt-5.5-codex",
    "gemini": "gemini-3.1-pro-preview", "pro": "gemini-3.1-pro-preview",
}


def _agent_model_menu(spec):
    """(label, backend, model) options the given agent may use."""
    lock = getattr(spec, "default_backend", None)
    if lock:
        return _LOCKED_MENU.get(lock, _FLAGSHIP_MENU)
    return _FLAGSHIP_MENU


def _resolve_in_menu(menu, tok: str):
    """Resolve a typed token (alias / id / label) to a (backend, model) IN this
    agent's menu, or None if it isn't allowed for this agent."""
    tl = (tok or "").strip().lower()
    want = _TYPED_ALIASES.get(tl, tok)
    for lbl, be, mid in menu:
        if mid == want or mid.lower() == tl or lbl.lower() == tl:
            return (be, mid)
    return None


def _infer_backend(model: str) -> Optional[str]:
    """Guess the backend from a model id. Exact AGENT_CHAINS match first, then a
    substring heuristic — so `--model gemini-3.1-pro-preview` selects gemini."""
    for chain in routing.AGENT_CHAINS.values():
        for b, m in chain:
            if m == model:
                return b
    ml = model.lower()
    for needle, b in (("gemini", "gemini"), ("gpt", "openai"), ("claude", "anthropic"),
                      ("deepseek", "deepseek"), ("qwen", "qwen")):
        if needle in ml:
            return b
    return None


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

    if model:
        # Only a model id given — infer its backend so `--model gemini-…` works.
        inferred = _infer_backend(model)
        if inferred:
            return inferred, model

    # Auto-detect: first reachable backend in the orchestration chain.
    from ai4science.harness.adapters.factory import harness_available
    for b, m in routing.AGENT_CHAINS.get("orchestration", []):
        if harness_available(b):
            return b, m

    # Nothing reachable — fall back to Gemini.
    return "gemini", "gemini-3.1-pro-preview"


# NOTE: legacy/unused at runtime — research mode's LIVE system prompt is
# AgentSpec.system_prompt in ai4science/harness/agents/specs/research.py (resolved
# via agent_registry.get("research")). Edit THAT to change research behavior.
# Kept only because a test still imports this symbol.
RESEARCH_PROMPT = (
    "You are AI4Science in RESEARCH mode. In addition to coding tools, you can query "
    "the PWM registry: pwm_principles / pwm_principle, pwm_benchmarks / pwm_benchmark, "
    "pwm_solutions (registered SOTA solutions + scores per benchmark), pwm_overview. "
    "Use registered Principles, Specs, Benchmarks and Solutions to ground your work — "
    "consult pwm_solutions before proposing a new solution, and build on the best "
    "registered baselines. Mainnet/testnet status is shown via each artifact's chain_status."
)


def _make_build_context(*, workspace, brand_provider, session_factory=None,
                        read_only=False, auto_yes=False, mcp_clients=None) -> BuildContext:
    return BuildContext(workspace=workspace, brand_provider=brand_provider,
                        session_factory=session_factory, read_only=read_only,
                        auto_yes=auto_yes, mcp_clients=mcp_clients)


def _registry_for_spec(spec, *, is_subagent, ctx):
    return build_registry_for(spec, is_subagent=is_subagent, ctx=ctx)


def _format_mode_menu() -> str:
    from ai4science.harness import tui as _tui
    lines = ["[agents]"]
    for s in agent_registry.core_agents():
        lines.append(f"  {_tui._display_mode(s.name):<22} {s.description}")
    n = len(agent_registry.specific_agents())
    lines.append(f"  {'specific':<22} ({n}) domain agents — /agent specific <query> to search")
    lines.append("  switch with: /agent <name> (e.g. /agent Claude, /agent \"Computational Imaging\")")
    return "\n".join(lines)


def _format_specific_list(query: str) -> str:
    hits = agent_registry.search(query)
    if not hits:
        return f"[agents] no specific agent matches {query!r}"
    return "\n".join([f"  {s.name:<24} {s.title}" for s in hits])


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
    system_prompt: Optional[str] = None,
    mode_label: str = "unified-LLM",
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
    system_prompt:
        Optional system prompt string seeded as the leading system Message in
        history.  None → no system turn added.
    """
    from ai4science.harness import persistence

    # Shining-star spinner (Claude Code feel): pulses while the model is
    # thinking; the first streamed token clears it. Holder is per-turn.
    from ai4science.harness.spinner import Spinner
    _spin = {"s": None}

    def _stop_spin() -> None:
        if _spin["s"] is not None:
            _spin["s"].stop()
            _spin["s"] = None

    # Live output-token estimate for the box's "↓ N tokens" status.
    _live_tok = {"n": 0}

    def _tick_tokens(t: str) -> None:
        _live_tok["n"] += max(1, len(t) // 4)   # ~4 chars/token
        from ai4science.harness import tui as _tui
        _tui.set_tokens(_live_tok["n"])

    if on_text is None:
        def on_text(t: str) -> None:
            _stop_spin()                  # first token → clear the spinner
            _tick_tokens(t)
            sys.stdout.write(t)
            sys.stdout.flush()
    else:
        _user_on_text = on_text
        def on_text(t: str) -> None:      # noqa: F811 — wrap caller's on_text
            _stop_spin()
            _tick_tokens(t)
            _user_on_text(t)

    # Per-edit confirmation with a(lways) (Claude-Code style). Skipped by the
    # gate when auto_yes or read_only; read-only bash is auto-allowed earlier.
    def _tui_read(prompt: str, mode: str) -> str:
        from ai4science.harness import tui
        return tui.read_input(prompt, mode)

    _confirm = make_confirm(_tui_read, mode_label)

    active_spec = agent_registry.get(mode_label) or agent_registry.get("unified-LLM")
    # A mode may prefer a backend (e.g. 'codex' → openai, 'claude-code' →
    # anthropic). Honor it only when the user pinned nothing, so an explicit
    # --backend/--model always wins.
    eff_backend = backend
    if eff_backend is None and model is None and active_spec.default_backend:
        eff_backend = active_spec.default_backend
    active_backend, active_model = _pick_brand(eff_backend, model)
    # The brand was truly auto-detected (self-heal allowed) only when nothing —
    # not even a mode default — pinned it. A mode that requires its backend
    # (codex) must not silently self-heal to a different brand.
    brand_autodetected = backend is None and model is None and eff_backend is None
    fell_back = {"v": False}

    # Mutable state dict — tracks modes and slash-command flags.
    # _build_session reads read_only/auto_yes from here so toggles take effect.
    state: dict = {
        "read_only": read_only,
        "auto_yes": auto_yes,
        "exit": False,
    }

    # Per-turn token accumulator (mutated by the meter wrapper).
    turn_tokens: dict = {"total": 0}
    turn_cost = {"pwm": 0.0, "wallet": None}
    turn_calls = {"n": 0}

    # Collapsed Claude Code-style tool lines (`⏺ bash(ls …)` / dim `⎿ …`).
    from ai4science.harness import toolfmt

    def _show_tool_start(name: str, args: dict) -> None:
        _stop_spin()
        turn_calls["n"] += 1
        from ai4science.harness import tui as _tui
        _tui.set_activity(f"running {toolfmt._DISPLAY_NAME.get(name, name)}")
        print(f"\n{toolfmt.fmt_tool_start(name, args)}", flush=True)

    def _show_tool_end(name: str, result: str) -> None:
        from ai4science.harness import tui as _tui
        _tui.set_activity("thinking")
        line = toolfmt.fmt_tool_result(result)
        if line:
            print(line, flush=True)
    gate = PwmGate.from_env()
    turn_counter = {"n": 0}
    # Agent-mining: domain tools invoked this turn (their authors earn from the
    # agent pool). Base Claude-Code tools are platform infra, not contributions.
    turn_tools: set = set()

    def _make_wrapped_meter(b: str, m: str):
        """Return a meter that accumulates into turn_tokens AND calls real meter."""
        real = make_meter(backend=b, model=m)

        def _meter(u) -> None:
            turn_tokens["total"] += getattr(u, "total", 0) or 0
            pwm, wallet = _turn_cost_for(b, m, u)
            turn_cost["pwm"] += pwm
            if wallet:
                turn_cost["wallet"] = wallet
            real(u)

        return _meter

    def _child_session_factory(*, spec, ctx):
        child = AgentSession(
            adapter=adapter_for(active_backend),
            model=active_model,
            backend=active_backend,
            workspace=workspace,
            read_only=state["read_only"],
            auto_yes=True,                      # sub-agents auto-approve
            confirm=_confirm,
            on_text=on_text,
            meter=_make_wrapped_meter(active_backend, active_model),
            on_tool=lambda name: turn_tools.add(name),
            on_tool_start=_show_tool_start, on_tool_end=_show_tool_end,
            registry=build_registry_for(spec, is_subagent=True, ctx=ctx),
        )
        if spec.system_prompt:
            child.history.insert(0, Message(role="system", content=spec.system_prompt))
        return child

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
            on_tool=lambda name: turn_tools.add(name),
            on_tool_start=_show_tool_start, on_tool_end=_show_tool_end,
            registry=_registry_for_spec(
                active_spec, is_subagent=False,
                ctx=_make_build_context(
                    workspace=workspace,
                    brand_provider=lambda: (active_backend, active_model),
                    session_factory=_child_session_factory,
                    read_only=state["read_only"], auto_yes=state["auto_yes"],
                )),
        )
        # Seed the system prompt on every build (initial AND /clear rebuild) so the
        # mode grounding survives a /clear and /mode switches re-ground.
        seed_prompt = active_spec.system_prompt or system_prompt
        if seed_prompt:
            s.history.insert(0, Message(role="system", content=seed_prompt))
        return s

    _sid = session_id or secrets.token_hex(8)

    session = _build_session()

    if resume_history:
        session.history.extend(resume_history)

    from ai4science.harness.tui import _display_mode
    from ai4science import __version__ as _ver
    print(f"\n[harness] {_display_mode(mode_label)} mode  backend={active_backend}  "
          f"model={active_model}  v{_ver}", flush=True)
    print(f"[harness] session {_sid}  (resume later with --resume {_sid})", flush=True)
    print("[harness] /help for commands  /exit to quit\n", flush=True)
    if gate.enabled:
        print("[harness] PWM gate ON — each turn is charged to the provider in PWM", flush=True)

    from ai4science.harness import lineedit
    lineedit.enable(mode_label or "chat")     # ↑/↓ history, ←/→ cursor
    _interrupts = {"n": 0}
    while True:
        try:
            from ai4science.harness import tui
            _st = f"{active_model} · {_shortcwd(workspace)}"
            # use the CURRENT spec name so the info-line label tracks /mode switches
            line = tui.read_input("> ", active_spec.name or mode_label or "chat",
                                  _st).strip()
            _interrupts["n"] = 0
        except EOFError:
            print("\n[harness] EOF — exiting", flush=True)
            break
        except KeyboardInterrupt:
            _interrupts["n"] += 1
            if _interrupts["n"] >= 2:
                print("\n[harness] exiting", flush=True)
                break
            print("\n[harness] Ctrl-C — press again to exit (or type /exit)",
                  flush=True)
            continue

        if not line:
            continue

        # Accept bare exit words too (not only the slash form) — a user who
        # types `exit`/`quit`/`q` should not be sent to the LLM or trapped.
        if line.lower() in ("exit", "quit", "q", ":q", ":q!"):
            break

        if line.startswith("/"):
            cmd, _, arg = line[1:].partition(" ")
            cmd = cmd.lower().strip()
            arg = arg.strip()

            # /feedback — early-user feedback on the ACTIVE agent (agent-mining).
            if cmd == "feedback":
                if not arg:
                    print(f"[harness] usage: /feedback <your experience + how to improve "
                          f"{active_spec.name}>", flush=True)
                    continue
                # Zero-login: post_feedback auto-provisions a local wallet when
                # not logged in, so feedback always submits and can earn PWM.
                ok, status = gate.post_feedback(agent_name=active_spec.name, text=arg)
                note = (status if ok and str(status).startswith("accepted")
                        else status if any(str(status).startswith(k) for k in
                                           ("use_agent_first", "balance_not_low", "need_more_usage"))
                        else "program full (first-N guard)" if status == "program_full"
                        else f"failed ({status})")
                print(f"[pwm] feedback for {active_spec.name}: {note}", flush=True)
                continue

            # /login — sign in to physicsworldmodel.org mid-session (device flow)
            # so a logged-out or expired session can earn/spend PWM WITHOUT
            # restarting, then refresh the gate so the next turn uses the token.
            if cmd == "login":
                try:
                    from ai4science.commands.login import _login_pwm
                    _login_pwm(arg or None)        # arg = optional base/mirror url
                except (SystemExit, Exception):
                    pass                           # _login_pwm prints its own reason
                try:
                    fresh = PwmGate.from_env()   # PwmGate imported at module level
                    gate.token, gate.base, gate.enabled = (
                        fresh.token, fresh.base, fresh.enabled)
                except Exception:
                    pass
                continue

            # /whoami — show the current login / how the agent is powered.
            if cmd == "whoami":
                import os as _os
                try:
                    from ai4science import pwm_account
                    acct = pwm_account.load() or {}
                except Exception:
                    acct = {}
                tok = (_os.environ.get("PWM_TOKEN") or _os.environ.get("PWM_ONBOARD_TOKEN")
                       or acct.get("token"))
                if tok:
                    who = (acct.get("email")
                           or (f"user #{acct.get('user_id')}" if acct.get("user_id") else "signed in"))
                    print(f"[pwm] signed in: {who}  ({acct.get('base') or 'physicsworldmodel.org'})",
                          flush=True)
                else:
                    print("[pwm] not signed in — /login to sign in (or set PWM_TOKEN).",
                          flush=True)
                continue

            # /model needs the live session — handle inline. The menu is scoped to
            # the active agent: Claude → Anthropic models, Codex → OpenAI models,
            # every other agent → cross-provider flagships (Opus 4.8 / ChatGPT 5.5
            # / Gemini 3.1 Pro). Selecting switches BOTH backend and model.
            if cmd == "model":
                from ai4science.harness import tui as _tui
                menu = _agent_model_menu(active_spec)
                if not arg:
                    # interactive ↑/↓/⏎ picker (like real Claude Code).
                    labels = [f"{lbl} ({mid})"
                              + ("  ← current" if (be == active_backend and mid == active_model) else "")
                              for lbl, be, mid in menu]
                    idx = _tui.ask_choice(
                        f"Select a model · {_tui._display_mode(active_spec.name)}", labels)
                    new_backend, new_model = menu[idx][1], menu[idx][2]
                else:
                    hit = _resolve_in_menu(menu, arg.strip().strip('"').strip("'"))
                    if hit is None:
                        opts = ", ".join(lbl for lbl, _, _ in menu)
                        print(f"[harness] {_tui._display_mode(active_spec.name)} "
                              f"can use: {opts}", flush=True)
                        continue
                    new_backend, new_model = hit
                if new_backend == active_backend and new_model == active_model:
                    print(f"[harness] model unchanged: {active_model}", flush=True)
                    continue
                try:
                    session.set_brand(adapter_for(new_backend), new_model, new_backend)
                    session.meter = _make_wrapped_meter(new_backend, new_model)
                    active_backend, active_model = new_backend, new_model
                    # User chose this brand explicitly — stop auto-healing away from it.
                    brand_autodetected = False
                    print(f"[harness] switched model: {active_model} "
                          f"(backend={active_backend})", flush=True)
                except ValueError as e:
                    print(f"[harness] error: {e}", flush=True)
                continue

            # /agent switches the active AgentSpec — handle inline (rebuilds
            # session). `/mode` kept as a silent back-compat alias.
            if cmd in ("agent", "mode"):
                from ai4science.harness import tui as _tui
                target = None
                if not arg:
                    # interactive ↑/↓/⏎ picker over the agents (like /model)
                    core = agent_registry.core_agents()
                    labels = [
                        f"{_tui._display_mode(s.name)} — {s.description}"
                        + ("  ← current" if s.name == active_spec.name else "")
                        for s in core
                    ]
                    idx = _tui.ask_choice("Select an agent", labels)
                    target = core[idx]
                else:
                    parts = arg.split(None, 1)
                    if parts[0] == "specific":
                        print(_format_specific_list(parts[1] if len(parts) > 1 else ""),
                              flush=True)
                        continue
                    # the agent name may be multi-word / quoted (e.g. "Computational
                    # Imaging"), so resolve the FULL argument, not just the first token.
                    name = arg.strip().strip('"').strip("'")
                    target = agent_registry.get(_tui.resolve_mode(name))
                    if target is None:
                        print(f"[agents] unknown agent {name!r}; /agent to list",
                              flush=True)
                        continue
                if target.name == active_spec.name:
                    print(f"[harness] agent unchanged: {_tui._display_mode(target.name)}",
                          flush=True)
                    continue
                active_spec = target
                # Enforce the agent's provider lock: Codex → OpenAI (ChatGPT),
                # Claude → Anthropic. Switch the brand to that provider's flagship
                # so a Codex session never runs on Claude (and vice-versa). Other
                # agents are cross-provider and keep the current backend/model.
                _lock = getattr(target, "default_backend", None)
                if _lock and active_backend != _lock:
                    _, active_backend, active_model = _agent_model_menu(target)[0]
                    brand_autodetected = False
                    print(f"[harness] backend → {active_backend} (model {active_model})",
                          flush=True)
                session = _build_session()
                # keep the full-TUI info line ("ai4science · <agent>") in sync
                _scr = getattr(_tui, "_ACTIVE", {}).get("screen")
                if _scr is not None:
                    _scr.mode = target.name
                print(f"[harness] switched agent: {_tui._display_mode(target.name)}",
                      flush=True)
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
        from ai4science.harness import mentions
        allowed, _greason = gate.check()
        if not allowed:
            print(_greason, flush=True)
            continue
        turn_cost["pwm"] = 0.0
        turn_cost["wallet"] = None
        turn_tools.clear()
        turn_counter["n"] += 1
        text, images = mentions.expand(line, workspace)

        def _do_turn():
            import time
            from ai4science.harness import interrupt
            from ai4science.harness import tui as _tui
            interrupt.clear()                   # stale Esc must not kill this turn
            turn_tokens["total"] = 0
            turn_calls["n"] = 0
            _live_tok["n"] = 0
            t0 = time.monotonic()
            _tui.begin_turn()                   # start the live "shining" status
            _spin["s"] = Spinner("thinking").start()   # shine until first token
            try:
                result = session.run_turn(text, images=images)
            finally:
                _stop_spin()
                _tui.end_turn()
            # Ensure there's a trailing newline after streamed output.
            if result and not result.endswith("\n"):
                print(flush=True)
            elapsed = time.monotonic() - t0
            print(toolfmt.fmt_turn_footer(seconds=elapsed,
                                          tools=turn_calls["n"],
                                          tokens=turn_tokens["total"]), flush=True)
            # One-sentence recap after substantial turns (Claude Code parity).
            # Decoration only — any failure is swallowed.
            from ai4science.harness import recap as recap_mod
            if recap_mod.should_recap(seconds=elapsed, tools=turn_calls["n"]):
                try:
                    rtext = recap_mod.generate_recap(
                        session.adapter, session.model,
                        user_text=text, final_text=result or "",
                        meter=session.meter)
                    if rtext:
                        print(f"\x1b[2m✶ recap: {rtext}\x1b[0m", flush=True)
                except Exception:
                    pass
            persistence.save(_sid, workspace, session.history)

        # Ctrl+C during a turn (inline/fallback mode = REPL on the main thread):
        # route SIGINT to the cooperative interrupt (like Esc / the TUI c-c
        # binding) so the turn ends and we return to the prompt for a NEW or
        # steering message — instead of a KeyboardInterrupt that exits the
        # program. Full-screen mode runs the REPL in a worker thread (signal
        # would fail there) and is handled by the TUI c-c binding, so guard on
        # the main thread. A 2nd Ctrl+C force-stops the turn.
        import signal as _signal
        import threading as _threading
        from ai4science.harness import interrupt as _intr
        _sigint = {"n": 0}

        def _sigint_handler(_signum, _frame):
            _intr.request()
            _sigint["n"] += 1
            if _sigint["n"] >= 2:
                raise KeyboardInterrupt        # 2nd press → hard-stop this turn
            print("\n[harness] interrupting… (Ctrl+C again to force-stop)", flush=True)

        _prev_sigint = None
        if _threading.current_thread() is _threading.main_thread():
            try:
                _prev_sigint = _signal.signal(_signal.SIGINT, _sigint_handler)
            except (ValueError, OSError):
                _prev_sigint = None
        try:
            _do_turn()
        except KeyboardInterrupt:
            _intr.clear()
            print("\n[harness] turn stopped — type a new message.", flush=True)
        except Exception as exc:
            # Directive 2026-06-11: NEVER stop the user — walk the whole
            # orchestration chain (Opus 4.8 → GPT-5.5 → safety net),
            # switching automatically until one model serves the turn.
            from ai4science.harness.adapters.factory import harness_available
            last = exc
            rest = [(b, m) for b, m in routing.AGENT_CHAINS.get("orchestration", [])
                    if (b, m) != (active_backend, active_model) and harness_available(b)]
            served = False
            for nb, nm in rest:
                print(f"\n[harness] {active_model} unavailable "
                      f"({_clean_turn_error(last)}) — switching to {nm}…", flush=True)
                active_backend, active_model = nb, nm
                session.set_brand(adapter_for(nb), nm, nb)
                session.meter = _make_wrapped_meter(nb, nm)
                try:
                    _do_turn()
                    served = True
                    break
                except Exception as e2:
                    last = e2
            if not served:
                print(f"\n[harness] all models are temporarily unavailable "
                      f"({_clean_turn_error(last)}). Retry in a moment.", flush=True)
        finally:
            if _prev_sigint is not None:
                try:
                    _signal.signal(_signal.SIGINT, _prev_sigint)
                except (ValueError, OSError):
                    pass

        ok, _creason = gate.charge(turn_cost["pwm"], turn_cost["wallet"],
                                   purpose=f"ai4science:{active_spec.name}:{active_model}",
                                   idempotency_key=f"{_sid}:{turn_counter['n']}")
        if not ok:
            print(_creason, flush=True)

        # Agent-mining: log usage of any registered contribution (domain tool)
        # invoked this turn → its author earns a share of the agent pool. Off by
        # default; the backend attributes only registered contributions and is
        # idempotent per (contribution, turn).
        if gate.enabled and turn_tools:
            _tid = f"{_sid}:{turn_counter['n']}"
            for _name in turn_tools:
                if _name not in BASE_TOOLS:
                    gate.post_usage(contribution_id=_name, agent_name=active_spec.name,
                                    turn_id=_tid)
