"""ai4science as an ACP agent — the executor that needs only ai4science.

OpenClaw drives an external coding agent through the Agent Client Protocol: it
spawns a process, speaks JSON-RPC over its stdio, and the process is the agent.
`sarsi-claude` works that way, through `@agentclientprotocol/claude-agent-acp`,
and that adapter drives Claude.

`sarsi-ai4sci` is meant to be its sibling with one difference — *sarsi-claude
needs Claude; sarsi-ai4sci needs only ai4science* — and it could not be, because
ai4science shipped no ACP adapter. Its `runtime.acp.agent` therefore said
`"claude"`, and the identity was real while the executor underneath was not the
one asked for.

Two routes were possible and only one exists. OpenClaw's agent runtime schema is
a strict union of exactly two members:

    AgentRuntimeSchema = z.union([
      z.object({ type: z.literal("embedded") }).strict(),
      z.object({ type: z.literal("acp"), acp: AgentRuntimeAcpSchema }).strict(),
    ])

— checked in openclaw 2026.5.12 (f066dd2), `dist/zod-schema.agent-runtime-*.js`.
There is no command-backed executor runtime, so "skip the protocol and invoke
the CLI directly" is not available in this build. Speaking ACP is the only way in.

This module is that adapter. It is deliberately small: ACP is JSON-RPC 2.0 over
newline-delimited stdio, and the agent half of the handshake is four methods.
What it does NOT do is as important — it never spawns Claude, never reads an
Anthropic credential, and never imports the claude agent. The turn is served by
`ai4science.llm`, so whatever backend this machine has configured is what runs,
including a local model with no cloud credential of any kind.

Wire it up by giving acpx a custom agent alias pointing at:

    python3 -m ai4science.harness.acp

then setting the agent's runtime to `{"type": "acp", "acp": {"agent":
"ai4science", "backend": "acpx", ...}}`. Nothing in that names Claude, which is
p4 condition 1.
"""
from __future__ import annotations

from ai4science.harness.acp.server import ACPServer, serve

__all__ = ["ACPServer", "serve"]
