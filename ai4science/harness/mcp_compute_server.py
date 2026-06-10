"""Stdio MCP server exposing AI4Science's GPU/compute tools to EXTERNAL agent
engines — the real OpenAI codex CLI today, anything MCP-speaking tomorrow.

This is the codex-side counterpart of sdk_repl's in-process bridge for the
Claude Code engine: same three tools, same PWM semantics, same autonomy guard
(`compute_dispatch confirm=true` refuses in this non-interactive context
unless AI4SCIENCE_COMPUTE_AUTOCONFIRM=1 — the human opts in per session).

Run:  python3 -m ai4science.harness.mcp_compute_server
Env:  AI4SCIENCE_WS  — workspace path for the tools (default: cwd)
"""
from __future__ import annotations

import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from ai4science.harness.compute_tools import compute_tools

_WS = Path(os.environ.get("AI4SCIENCE_WS", ".")).expanduser().resolve()
_TOOLS = {t.name: t for t in compute_tools()}

mcp = FastMCP("ai4science")


def _run(name: str, **kwargs) -> str:
    try:
        return str(_TOOLS[name].func(_WS, **kwargs))
    except Exception as e:                       # surface, never crash the server
        return f"[{name} error] {type(e).__name__}: {e}"


@mcp.tool(description=_TOOLS["compute_providers"].description)
def compute_providers() -> str:
    return _run("compute_providers")


@mcp.tool(description=_TOOLS["compute_dispatch"].description)
def compute_dispatch(provider: str = "", run_command: str = "",
                     solver: str = "code/", benchmark: str = "",
                     max_runtime_s: int = 3600, confirm: bool = False) -> str:
    return _run("compute_dispatch", provider=provider, run_command=run_command,
                solver=solver, benchmark=benchmark,
                max_runtime_s=max_runtime_s, confirm=confirm)


@mcp.tool(description=_TOOLS["compute_result"].description)
def compute_result(job_id: str, provider: str = "") -> str:
    return _run("compute_result", job_id=job_id, provider=provider)


if __name__ == "__main__":
    mcp.run()          # stdio transport
