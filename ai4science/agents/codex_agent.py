"""CodexAgent — Phase A2.5 wiring to the OpenAI Codex CLI (read-only).

Runtime requirements:
  - `codex` CLI binary on PATH (https://github.com/openai/codex)
  - EITHER OPENAI_API_KEY in env OR `codex login` for ChatGPT subscription auth

Same read-only semantics as ClaudeAgent: workspace context is passed
inline; the agent's stdout is returned as text. We do NOT enable any
write tools; if you want the agent to edit files in your workspace, do
that with the underlying `codex` CLI directly (outside this wrapper).

This agent is intended for the AI **Overseer** role per the PWM
oversight architecture. AI4Science (contributor) uses Claude; Overseer
uses Codex. Hard rule: the two roles must use different LLM families.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional

from ai4science.agents._context import compose_prompt
from ai4science.agents.base import AgentResult, BaseAgent

# Timeout for one-shot Codex calls (seconds). Generous because cold-start
# auth flows + model load can be slow.
CODEX_TIMEOUT_SECONDS = 180


class CodexAgent(BaseAgent):
    name = "codex"

    def is_available(self) -> bool:
        """Available iff the `codex` CLI is on PATH.

        Auth (API key vs ChatGPT subscription) is handled by the CLI itself.
        We don't pre-judge — if auth fails at exec time, the subprocess
        surfaces the error and we relay it.
        """
        return shutil.which("codex") is not None

    def unavailable_reason(self) -> str:
        reasons: List[str] = []
        if shutil.which("codex") is None:
            reasons.append("`codex` CLI binary not on PATH "
                           "(install from https://github.com/openai/codex)")
        elif not os.environ.get("OPENAI_API_KEY"):
            reasons.append("note: OPENAI_API_KEY is unset — that's fine if you "
                           "ran `codex login` (ChatGPT Plus/Pro/Team subscription "
                           "auth). If neither is configured, the call will fail "
                           "at exec time.")
        return "; ".join(reasons) if reasons else "available"

    def run_task(self, prompt: str, workspace: Path,
                 context_files: List[Path]) -> AgentResult:
        if not self.is_available():
            return AgentResult(
                status="not_available",
                message=(f"CodexAgent is not available: {self.unavailable_reason()}."),
            )

        # Codex CLI does not have a top-level --system flag, so we embed the
        # AI4Science system prompt INSIDE the prompt blob.
        try:
            from ai4science.prompts import load_system_prompt
            system_text = load_system_prompt("ai4science_system")
        except Exception as e:
            return AgentResult(status="error",
                               message=f"could not load system prompt: {e}")

        full_prompt = compose_prompt(prompt, workspace, context_files,
                                      embed_system=system_text)

        cmd = _build_codex_command(workspace)

        try:
            proc = subprocess.run(
                cmd,
                input=full_prompt,
                capture_output=True,
                text=True,
                timeout=CODEX_TIMEOUT_SECONDS,
                check=False,
                env={**os.environ},   # inherit OPENAI_API_KEY etc.
            )
        except subprocess.TimeoutExpired:
            return AgentResult(
                status="error",
                message=f"codex timed out after {CODEX_TIMEOUT_SECONDS}s",
            )
        except (OSError, subprocess.SubprocessError) as e:
            return AgentResult(
                status="error",
                message=f"codex subprocess error: {type(e).__name__}: {e}",
            )

        if proc.returncode != 0:
            stderr_snippet = (proc.stderr or proc.stdout or "")[:800].strip()
            return AgentResult(
                status="error",
                message=(f"codex exited with code {proc.returncode}\n"
                         f"{stderr_snippet}"),
            )

        out = (proc.stdout or "").strip()
        if not out:
            return AgentResult(
                status="error",
                message="codex returned empty stdout (auth missing? try `codex login`)",
            )

        return AgentResult(status="ok", message=out)


def _build_codex_command(workspace: Path) -> List[str]:
    """Build the codex CLI invocation.

    Uses `codex exec` (the non-interactive subcommand) with the workspace
    as cwd. The prompt is piped via stdin to avoid argv length limits.

    NOTE: The OpenAI Codex CLI surface has evolved across releases. If your
    installed version uses different flag names, set the environment
    variable AI4SCIENCE_CODEX_CMD to a space-separated override, e.g.::

        export AI4SCIENCE_CODEX_CMD="codex exec --cd"
    """
    override = os.environ.get("AI4SCIENCE_CODEX_CMD")
    if override:
        parts = override.split()
        # Treat the final token as the position where the cwd argument
        # belongs only if it matches a known flag.
        if parts and parts[-1] in ("--cd", "-C"):
            return parts + [str(workspace.resolve())]
        return parts
    # Default: `codex exec --cd <workspace>` — prompt piped via stdin.
    return ["codex", "exec", "--cd", str(workspace.resolve())]
