"""ClaudeAgent — Phase A2 wiring to the Claude Agent SDK (read-only).

Runtime requirements:
  - ANTHROPIC_API_KEY in environment
  - `pip install ai4science[claude]` (pulls claude-agent-sdk)
  - `claude` CLI binary on PATH (the SDK shells out to it)

Read-only semantics: allowed_tools=[] so the agent cannot edit any file.
Workspace context is passed inline in the prompt. The agent returns text;
the user copies whatever they want into their editor.
"""
from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path
from typing import List, Optional

from ai4science.agents._context import compose_prompt
from ai4science.agents.base import AgentResult, BaseAgent

DEFAULT_MODEL: Optional[str] = None   # None → SDK picks the default


class ClaudeAgent(BaseAgent):
    name = "claude"

    def is_available(self) -> bool:
        """Available iff the `claude` CLI is on PATH AND claude-agent-sdk is importable.

        Auth itself (API key vs subscription login) is handled by the
        underlying `claude` CLI, NOT by us. Two supported auth modes:

          1. API key:        export ANTHROPIC_API_KEY=...
          2. Subscription:   run `claude login` once; stores creds in ~/.claude/

        If auth fails at query time, the SDK raises and we surface that
        error to the user — we don't pre-judge their auth method here.
        """
        try:
            import claude_agent_sdk  # noqa: F401
        except Exception:
            return False
        if shutil.which("claude") is None:
            return False
        return True

    def unavailable_reason(self) -> str:
        """Human-readable explanation of why is_available() is False."""
        reasons: List[str] = []
        try:
            import claude_agent_sdk  # noqa: F401
        except Exception as e:
            reasons.append(f"claude-agent-sdk not importable ({type(e).__name__}). "
                           "Install with: `pip install ai4science[claude]`")
        if shutil.which("claude") is None:
            reasons.append("`claude` CLI binary not on PATH "
                           "(install: `npm install -g @anthropic-ai/claude-code`)")
        # Auth-mode hint (purely informational; we do NOT block on it).
        if not os.environ.get("ANTHROPIC_API_KEY"):
            reasons.append("note: ANTHROPIC_API_KEY is unset — that's fine if you "
                           "ran `claude login` (subscription auth). If neither is "
                           "configured, the call will fail at query time.")
        if not reasons:
            return "available"
        return "; ".join(reasons)

    def run_task(self, prompt: str, workspace: Path,
                 context_files: List[Path]) -> AgentResult:
        if not self.is_available():
            return AgentResult(
                status="not_available",
                message=(f"ClaudeAgent is not available: {self.unavailable_reason()}. "
                         "Set ANTHROPIC_API_KEY, `pip install ai4science[claude]`, and "
                         "install the `claude` CLI, then re-run."),
            )

        # Claude SDK accepts a separate system_prompt; don't embed it inline.
        full_prompt = compose_prompt(prompt, workspace, context_files, embed_system="")

        try:
            from ai4science.prompts import load_system_prompt
            system_prompt = load_system_prompt("ai4science_system")
        except Exception as e:
            return AgentResult(status="error",
                               message=f"could not load system prompt: {e}")

        try:
            text = asyncio.run(_run_query(full_prompt, system_prompt, workspace))
        except KeyboardInterrupt:
            return AgentResult(status="error", message="interrupted by user")
        except Exception as e:
            return AgentResult(status="error",
                               message=f"Claude Agent SDK error: {type(e).__name__}: {e}")

        return AgentResult(status="ok", message=text)


async def _run_query(prompt: str, system_prompt: str, workspace: Path) -> str:
    """One-shot, read-only call into claude-agent-sdk's `query()`."""
    from claude_agent_sdk import (   # type: ignore
        query, ClaudeAgentOptions, AssistantMessage,
    )

    options = ClaudeAgentOptions(
        system_prompt=system_prompt,
        allowed_tools=[],                       # ← read-only: no Edit/Write
        permission_mode="default",
        cwd=str(workspace.resolve()),
        # max_turns is a safety cap; with allowed_tools=[] the agent cannot
        # use tools, so a simple one-shot response is typically 1-2 turns.
        # Set generous headroom so longer explanations don't hit the limit.
        max_turns=6,
        model=DEFAULT_MODEL,
    )

    chunks: List[str] = []
    async for msg in query(prompt=prompt, options=options):
        if isinstance(msg, AssistantMessage):
            for block in getattr(msg, "content", []):
                # ContentBlock subclasses expose .text on text blocks.
                text = getattr(block, "text", None)
                if text:
                    chunks.append(text)
    return "".join(chunks).strip()


