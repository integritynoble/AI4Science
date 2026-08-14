"""ai4science as an ACP agent — the executor that needs only ai4science.

OpenClaw drives an external coding agent through the Agent Client Protocol: it
spawns a process, speaks JSON-RPC over its stdio, and the process is the agent.
`sarsi-claude` works that way, through `@agentclientprotocol/claude-agent-acp`,
and that adapter drives Claude. Its sibling `sarsi-ai4sci` is meant to differ in
exactly one respect — *sarsi-claude needs Claude; sarsi-ai4sci needs only
ai4science* — and could not, because ai4science shipped no ACP adapter.

Two routes were possible and only one exists. OpenClaw's agent runtime schema is
a strict union of exactly two members:

    AgentRuntimeSchema = z.union([
      z.object({ type: z.literal("embedded") }).strict(),
      z.object({ type: z.literal("acp"), acp: AgentRuntimeAcpSchema }).strict(),
    ])

— checked in openclaw 2026.5.12 (f066dd2), `dist/zod-schema.agent-runtime-*.js`.
There is no command-backed executor runtime, so "skip the protocol and invoke
the CLI directly" is not available. Speaking ACP is the only way in.

Wire it up by giving acpx a custom agent alias whose command is:

    python3 -m ai4science.harness.acp

then setting the agent's runtime to `{"type": "acp", "acp": {"agent":
"ai4sci", "backend": "acpx", ...}}`. Nothing in that names Claude.

The adapter drives the real CLI (`ai4science.cli chat --mode ai4sci`) as a
subprocess rather than calling the model layer in-process, so the mode, the
banner and the session ledger are all exercised — see `server.py`.
"""
from __future__ import annotations

from ai4science.harness.acp.server import (
    MODE, PROTOCOL_VERSION, Server, Session, drop_claude_from_env,
    engine_path, engine_python, parse_transcript, records_dir, serve,
)

__all__ = ["MODE", "PROTOCOL_VERSION", "Server", "Session",
           "drop_claude_from_env", "engine_path", "engine_python",
           "parse_transcript", "records_dir", "serve"]
