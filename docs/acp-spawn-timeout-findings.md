# ACP spawn/connect ~80s timeout — findings

Status: IN PROGRESS. This file is committed early and updated as evidence lands.

## Goal
Find the ~80s timeout in the OpenClaw ACP spawn/connect path (FILE, LINE, VALUE),
determine whether it is configurable on the spawn path, and remedy so a spawn
report distinguishes: (a) started+running, (b) started+finished, (c) never started.

## Search locations
1. acpx plugin: /home/tina1/.openclaw/npm/projects/openclaw-acpx-052d680d6d/node_modules/@openclaw/acpx/
   (dist/ + node_modules/)
2. OpenClaw gateway/session/spawn: /home/tina1/.nvm/versions/node/v24.19.0/lib/node_modules/openclaw
3. Our client (READ-ONLY): /home/tina1/pwm/AI4Science-engine/ai4science/harness/agents/sarsi/acp.py

## Findings (deliverable a) — the timeouts, verified from source

### Inner timeout: the Claude ACP session-create timeout (60s, env-configurable)

FILE: /home/tina1/.nvm/versions/node/v24.19.0/lib/node_modules/openclaw/dist/runtime-BzlxAzli.js

Line 1974 — the constant (6e4 = 60000 ms = 60s):
```
$ sed -n '1974p' .../openclaw/dist/runtime-BzlxAzli.js
const CLAUDE_ACP_SESSION_CREATE_TIMEOUT_MS = 6e4;
```

Lines 2044-2051 — a REAL env read site (not inert). Reads
`ACPX_CLAUDE_ACP_SESSION_CREATE_TIMEOUT_MS`, parses it, and falls back to the constant:
```
$ sed -n '2044,2051p' .../openclaw/dist/runtime-BzlxAzli.js
function resolveClaudeAcpSessionCreateTimeoutMs() {
	const raw = process.env.ACPX_CLAUDE_ACP_SESSION_CREATE_TIMEOUT_MS;
	if (typeof raw === "string" && raw.trim().length > 0) {
		const parsed = Number(raw);
		if (Number.isFinite(parsed) && parsed > 0) return Math.round(parsed);
	}
	return CLAUDE_ACP_SESSION_CREATE_TIMEOUT_MS;
}
```

Lines ~3452-3470 — the spawn/connect path. `connection.newSession({...})` is wrapped in
`withTimeout(...)` using the resolved timeout, and on timeout throws a
`ClaudeAcpSessionCreateTimeoutError` with `retryable: true`:
```
$ sed -n '3452,3470p' .../openclaw/dist/runtime-BzlxAzli.js
	async createSession(cwd = this.options.cwd) {
		const connection = this.getConnection();
		const { command, args } = splitCommandLine(this.options.agentCommand);
		const claudeAcp = isClaudeAcpCommand$1(command, args);
		const sessionCwd = await resolveAgentSessionCwd(cwd, this.options.agentCommand);
		let result;
		try {
			const createPromise = this.runConnectionRequest(() => connection.newSession({
				cwd: sessionCwd,
				mcpServers: this.options.mcpServers ?? [],
				_meta: buildClaudeCodeOptionsMeta(this.options.sessionOptions, claudeAcp)
			}));
			result = claudeAcp ? await withTimeout(createPromise, resolveClaudeAcpSessionCreateTimeoutMs()) : await createPromise;
		} catch (error) {
			if (claudeAcp && error instanceof TimeoutError) throw new ClaudeAcpSessionCreateTimeoutError(buildClaudeAcpSessionCreateTimeoutMessage(), {
				cause: error,
				retryable: true
			});
			throw error;
```

Line 2134 — the message this inner timeout produces (note: this is NOT what the caller saw):
```
$ sed -n '2134,2140p' .../openclaw/dist/runtime-BzlxAzli.js
function buildClaudeAcpSessionCreateTimeoutMessage() {
	return [
		"Claude ACP session creation timed out before session/new completed.",
		"This matches the known persistent-session stall seen with some Claude Code and @agentclientprotocol/claude-agent-acp combinations.",
		"In harnessed or non-interactive runs, prefer --approve-all with nonInteractivePermissions=deny, upgrade Claude Code and the Claude ACP adapter, or use acpx claude exec as a one-shot fallback."
	].join(" ");
}
```

### Outer timeout: the MCP request timeout (60s, the second independent ceiling)

FILE: /home/tina1/.nvm/versions/node/v24.19.0/lib/node_modules/openclaw/node_modules/@modelcontextprotocol/sdk/dist/esm/shared/protocol.js

Line 8 — the default request timeout constant:
```
$ sed -n '8p' .../@modelcontextprotocol/sdk/dist/esm/shared/protocol.js
export const DEFAULT_REQUEST_TIMEOUT_MSEC = 60000;
```

Lines 708-716 — every MCP request uses `options?.timeout ?? DEFAULT_REQUEST_TIMEOUT_MSEC`.
This wraps the tool call that carries `sessions_spawn`:
```
$ sed -n '708,716p' .../@modelcontextprotocol/sdk/dist/esm/shared/protocol.js
            });
            options?.signal?.addEventListener('abort', () => {
                cancel(options?.signal?.reason);
            });
            const timeout = options?.timeout ?? DEFAULT_REQUEST_TIMEOUT_MSEC;
            const timeoutHandler = () => cancel(McpError.fromError(ErrorCode.RequestTimeout, 'Request timed out', { timeout }));
            this._setupTimeout(messageId, timeout, options?.maxTotalTimeout, timeoutHandler, options?.resetTimeoutOnProgress ?? false);
```

Note: when THIS timeout fires, the MCP SDK's own wording is `"Request timed out"` — still
not the `"The operation timed out"` string the caller observed.

### Negative result — "The operation timed out" is generated ABOVE openclaw

The literal string does not exist anywhere in openclaw's own dist:
```
$ grep -rc "The operation timed out" .../openclaw/dist/ | grep -v ':0'
NOT FOUND in openclaw dist
```

And it is not the MCP SDK's wording either (that is `"Request timed out"`, line 713 above).
Therefore the message the caller sees ("The operation timed out") is generated ABOVE openclaw
— a platform/DOMException-style `TimeoutError` message (the Web Platform `AbortSignal.timeout()`
/ DOMException "TimeoutError" produces exactly this text). That is precisely why it is
uninformative and why all three outcomes (running / finished / never-started) collapse to one
identical string: the string carries no session identity and no lifecycle status.

## Configurable on the path that bit us? (deliverable b)
See section below — short answer: **configurable but masked**.

## Remedy (deliverable c)
See docs/red-evidence.txt / docs/green-evidence.txt and the wrapped-spawn implementation.
