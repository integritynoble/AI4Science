"""ClaudeAgent — Phase A2 wiring to the Claude Agent SDK.

v0.3 adds **tool use with diff preview** as the default for Claude:
the agent can Read / Grep / Glob (auto-approved) and Edit / Write /
Bash (each requires user confirmation, with a unified-diff preview for
Edit). Pass ``read_only=True`` or use ``--read-only`` on the CLI to
get the v0.2 read-only-text-only behavior.

Runtime requirements:
  - `claude` CLI on PATH (`npm install -g @anthropic-ai/claude-code`)
  - Either ANTHROPIC_API_KEY in env OR `claude login` (subscription auth)
  - `pip install ai4science[claude]`
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

# Tools the agent may consider. Auto-approved reads + confirmed edits.
DEFAULT_ALLOWED_TOOLS = ["Read", "Grep", "Glob", "Edit", "Write", "Bash", "MultiEdit"]


class ClaudeAgent(BaseAgent):
    name = "claude"

    def __init__(self, read_only: bool = False, auto_yes: bool = False):
        self.read_only = read_only
        self.auto_yes = auto_yes

    def is_available(self) -> bool:
        """Available iff `claude` CLI on PATH AND claude-agent-sdk importable.

        Auth (API key vs subscription) is handled by the `claude` CLI itself;
        we don't pre-judge it here. If auth fails at query time the SDK
        raises and we surface that error.
        """
        try:
            import claude_agent_sdk  # noqa: F401
        except Exception:
            return False
        if shutil.which("claude") is None:
            return False
        return True

    def unavailable_reason(self) -> str:
        reasons: List[str] = []
        try:
            import claude_agent_sdk  # noqa: F401
        except Exception as e:
            reasons.append(f"claude-agent-sdk not importable ({type(e).__name__}). "
                           "Install with: `pip install ai4science[claude]`")
        if shutil.which("claude") is None:
            reasons.append("`claude` CLI binary not on PATH "
                           "(install: `npm install -g @anthropic-ai/claude-code`)")
        if not os.environ.get("ANTHROPIC_API_KEY"):
            reasons.append("note: ANTHROPIC_API_KEY is unset — that's fine if you "
                           "ran `claude login` (subscription auth). If neither is "
                           "configured, the call will fail at query time.")
        return "; ".join(reasons) if reasons else "available"

    def run_task(self, prompt: str, workspace: Path,
                 context_files: List[Path]) -> AgentResult:
        if not self.is_available():
            return AgentResult(
                status="not_available",
                message=(f"ClaudeAgent is not available: {self.unavailable_reason()}. "
                         "Set ANTHROPIC_API_KEY or run `claude login`, "
                         "`pip install ai4science[claude]`, and install the "
                         "`claude` CLI, then re-run."),
            )

        full_prompt = compose_prompt(
            prompt, workspace, context_files,
            embed_system="",
            tools_enabled=not self.read_only,
        )

        try:
            from ai4science.prompts import load_system_prompt
            sysprompt_name = "ai4science_system_readonly" if self.read_only else "ai4science_system"
            system_prompt = load_system_prompt(sysprompt_name)
        except Exception as e:
            return AgentResult(status="error",
                               message=f"could not load system prompt: {e}")

        try:
            text, changed_files = asyncio.run(
                _run_query(
                    full_prompt=full_prompt,
                    system_prompt=system_prompt,
                    workspace=workspace,
                    read_only=self.read_only,
                    auto_yes=self.auto_yes,
                )
            )
        except KeyboardInterrupt:
            return AgentResult(status="error", message="interrupted by user")
        except Exception as e:
            return AgentResult(status="error",
                               message=f"Claude Agent SDK error: {type(e).__name__}: {e}")

        return AgentResult(status="ok", message=text, changed_files=changed_files)


async def _run_query(*, full_prompt: str, system_prompt: str, workspace: Path,
                     read_only: bool, auto_yes: bool):
    """Run a one-shot query through the SDK with appropriate tool/permission gates."""
    from claude_agent_sdk import (   # type: ignore
        query, ClaudeAgentOptions, AssistantMessage,
    )

    workspace = workspace.resolve()

    if read_only:
        # Strict v0.2 behavior — no tool calls at all; text-only output.
        options = ClaudeAgentOptions(
            system_prompt=system_prompt,
            allowed_tools=[],
            permission_mode="default",
            cwd=str(workspace),
            max_turns=6,
            model=DEFAULT_MODEL,
        )
        prompt_arg = full_prompt   # static string is OK without can_use_tool
    else:
        # v0.3 default: tool use ON, every change confirmed.
        from ai4science.agents.permissions import make_workspace_permission_callback
        can_use_tool = make_workspace_permission_callback(workspace, auto_yes=auto_yes)
        options = ClaudeAgentOptions(
            system_prompt=system_prompt,
            allowed_tools=DEFAULT_ALLOWED_TOOLS,
            permission_mode="default",
            can_use_tool=can_use_tool,
            cwd=str(workspace),
            max_turns=25,   # agentic loops need room
            model=DEFAULT_MODEL,
        )
        # The SDK requires streaming mode (AsyncIterable prompt) whenever a
        # can_use_tool callback is configured, so wrap the single message.
        prompt_arg = _single_user_message_stream(full_prompt)

    chunks: List[str] = []
    changed_files: List[Path] = []
    async for msg in query(prompt=prompt_arg, options=options):
        if isinstance(msg, AssistantMessage):
            for block in getattr(msg, "content", []):
                # Text blocks have .text; tool-use blocks have .input/.name.
                text = getattr(block, "text", None)
                if text:
                    # Separate text blocks with a blank line so the rendered
                    # output doesn't run sentences together when the agent
                    # interleaves tool calls with text.
                    if chunks and not chunks[-1].endswith("\n"):
                        chunks.append("\n\n")
                    chunks.append(text)
                # Track which files the agent touched (for the final summary).
                if hasattr(block, "name") and getattr(block, "name", None) in (
                    "Edit", "Write", "MultiEdit",
                ):
                    fp = (getattr(block, "input", None) or {}).get("file_path")
                    if fp:
                        try:
                            p = Path(fp)
                            if p not in changed_files:
                                changed_files.append(p)
                        except Exception:
                            pass
    return "".join(chunks).strip(), changed_files


async def _single_user_message_stream(text: str):
    """Yield exactly one user message — the streaming-mode equivalent of a
    single static prompt. Required by the SDK whenever can_use_tool is set.

    The SDK expects each yielded item to match the on-wire `user` event
    shape: ``{"type": "user", "message": {"role": "user", "content": ...}}``.
    """
    yield {
        "type": "user",
        "message": {
            "role": "user",
            "content": text,
        },
    }
