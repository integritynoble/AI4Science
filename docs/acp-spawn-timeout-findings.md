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

**Verdict: configurable, but MASKED — the inner knob is real yet useless to the caller.**

### The timeout stack on the spawn path (innermost → outermost)

There are (at least) three nested timeouts between "spawn requested" and "caller gives up",
and each throws a DIFFERENT, identifiable message. None of them is the string the caller saw.

1. **Inner — Claude ACP session-create timeout (60s, env-configurable).**
   `createSession()` wraps `connection.newSession(...)` in
   `withTimeout(createPromise, resolveClaudeAcpSessionCreateTimeoutMs())` (line 3464). On fire
   it throws `ClaudeAcpSessionCreateTimeoutError(buildClaudeAcpSessionCreateTimeoutMessage())`.
   Message = "Claude ACP session creation timed out before session/new completed. ...".
   This is the ONLY timeout that reads `ACPX_CLAUDE_ACP_SESSION_CREATE_TIMEOUT_MS`.

2. **Middle — the gateway's own createSession timeout (`timeoutMs`).**
   `createFreshRuntimeSession` (line 5196-5197) wraps the WHOLE `client.createSession(...)` in a
   SECOND `withTimeout(..., timeoutMs)`:
   ```
   $ sed -n '5196,5198p' .../openclaw/dist/runtime-BzlxAzli.js
   async function createFreshRuntimeSession(client, record, timeoutMs) {
       const createdSession = await withTimeout(client.createSession(record.cwd), timeoutMs);
   ```
   On fire it throws the generic `TimeoutError`, whose message is fixed and does NOT read the
   env var:
   ```
   $ sed -n '530,538p' .../openclaw/dist/runtime-BzlxAzli.js
   var TimeoutError = class extends Error {
       constructor(timeoutMs) {
           super(`Timed out after ${timeoutMs}ms`);
   ```
   If `timeoutMs` (`this.options.timeoutMs`) is ≤ the inner 60s, THIS fires first and the inner
   env knob can never surface — raising the inner constant changes nothing because the outer
   race resolves first.

3. **Outer — the MCP request timeout (60s default).** The tool call carrying the spawn is an
   MCP request bounded by `options?.timeout ?? DEFAULT_REQUEST_TIMEOUT_MSEC` (60000, protocol.js
   line 8/712). On fire the SDK's own wording is `"Request timed out"` — again not what the
   caller saw.

### Why the observed message proves masking (message-identity argument)

The caller observed **"The operation timed out"** at ~80s. That string matches NONE of the
three openclaw/MCP messages above:
 - not "Claude ACP session creation timed out before session/new completed…" (inner)
 - not "Timed out after {n}ms" (middle)
 - not "Request timed out" (MCP)

A full-tree search finds the string in exactly ONE place — playwright-core's fake clock —
where it is literally built as a Web-Platform DOMException:
```
$ grep -rn "The operation timed out" .../node_modules/    # single hit, in playwright fake-clock:
new DOMException(browserName === "chromium" ? "signal timed out" : "The operation timed out.", "TimeoutError")
```
That is the canonical `AbortSignal.timeout()` / DOMException `"TimeoutError"` message emitted by
the JS platform (Node/undici) when an `AbortSignal.timeout(ms)` fires. So the caller's await was
resolved by a **platform-level abort ABOVE openclaw**, before any of openclaw's own timeout
errors could propagate up.

**Conclusion.** `ACPX_CLAUDE_ACP_SESSION_CREATE_TIMEOUT_MS` is a genuine, live read site (Part 1
proved that) — so "configurable" is true in the narrow sense. But on the path that bit us the
value the CALLER experiences is bounded by an OUTER timeout it does not set via that env var
(the platform `AbortSignal.timeout` at ~80s, and/or the 60s MCP request timeout). Because the
caller's error string is the platform DOMException and NOT `ClaudeAcpSessionCreateTimeoutMessage`,
we know for certain the inner timeout's result never reached the caller — it was masked.
Turning the inner knob up therefore cannot change what the caller sees. **Configurable but
masked; the honest answer for us is "useless on this path."** The fix must live in code we own
(Part 3), not in that env var.

### What the exact-80s figure would require (stated honestly)
The ~80s (vs 60s) tells us the dominating outer timeout is ~80s, not the 60s MCP default. Pinning
the exact 80000ms constant would require the CALLER's MCP-transport config (the `AbortSignal.timeout`
/ request-timeout the AI4Science MCP client passes when invoking `sessions_spawn`), which is not in
openclaw's dist and was not located in this run. It does not change the verdict: whatever its exact
value, it is an outer platform abort that masks the inner knob. See "Could not determine" below.

## Remedy (deliverable c)
See docs/red-evidence.txt / docs/green-evidence.txt and the wrapped-spawn implementation.
