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

## Remedy (deliverable c) — a spawn that reports the truth, in code WE own

Implemented in the clone only (`ai4science/harness/agents/sarsi/acp.py`); node_modules is
untouched. Test-first: RED in `docs/red-evidence.txt`, GREEN in `docs/green-evidence.txt`,
tests in `tests/sarsi/test_acp_spawn_report.py`.

### The change
`AcpRuntime` gains an injected `lookup` callable and a new `spawn(name, cwd, **kw)` method that
wraps the real spawn (`start`) and NEVER propagates a bare timeout. The caller can now tell the
three realities apart **from the return value alone**, via a `status` field:

| status | meaning | how it is decided |
|---|---|---|
| `RUNNING` (`"running"`) | (a) started and running | `start()` acknowledged, OR the ack was lost but a lookup found a live session |
| `FINISHED` (`"finished"`) | (b) started and finished | ack lost, lookup found a session in a finished state |
| `NEVER_STARTED` (`"never_started"`) | (c) never started | ack lost AND a **genuine negative lookup** found no session |
| `UNKNOWN` (`"unknown"`) | can't tell | ack lost and the lookup could not be performed (none configured, or it raised) |

Every return also carries `session_key` (so a follow-up can act on the handle regardless of
status) and a human `detail`.

### The invariant that drove the design
`never_started` is a POSITIVE claim and is returned **only** on a genuine negative lookup.
Absence of evidence is not evidence of absence: with no lookup configured, or a lookup that
itself raised, the result is `UNKNOWN`, never a guessed `never_started`. This is exactly the lie
Part 1/2 diagnosed ("The operation timed out" collapsing all three) — refusing to re-commit it is
the whole point. Two tests pin it:
`test_a_lookup_that_raises_does_not_become_never_started` and
`test_no_lookup_configured_does_not_become_never_started`.

### Why a `lookup` seam rather than a live gateway call
`lookup(session_key)` returns a truthy record (optionally with `state`) when the session exists,
a falsy value on a genuine negative, and may raise when it simply cannot tell. It is injected so
tests decide the answer deterministically and so production can point it at the gateway's session
listing (`sessions` / by label) without this file taking a hard dependency on — or a live call
to — the gateway. No test touches a real gateway; a unit test that needs a live gateway is a test
that dies with the gateway.

### Result
8/8 tests green (see `docs/green-evidence.txt`). The clean-spawn path reports `RUNNING` with the
handle; the timeout path is routed through the lookup and resolves to `RUNNING` / `FINISHED` /
`NEVER_STARTED` / `UNKNOWN` — never the identity-free, status-free platform string.

---

# Addendum (second executor, independent pass) — live-path copy, config-key verdict, and the 60→80s gap

> NOTE ON CONCURRENCY: two executors were working this branch at the same time.
> This addendum was written after Part 1/Part 2 above and does not contradict
> them; it pins the copy that is actually loaded, settles the config-key lead,
> and supplies a mechanical explanation for the 60s→~80s gap.

## A1. The copy that is actually loaded is NOT `openclaw/dist/runtime-BzlxAzli.js`

Parts 1-2 read `openclaw/dist/runtime-BzlxAzli.js`. That file is openclaw's own
*bundled* acpx backend. The **npm-installed external plugin is enabled** in the
live config (`plugins.entries.acpx.enabled: true`, project dir
`/home/tina1/.openclaw/npm/projects/openclaw-acpx-052d680d6d`), and that plugin
loads a *different* chunk:

```
$ sed -n '/^function loadRuntimeModule/,/^}/p' \
    /home/tina1/.openclaw/npm/projects/openclaw-acpx-052d680d6d/node_modules/@openclaw/acpx/dist/service-BqMIPoSJ.js
function loadRuntimeModule() {
	runtimeModulePromise ??= import("./runtime-B1cHS4Li.js");
	return runtimeModulePromise;
}
```

…and `runtime-B1cHS4Li.js` line 8 imports the real runtime from the plugin's
**nested `acpx` 0.11.2**, not from openclaw's bundle:

```
import { ACPX_BACKEND_ID, AcpxRuntime as AcpxRuntime$1, ... } from "acpx/runtime";
```

So the constant on the live path is:

```
FILE : /home/tina1/.openclaw/npm/projects/openclaw-acpx-052d680d6d/node_modules/@openclaw/acpx/node_modules/acpx/dist/live-checkpoint-mdAaF3qJ.js
LINE : 2653
VALUE: const CLAUDE_ACP_SESSION_CREATE_TIMEOUT_MS = 6e4;   // 60000 ms = 60 s
```

```
$ grep -n 'const CLAUDE_ACP_SESSION_CREATE_TIMEOUT_MS' \
    /home/tina1/.openclaw/npm/projects/openclaw-acpx-052d680d6d/node_modules/@openclaw/acpx/node_modules/acpx/dist/live-checkpoint-mdAaF3qJ.js
2653:const CLAUDE_ACP_SESSION_CREATE_TIMEOUT_MS = 6e4;
```

Env read site `resolveClaudeAcpSessionCreateTimeoutMs()` at lines **2723-2730**;
applied at line **4153** (`result = claudeAcp ? await withTimeout(createPromise,
resolveClaudeAcpSessionCreateTimeoutMs()) : await createPromise;`).

**All three copies on this box carry the identical value 6e4**, so the verdict is
unchanged — but the file/line to cite for the live path is the one above:

| copy | file | const line | env line | apply line |
|---|---|---|---|---|
| live plugin (`acpx` 0.11.2) | `.../@openclaw/acpx/node_modules/acpx/dist/live-checkpoint-mdAaF3qJ.js` | 2653 | 2724 | 4153 |
| openclaw-bundled | `.../openclaw/dist/runtime-BzlxAzli.js` | 1974 | 2045 | ~3464 |
| global `acpx` 0.13.0 | `.../lib/node_modules/acpx/dist/live-checkpoint-CBecfnSH.js` | 2846 | 2917 | 4355 |

**This is a hard-coded constant in vendored JS.** The remedy is "wrap", not
"config".

## A2. The LEAD settled: `plugins.entries.acpx.config.timeoutSeconds`

Three facts, each read from source/config:

1. **It is not set in the live config.** `~/.openclaw/openclaw.json`
   `plugins.entries.acpx.config` contains only `permissionMode` and `agents`
   (with `claude` → `/home/tina1/.openclaw/acpx/claude-run.sh`). The "120" is the
   **schema default** declared in
   `.../node_modules/@openclaw/acpx/openclaw.plugin.json:43-46`
   (`"timeoutSeconds": {"type":"number","minimum":0.001,"default":120}`).

2. **It is NOT an inert key.** It has a real read chain to the spawn path:
   `service-BqMIPoSJ.js:881` → `resolveAcpxTimerTimeoutMs(pluginConfig.timeoutSeconds)`
   → `new AcpxRuntime({ ..., timeoutMs })` → `this.options.timeoutMs` → the
   "Middle" `withTimeout(client.createSession(...), timeoutMs)` that Part 2 found
   at `createFreshRuntimeSession`. Its manifest help text agrees: *"Timeout for
   embedded ACP runtime startup and control operations. ACP turns use OpenClaw
   agent/run timeouts."*
   So this is **not** the `schema-valid-config-can-be-inert` failure mode.

3. **It still cannot be the timeout that fires.** Its effective value (120 s) is
   **twice** the inner Claude cap (60 s), and the inner cap sits strictly inside
   the operation the middle timeout wraps. The 60 s always wins the race.
   Part 2's caveat ("if `timeoutMs` ≤ 60s, the middle fires first") is therefore
   not the case here: `timeoutMs` = 120 000 > 60 000.

**Answer to "which timeout really fires at ~80s": the hard-coded 60 s
`CLAUDE_ACP_SESSION_CREATE_TIMEOUT_MS`, or the caller's own RPC wait — never
`timeoutSeconds`.** Raising `timeoutSeconds` is a no-op, which is consistent with
raising `AI4SCI_ACP_TIMEOUT` to 1800 s having had no effect.

## A3. Why 60 s of cap produced ~80 s of wall clock

On the Claude path, everything *before* `session/new` is **uncapped**. In
`initializeProtocolConnection()` the `initialize` handshake is wrapped in
`withTimeout` **only for Gemini**:

```
$ grep -n 'geminiAcp ? await withTimeout(initializePromise' \
    /home/tina1/.nvm/versions/node/v24.19.0/lib/node_modules/acpx/dist/live-checkpoint-CBecfnSH.js
4290:  const initialized = launch.geminiAcp ? await withTimeout(initializePromise, resolveGeminiAcpStartupTimeoutMs()) : await initializePromise;
```

(`GEMINI_ACP_STARTUP_TIMEOUT_MS = 15e3` at line 2845 of the same file.) For
Claude there is **no startup cap at all** — process spawn of
`claude-run.sh` plus the `initialize` round-trip run unbounded. On this
heavily I/O-loaded box that plausibly accounts for the ~20 s between t=0 and the
start of the 60 s `session/new` window.

So there are two readings of "~80 s", and both are consistent with Part 2's
message-identity proof:

* **(i)** the 60 s cap fired at t≈80 s wall clock (because ~20 s of uncapped
  spawn+initialize preceded it), and openclaw's error was then *replaced* by the
  caller's own abort message; or
* **(ii)** the caller's own ~80 s RPC deadline fired first and openclaw's inner
  error never propagated.

Either way the conclusion is identical and is the one that matters: **the string
the caller receives is produced above openclaw and carries no session identity
and no lifecycle status.** Part 2's grep is decisive on that point — the observed
wording matches none of openclaw's three timeout messages.

## A4. What remains undetermined

* Which of readings (i) / (ii) actually occurred on the three recorded
  dispatches. Settling it needs either gateway logs from those runs (there are
  none: `~/.openclaw/logs/` holds only `config-audit.jsonl`) or a fresh
  instrumented dispatch, which would restart work on a loaded box.
* The exact numeric value of the caller-side ~80 s deadline. It is not in
  openclaw's dist and not in the acpx trees (searched: whole `openclaw` tree,
  both `acpx` copies, `@openclaw/acpx`). It lives in the harness that issues the
  tool call, which was outside the three read-only search locations for this run.
