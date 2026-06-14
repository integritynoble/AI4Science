"""Real Claude Code engine REPL — `ai4science chat --mode claude-code` (Option A).

Runs the **claude-agent-sdk** (the engine inside Anthropic's Claude Code) with
the genuine product experience: Claude Code's own system prompt (preset
``claude_code``), TodoWrite task tracking, plan mode, auto-compaction, hooks,
sub-agents and CLAUDE.md project memory — all maintained by Anthropic, not
re-implemented here.

The PWM layer wraps around it:
  • ``gate.check()`` before each turn, ``gate.charge()`` after — token-metered
    from the SDK's per-model usage, same pricing table as the native harness;
  • non-base tool uses logged via ``gate.post_usage`` (agent-mining);
  • ``/feedback`` intercepted locally (sustenance path);
  • ``/exit`` ``/quit`` ``/help`` handled locally; everything else (including
    Claude Code's own slash commands) goes straight to the engine.

Fallback: ``commands/chat.py`` calls :func:`sdk_available` first and routes to
the native harness when the SDK or the ``claude`` CLI is missing, so the other
five modes are untouched.
"""
from __future__ import annotations

import asyncio
import secrets
import shutil
import sys
from pathlib import Path
from typing import Optional, Tuple

from ai4science.harness.pwm_gate import BASE_TOOLS, PwmGate

AGENT_NAME = "claude-code"

_MODEL_ALIASES = {
    # Fable 5 suspended (US gov directive 2026-06-14) → alias resolves to Opus 4.8.
    "fable": "claude-opus-4-8", "fable-5": "claude-opus-4-8",
    "opus": "claude-opus-4-8", "opus-4-8": "claude-opus-4-8",
    "sonnet": "claude-sonnet-4-6", "sonnet-4-6": "claude-sonnet-4-6",
    "haiku": "claude-haiku-4-5", "haiku-4-5": "claude-haiku-4-5",
}


import re as _re
_CSI = _re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b[@-_]")


def _clean_input(line: str) -> str:
    """Strip terminal escape artifacts that leak into line input — tmux focus
    events (^[[I / ^[[O), bracketed-paste markers, stray CSI — which the real
    Claude Code TUI filters but a plain REPL receives raw. Also unwraps
    quote-pasted slash commands ('/model' → /model)."""
    line = _CSI.sub("", line)
    line = line.replace("\x1b", "").strip()
    if len(line) >= 2 and line[0] == line[-1] and line[0] in ("'", '"') \
            and line[1:2] == "/":
        line = line[1:-1].strip()
    return line


def _rule() -> str:
    import shutil as _sh
    cols = min(_sh.get_terminal_size((80, 20)).columns, 100)
    return "\x1b[2m" + "─" * cols + "\x1b[0m"


def sdk_available() -> Tuple[bool, str]:
    """Can the real Claude Code engine run here? (SDK import + claude CLI.)"""
    try:
        import claude_agent_sdk  # noqa: F401
    except ImportError:
        return False, ("claude-agent-sdk not installed — "
                       "pip install 'pwm-ai4science[claude]'")
    if not shutil.which("claude"):
        return False, ("claude CLI not on PATH — npm i -g @anthropic-ai/claude-code "
                       "then `claude login`")
    return True, ""


def _pwm_for(model_usage: dict, fallback_model: Optional[str]) -> Tuple[float, str]:
    """PWM cost of one turn from the SDK's per-model usage breakdown.

    Same pricing table as the native harness, so a claude-code turn costs the
    same whether served by the SDK engine or the native loop."""
    from ai4science.llm import pricing
    total = 0.0
    last_model = fallback_model or "claude-opus-4-8"
    for model, u in (model_usage or {}).items():
        ud = u if isinstance(u, dict) else getattr(u, "__dict__", {}) or {}
        usage = {"input": ud.get("input_tokens") or ud.get("inputTokens") or 0,
                 "output": ud.get("output_tokens") or ud.get("outputTokens") or 0}
        total += pricing.price_call(model, usage)["pwm"]
        last_model = model
    return round(total, 6), last_model


def _build_mcp(workspace: Path):
    """Bridge AI4Science's GPU/compute tools into the engine as an in-process
    MCP server — the differentiator vs. stock Claude Code: dispatch jobs to
    PWM GPU providers (currently the sub-GPU server) from inside the session.

    Returns (mcp_servers dict, allowed tool names) for ClaudeAgentOptions."""
    from claude_agent_sdk import create_sdk_mcp_server, tool as sdk_tool
    from ai4science.harness.compute_tools import compute_tools

    wrapped = []
    for t in compute_tools():
        def _make(ht):
            async def _handler(args: dict):
                loop = asyncio.get_event_loop()
                try:
                    out = await loop.run_in_executor(
                        None, lambda: ht.func(workspace, **(args or {})))
                except Exception as e:                      # surface, don't crash
                    out = f"[{ht.name} error] {type(e).__name__}: {e}"
                return {"content": [{"type": "text", "text": str(out)}]}
            return _handler
        wrapped.append(sdk_tool(t.name, t.description, t.parameters)(_make(t)))

    server = create_sdk_mcp_server(name="ai4science", version="1.0", tools=wrapped)
    allowed = [f"mcp__ai4science__{t.name}" for t in compute_tools()]
    return {"ai4science": server}, allowed


from ai4science.harness.spinner import STAR_COLOR as _SC
_STAR = f"{_SC}⏺\x1b[0m"            # Claude-coral dot (matches the spinner)
_ARM = "\x1b[2m  ⎿"                # dim result gutter
_RST = "\x1b[0m"


def _bash_auto_allow(tool_name: str, tool_input: dict) -> bool:
    """Claude Code parity: read-only shell commands run without a prompt."""
    if tool_name != "Bash":
        return False
    from ai4science.harness.permissions import is_read_only_bash
    return is_read_only_bash((tool_input or {}).get("command", ""))


def _fmt_tool(name: str, inp: dict) -> str:
    """Claude Code-style tool line: `⏺ Bash(ls /home/x)` instead of bare names."""
    inp = inp or {}
    if name == "Bash":
        arg = inp.get("command", "")
    elif name in ("Read", "Write", "Edit", "MultiEdit", "NotebookEdit"):
        arg = inp.get("file_path", "") or inp.get("path", "")
    elif name in ("Grep", "Glob"):
        arg = inp.get("pattern", "")
    elif name in ("Task", "Agent"):
        arg = inp.get("description", "") or inp.get("prompt", "")
    elif name == "TodoWrite":
        todos = inp.get("todos") or []
        done = sum(1 for t in todos if t.get("status") == "completed")
        items = "; ".join(
            ("✔ " if t.get("status") == "completed" else
             "▸ " if t.get("status") == "in_progress" else "· ")
            + str(t.get("content", ""))[:48] for t in todos[:6])
        return f"{_STAR} \x1b[1mTodos\x1b[0m [{done}/{len(todos)}] {items}"
    elif name == "WebFetch":
        arg = inp.get("url", "")
    else:
        arg = next((str(v) for v in inp.values() if isinstance(v, str) and v), "")
    arg = str(arg).replace("\n", " ")
    if len(arg) > 88:
        arg = arg[:85] + "…"
    return f"{_STAR} \x1b[1m{name}\x1b[0m({arg})"


def _fmt_result(content, is_error: bool) -> Optional[str]:
    """One dimmed summary line for a tool result, like Claude Code's `⎿ …`."""
    if isinstance(content, list):
        content = " ".join(b.get("text", "") for b in content
                           if isinstance(b, dict) and b.get("type") == "text")
    text = str(content or "").strip()
    if not text:
        return f"{_ARM} (no output){_RST}" if is_error else None
    first = text.splitlines()[0][:100]
    n = len(text.splitlines())
    tail = f" (+{n - 1} lines)" if n > 1 else ""
    err = "\x1b[31mERROR: \x1b[0m\x1b[2m" if is_error else ""
    return f"{_ARM} {err}{first}{tail}{_RST}"


def _provider_wallet() -> Optional[str]:
    try:
        from ai4science.llm import routing
        return routing._select_source("anthropic")[2]
    except Exception:
        return None


async def _loop(workspace: Path, *, auto_yes: bool, read_only: bool,
                plan_mode: bool, model: Optional[str],
                resume: Optional[str], continue_session: bool) -> None:
    from claude_agent_sdk import (AssistantMessage, ClaudeAgentOptions,
                                  ClaudeSDKClient, PermissionResultAllow,
                                  PermissionResultDeny, ResultMessage,
                                  TextBlock, ToolResultBlock, ToolUseBlock,
                                  UserMessage)

    gate = PwmGate.from_env()
    if gate.enabled:
        print("[harness] PWM gate ON — each turn is charged to the provider in PWM",
              flush=True)
    permission_mode = ("plan" if plan_mode
                       else "acceptEdits" if auto_yes
                       else "default")
    # Claude Code parity: in default mode on a TTY, permission requests become
    # interactive y/n/a prompts (a = always allow this tool for the session).
    _always: set = set()
    _spin = {"s": None}            # shared so the prompt can pause the star

    def _stop_spin() -> None:
        if _spin["s"] is not None:
            _spin["s"].stop()
            _spin["s"] = None

    async def _ask_permission(tool_name, tool_input, _ctx):
        if tool_name in _always:
            return PermissionResultAllow()
        if _bash_auto_allow(tool_name, tool_input):
            return PermissionResultAllow()
        _stop_spin()               # never let the star overwrite the prompt
        # The permission prompt OWNS the tool-line display in interactive mode
        # (the stream loop skips re-printing it).
        line = _fmt_tool(tool_name, tool_input or {})
        try:
            from ai4science.harness import tui, toolfmt
            prompt = toolfmt.fmt_permission_prompt(tool_name, line)
            ans = await asyncio.get_event_loop().run_in_executor(
                None, lambda: tui.read_input(prompt, "claude-code"))
        except (EOFError, KeyboardInterrupt):
            return PermissionResultDeny(message="denied by user")
        decision = toolfmt.parse_permission_answer(ans)
        if decision == "always":
            _always.add(tool_name)
            return PermissionResultAllow()
        if decision == "yes":
            return PermissionResultAllow()
        return PermissionResultDeny(message="denied by user")

    interactive_perms = (permission_mode == "default" and sys.stdin.isatty()
                         and not read_only)
    mcp_servers, mcp_allowed = _build_mcp(workspace)
    options = ClaudeAgentOptions(
        cwd=str(workspace),
        # THE Claude Code system prompt — the product experience, not a clone.
        system_prompt={"type": "preset", "preset": "claude_code"},
        setting_sources=["user", "project"],     # CLAUDE.md memory, like the product
        permission_mode=permission_mode,
        model=model,
        resume=resume,
        continue_conversation=continue_session,
        # AI4Science's edge over stock Claude Code: PWM GPU providers
        # (compute_providers / compute_dispatch / compute_result via MCP).
        mcp_servers=mcp_servers,
        allowed_tools=mcp_allowed,
        # AskUserQuestion is a TUI picker the line-REPL can't render — it would
        # hang the turn. Disallow it so the engine asks in plain text instead.
        disallowed_tools=["AskUserQuestion"],
        can_use_tool=_ask_permission if interactive_perms else None,
    )
    from ai4science import __version__ as _ver
    print(f"[harness] Claude mode — REAL Claude Code engine "
          f"(claude-agent-sdk; permission_mode={permission_mode}) "
          f"+ PWM GPU tools ({', '.join(n.split('__')[-1] for n in mcp_allowed)})  v{_ver}. "
          f"/feedback /exit are local; everything else is Claude Code.", flush=True)

    sid = secrets.token_hex(4)
    n = 0
    is_tty = sys.stdin.isatty()
    if is_tty:
        from ai4science.harness import lineedit
        lineedit.enable("claude-code")     # arrow-key history + cursor editing
    if is_tty:
        # the real Claude Code TUI manages these; in a line REPL they leak
        # escape artifacts into input — turn them off for the session.
        sys.stdout.write("\x1b[?1004l\x1b[?2004l")
        sys.stdout.flush()
    async with ClaudeSDKClient(options=options) as client:
        while True:
            try:
                if is_tty:
                    print(_rule(), flush=True)
                    from ai4science.harness import tui
                    _st = f"{model or 'claude-opus-4-8'} · {workspace.name or workspace}"
                    line = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: tui.read_input("❯ ", "claude-code", _st))
                else:
                    line = await asyncio.get_event_loop().run_in_executor(
                        None, sys.stdin.readline)
                    if not line:
                        break
                    print(f"❯ {line.rstrip()}", flush=True)
            except (EOFError, KeyboardInterrupt):
                break
            line = _clean_input(line)
            if not line:
                continue

            # ── local commands (everything else goes to the engine) ──────
            low = line.lower()
            if low in ("/exit", "/quit", "/q", "exit", "quit", "q", ":q"):
                break
            if low in ("/help", "/?"):
                print("[harness] local: /model [name]  /feedback <text>  /exit — "
                      "other input goes to the Claude Code engine.", flush=True)
                continue
            if low.startswith("/model"):
                arg = line[len("/model"):].strip().lower()
                if not arg:
                    cur = model or "(Claude Code default)"
                    print(f"[harness] model: {cur}\n  switch: /model "
                          f"opus | sonnet | haiku  (or any full model id)",
                          flush=True)
                    continue
                new_model = _MODEL_ALIASES.get(arg, arg)
                try:
                    await client.set_model(new_model)
                    model = new_model
                    print(f"[harness] model → {new_model} (session context kept)",
                          flush=True)
                except Exception as e:
                    print(f"[harness] model switch failed: {type(e).__name__}: {e}",
                          flush=True)
                continue
            if low.startswith("/feedback"):
                arg = line[len("/feedback"):].strip()
                if not arg:
                    print("[harness] usage: /feedback <your experience + how to "
                          "improve claude-code>", flush=True)
                    continue
                # Zero-login: post_feedback auto-provisions a local wallet when
                # not logged in, so feedback always submits and can earn PWM.
                ok, status = gate.post_feedback(agent_name=AGENT_NAME, text=arg)
                note = (status if ok and str(status).startswith("accepted")
                        else status if any(str(status).startswith(k) for k in
                                           ("use_agent_first", "balance_not_low",
                                            "need_more_usage"))
                        else "program full (first-N guard)" if status == "program_full"
                        else f"failed ({status})")
                print(f"[pwm] feedback for {AGENT_NAME}: {note}", flush=True)
                continue

            # ── PWM gate: block the turn on an empty balance ─────────────
            allowed, reason = gate.check()
            if not allowed:
                print(reason, flush=True)
                continue

            n += 1
            await client.query(line)
            tools_used: list[str] = []
            result: Optional[ResultMessage] = None
            from ai4science.harness.spinner import Spinner
            _spin["s"] = Spinner("thinking").start()   # shining star while we wait
            try:
                async for msg in client.receive_response():
                    if isinstance(msg, AssistantMessage):
                        for block in msg.content:
                            if isinstance(block, TextBlock):
                                _stop_spin()                 # text = the activity
                                print(block.text, end="", flush=True)
                            elif isinstance(block, ToolUseBlock):
                                _stop_spin()
                                tools_used.append(block.name)
                                # In interactive mode the permission prompt already
                                # printed this tool line — don't duplicate it.
                                if not interactive_perms:
                                    print(f"\n{_fmt_tool(block.name, block.input or {})}",
                                          flush=True)
                                _spin["s"] = Spinner(block.name.lower()).start()
                    elif isinstance(msg, UserMessage):
                        blocks = msg.content if isinstance(msg.content, list) else []
                        for block in blocks:
                            if isinstance(block, ToolResultBlock):
                                _stop_spin()
                                line2 = _fmt_result(block.content, bool(block.is_error))
                                if line2:
                                    print(line2, flush=True)
                                _spin["s"] = Spinner("thinking").start()
                    elif isinstance(msg, ResultMessage):
                        result = msg
            finally:
                _stop_spin()
            print(flush=True)

            # ── PWM: charge the turn + log domain-tool usage ─────────────
            if result is not None and gate.enabled:
                pwm, served_model = _pwm_for(
                    getattr(result, "model_usage", None) or {}, model)
                if pwm > 0:
                    ok, creason = gate.charge(
                        pwm, _provider_wallet(),
                        purpose=f"ai4science:{AGENT_NAME}:{served_model}",
                        idempotency_key=f"{sid}:{n}")
                    if not ok:
                        print(creason, flush=True)
                seen = {t.split("__")[-1] for t in tools_used}   # mcp__srv__name → name
                for t in {t for t in seen if t.lower() not in BASE_TOOLS}:
                    gate.post_usage(contribution_id=t, agent_name=AGENT_NAME,
                                    turn_id=f"{sid}:{n}")


def run_sdk_repl(workspace: Path, *, auto_yes: bool = False,
                 read_only: bool = False, plan_mode: bool = False,
                 model: Optional[str] = None, resume: Optional[str] = None,
                 continue_session: bool = False) -> None:
    """Synchronous entry point (mirrors run_common_repl's shape)."""
    try:
        asyncio.run(_loop(Path(workspace), auto_yes=auto_yes,
                          read_only=read_only, plan_mode=plan_mode, model=model,
                          resume=resume, continue_session=continue_session))
    except KeyboardInterrupt:
        pass
