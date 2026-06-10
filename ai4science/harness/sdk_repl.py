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
    last_model = fallback_model or "claude-fable-5"
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
                                  ClaudeSDKClient, ResultMessage, TextBlock,
                                  ToolUseBlock)

    gate = PwmGate.from_env()
    if gate.enabled:
        print("[harness] PWM gate ON — each turn is charged to the provider in PWM",
              flush=True)
    permission_mode = ("plan" if plan_mode
                       else "acceptEdits" if auto_yes
                       else "default")
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
    )
    print(f"[harness] claude-code mode — REAL Claude Code engine "
          f"(claude-agent-sdk; permission_mode={permission_mode}) "
          f"+ PWM GPU tools ({', '.join(n.split('__')[-1] for n in mcp_allowed)}). "
          f"/feedback /exit are local; everything else is Claude Code.", flush=True)

    sid = secrets.token_hex(4)
    n = 0
    is_tty = sys.stdin.isatty()
    async with ClaudeSDKClient(options=options) as client:
        while True:
            try:
                if is_tty:
                    line = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: input("> "))
                else:
                    line = await asyncio.get_event_loop().run_in_executor(
                        None, sys.stdin.readline)
                    if not line:
                        break
                    print(f"> {line.rstrip()}", flush=True)
            except (EOFError, KeyboardInterrupt):
                break
            line = line.strip()
            if not line:
                continue

            # ── local commands (everything else goes to the engine) ──────
            low = line.lower()
            if low in ("/exit", "/quit", "/q", "exit", "quit"):
                break
            if low in ("/help", "/?"):
                print("[harness] local: /feedback <text>  /exit — all other input "
                      "(incl. Claude Code slash commands) goes to the engine.",
                      flush=True)
                continue
            if low.startswith("/feedback"):
                arg = line[len("/feedback"):].strip()
                if not arg:
                    print("[harness] usage: /feedback <your experience + how to "
                          "improve claude-code>", flush=True)
                    continue
                if not gate.enabled:
                    print("[pwm] feedback needs the PWM gate on "
                          "(AI4SCIENCE_PWM_GATE=1 + login --pwm).", flush=True)
                    continue
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
            async for msg in client.receive_response():
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            print(block.text, end="", flush=True)
                        elif isinstance(block, ToolUseBlock):
                            tools_used.append(block.name)
                            print(f"\n[tool] {block.name}", flush=True)
                elif isinstance(msg, ResultMessage):
                    result = msg
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
