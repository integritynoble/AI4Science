# ACP spawn/connect ~80s timeout — findings

Status: (a) and (b) ANSWERED from source. See "Remedy" for (c)/(d).

## Goal
Find the ~80s timeout in the OpenClaw ACP spawn/connect path (FILE, LINE, VALUE),
determine whether it is configurable on the spawn path, and remedy so a spawn
report distinguishes: (a) started+running, (b) started+finished, (c) never started.

---

## (a) THE TIMEOUT — file, line, value

**It is a HARD-CODED constant in vendored JS.** It is not a gateway config key.

### Live path (the copy the gateway actually loads)

```
FILE : /home/tina1/.openclaw/npm/projects/openclaw-acpx-052d680d6d/node_modules/@openclaw/acpx/node_modules/acpx/dist/live-checkpoint-mdAaF3qJ.js
LINE : 2653
VALUE: const CLAUDE_ACP_SESSION_CREATE_TIMEOUT_MS = 6e4;      // 60000 ms = 60 s
```

Proof command:

```
grep -n 'const CLAUDE_ACP_SESSION_CREATE_TIMEOUT_MS' \
  /home/tina1/.openclaw/npm/projects/openclaw-acpx-052d680d6d/node_modules/@openclaw/acpx/node_modules/acpx/dist/live-checkpoint-mdAaF3qJ.js
# 2653:const CLAUDE_ACP_SESSION_CREATE_TIMEOUT_MS = 6e4;
```

**Where it fires** — same file, line 4153, inside `createSession()`, wrapping the
ACP `session/new` request, and only when the agent command is the Claude ACP
adapter (`claudeAcp = isClaudeAcpCommand(command, args)`):

```
sed -n '4148,4160p' <same file>
# 4153: result = claudeAcp ? await withTimeout(createPromise, resolveClaudeAcpSessionCreateTimeoutMs()) : await createPromise;
```

On expiry it throws `ClaudeAcpSessionCreateTimeoutError` with message
"Claude ACP session creation timed out before session/new completed. ..."
(`buildClaudeAcpSessionCreateTimeoutMessage()`), `retryable: true`.

### Why observed wall-clock is ~80 s, not 60 s

The 60 s cap covers **only** `session/new`. Everything before it is **unbounded**
on the Claude path:

* process spawn of the wrapper (`/home/tina1/.openclaw/acpx/claude-run.sh`)
* the ACP `initialize` handshake — `initializeProtocolConnection()` wraps
  `initialize` in `withTimeout` **only for Gemini**
  (`launch.geminiAcp ? await withTimeout(initializePromise, resolveGeminiAcpStartupTimeoutMs()) : await initializePromise`).
  For Claude there is no cap at all.

So ~80 s ≈ (unbounded spawn + initialize, ~15-20 s on this loaded box) + the 60 s
`session/new` cap. The single constant that terminates the wait is the 60 s one.

### The same constant in the other two copies (all identical, all 6e4)

| copy | file | line |
|---|---|---|
| gateway-vendored acpx | `/home/tina1/.nvm/versions/node/v24.19.0/lib/node_modules/openclaw/dist/runtime-BzlxAzli.js` | 1974 |
| global `acpx` 0.13.0 | `/home/tina1/.nvm/versions/node/v24.19.0/lib/node_modules/acpx/dist/live-checkpoint-CBecfnSH.js` | 2846 |
| live plugin `acpx` 0.11.2 | `/home/tina1/.openclaw/npm/projects/openclaw-acpx-052d680d6d/node_modules/@openclaw/acpx/node_modules/acpx/dist/live-checkpoint-mdAaF3qJ.js` | 2653 |

Sibling constant, for contrast (not on our path):
`GEMINI_ACP_STARTUP_TIMEOUT_MS = 15e3` — live copy line 2652.

---

## (b) Is it configurable?

**Yes — but only by an environment variable, not by any gateway config key.**

`resolveClaudeAcpSessionCreateTimeoutMs()` (live copy, lines 2723-2730) reads
`process.env.ACPX_CLAUDE_ACP_SESSION_CREATE_TIMEOUT_MS`:

```
sed -n '2723,2730p' /home/tina1/.openclaw/npm/projects/openclaw-acpx-052d680d6d/node_modules/@openclaw/acpx/node_modules/acpx/dist/live-checkpoint-mdAaF3qJ.js
```
```js
function resolveClaudeAcpSessionCreateTimeoutMs() {
	const raw = process.env.ACPX_CLAUDE_ACP_SESSION_CREATE_TIMEOUT_MS;
	if (typeof raw === "string" && raw.trim().length > 0) {
		const parsed = Number(raw);
		if (Number.isFinite(parsed) && parsed > 0) return Math.round(parsed);
	}
	return CLAUDE_ACP_SESSION_CREATE_TIMEOUT_MS;
}
```

That env var must be set **in the gateway process's own environment** (it is read
by `process.env` inside the gateway, not passed per-spawn). Setting it requires a
gateway restart, which is out of scope for this run. There is **no spawn argument
and no `openclaw.json` key** that reaches this value.

### The LEAD (`plugins.entries.acpx.config.timeoutSeconds`) — verified, and it is NOT the one that fires

Three separate facts, all read from source/config:

1. **It is not actually set.** The live `~/.openclaw/openclaw.json`
   `plugins.entries.acpx.config` contains only `permissionMode` and `agents`.
   The "120" is the **schema default** declared in
   `/home/tina1/.openclaw/npm/projects/openclaw-acpx-052d680d6d/node_modules/@openclaw/acpx/openclaw.plugin.json:43-46`
   (`"timeoutSeconds": { "type": "number", "minimum": 0.001, "default": 120 }`).

2. **It does have a real read site** — so it is not an inert key in the
   `schema-valid-config-can-be-inert` sense. Chain:
   `service-BqMIPoSJ.js:881` → `resolveAcpxTimerTimeoutMs(pluginConfig.timeoutSeconds)`
   → `new AcpxRuntime({ timeoutMs })` → `acpx/dist/runtime.js` uses
   `this.options.timeoutMs` for `client.start()`, `connectAndLoadSession(...)` etc.
   Its own manifest help text says: *"Timeout for embedded ACP runtime startup and
   control operations. ACP turns use OpenClaw agent/run timeouts."*

3. **It cannot be the timeout that fires at ~80 s.** Its value (120 s) is larger
   than the inner Claude cap (60 s), and the inner cap sits strictly inside
   `session/new`. Whichever races, the 60 s hard-coded constant expires first.
   Raising `timeoutSeconds` therefore cannot move the observed failure — which
   matches the field observation that raising `AI4SCI_ACP_TIMEOUT` (our adapter,
   1800 s) changed nothing either.

**Conclusion for (b): the remedy is "wrap", not "config".** The only in-band knob
is a gateway-process env var we may not set here without a restart. Since we must
not patch `node_modules` and must not restart the gateway, the honest fix belongs
in code we own.

### Also established (negative results, useful)

* The literal string `"The operation timed out"` that all three dispatches
  returned appears **nowhere** in `openclaw/dist` and nowhere in the acpx runtime.
  `acpx`'s own timeout error reads `Timed out after ${timeoutMs}ms`
  (`TimeoutError`), and the Claude-specific one reads *"Claude ACP session
  creation timed out before session/new completed."* So the string the caller saw
  was produced **above** the gateway, by the caller's own RPC wait — which is
  exactly why it carries no information about the child's fate. The only matches
  anywhere in either tree are in bundled Playwright clock-emulation code, which is
  not on this path.
* This is a **client-side wait**, not the motor's life. Consistent with the
  already-recorded observation that the ACP motor kept running and completed
  after the caller had been told it timed out.

---

## (c)/(d) Remedy

See `ai4science/harness/agents/sarsi/spawn_report.py` and
`tests/test_spawn_report.py`. RED output preserved under `docs/evidence/`.
