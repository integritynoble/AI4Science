# AI4Science vs Claude Code — function coverage

**What this is:** a direct mapping of Claude Code's key daily-development functions
onto what the AI4Science CLI provides today. AI4Science's `claude` agent embeds
the **claude-agent-sdk** (the same engine as Claude Code) with the **same tool
set**, so it inherits Claude Code's coding abilities and adds a PWM layer on top.

**Tool surface (identical core to Claude Code):**
`Read, Grep, Glob, Edit, Write, MultiEdit, Bash, Task` — plus PWM MCP tools
(`pwm_validate, pwm_judge_cassi, pwm_status, pwm_lookup_artifact`).

---

## Coverage matrix

| Claude Code function | AI4Science | How |
|---|---|---|
| **Understand the whole codebase** | ✅ | `Read` / `Grep` / `Glob` tools; auto-seeds workspace artifacts at session start; `@mentions`. |
| **Build new features** (multi-file) | ✅ | `Edit` / `Write` / `MultiEdit`; agentic loop (`max_turns=50`); confirms each edit. |
| **Fix bugs** | ✅ | `Read` + `Edit` + `Bash` (run the failing test/build, read output, iterate). |
| **Run terminal commands & tests** | ✅ | `Bash` tool (`pytest`, `npm test`, `dotnet test`, `python …`); reads output and continues. |
| **Refactor code** | ✅ | `Edit` / `MultiEdit` across files; rename, split, dedupe, migrate patterns. |
| **Generate & edit files directly** | ✅ | `Write` / `Edit` — new files, configs, scripts, tests, READMEs. |
| **Code review** | ✅ **+more** | Agent reviews diffs/changes; **plus** the deterministic Physics Judge (S1–S4) and `physics-reviewer` sub-agent for scientific review the LLM can't fake. |
| **Git workflow help** | ✅ | `Bash` git: inspect diffs, summarize, write commit messages, commit. (`--git-sync` automates pull/commit/push for the compute inbox.) |
| **Project documentation** | ✅ | `Write` README / `AI4SCIENCE.md` (= CLAUDE.md) / API docs; memory file is auto-loaded into the system prompt. |
| **Longer autonomous tasks** | ✅ | Agentic loop + **plan mode** (`--plan`, `/plan`) + **sub-agent delegation** (physics-reviewer, schema-validator, benchmark-architect). |

## Interactive chat parity (the REPL, `ai4science chat`)

| Capability | Status |
|---|---|
| Persistent REPL, token-level streaming | ✅ (same `ClaudeSDKClient`) |
| Tool use with per-edit confirmation + diff preview | ✅ |
| Memory (CLAUDE.md / AI4SCIENCE.md / AGENTS.md) | ✅ auto-loaded |
| `@mentions`, image attachments | ✅ |
| MCP servers + sub-agents | ✅ (PWM MCP + 3 PWM sub-agents) |
| Custom slash commands (`.ai4science/commands/*.md`) | ✅ |
| Live mode toggles `/yes` `/readonly` `/default` | ✅ |
| `/model [name]` — switch model live | ✅ |
| `/compact` — context usage + auto-compaction state | ✅ (SDK auto-compacts; no manual trigger exposed) |
| `/resume` + `--resume <id>` — session picker | ✅ |
| `/plan`, `/cost`, `/files`, `/commands`, `/validate`, `/judge`, `/status` | ✅ |
| Auto-route bare prompts to the real agent | ✅ |

## What AI4Science adds beyond Claude Code

- **Deterministic Physics Judge (S1–S4)** — un-gameable scientific verification; no LLM in the verdict path.
- **PWM MCP tools** — `pwm_validate / pwm_judge_cassi / pwm_status / pwm_lookup_artifact` callable mid-session.
- **GPU compute layer** — dispatch a reconstruction to a sub-GPU, judge re-verifies, credit a wallet (cross-machine, git-synced).
- **4-layer protocol awareness** — Principle → Spec → Benchmark → Solution.

## Genuinely out of scope (Claude Code product-shell features, not capability gaps)

IDE integrations (VS Code / JetBrains), `/vim`, `/bug` (reports to Anthropic),
`/pr-comments`, `/doctor`, `/terminal-setup`, `/login` (AI4Science rides the
existing `claude login`). These are product-surface features that don't apply to
a scientific-contribution CLI.

---

## Bottom line

For day-to-day development, **AI4Science covers every key Claude Code function**
— because it runs on Claude Code's own engine and tool set — and layers on the
physics-verification + GPU-compute capabilities Claude Code does not have. The
only differences are product-shell integrations that are out of scope for a PWM
tool.

The example prompt from the Claude Code summary works verbatim in AI4Science:

```
ai4science "Please inspect this repository first. Explain the architecture,
main modules, setup steps, and current problems. Then propose a step-by-step
implementation plan before editing any files."
```

(Auto-routes to the claude agent, uses Read/Grep/Glob to investigate, returns a
plan. Add `--plan` to guarantee no edits until you approve.)

---

## Interactive common mode runs on a native brand-agnostic harness (2026-05-31)

Common mode's default is a single live streaming agent on `ai4science/harness/` —
uniform streaming, per-edit confirmation + PWM sandbox, and a `/model` brand switch
across Anthropic / ChatGPT / Gemini (all driven by one native loop, no
`claude-agent-sdk` in the interactive path). `ai4science chat --mode common` launches
it via `harness/repl.py`; research mode keeps the SDK path.

This is **Option A** (uniform, self-owned harness) — chosen as the recursive
self-improvement substrate. Full Claude-Code polish (live bash streaming, rich diff
rendering, sub-agents, MCP, compaction, session persistence, @mentions/images, hooks)
is the REQUIRED parity work tracked in Plan 3. The opt-in best-of-N ensemble is Plan 2.
See docs/superpowers/specs/2026-05-31-common-mode-multibrand-ensemble-design.md.

---

## Plan 3a landed — interactive experience essentials (2026-05-31)

Common mode (native harness) now has: **live bash output streaming**, **rich unified-diff
previews** on edit/write confirmation, **session persistence** with `--continue` / `--resume`,
**context compaction** (summarize old history over a threshold), and the **full slash-command
set** (`/help /clear /model /readonly /yes /default /cost /files /exit`) with a per-turn token
footer. Mode toggles update the gate in place (history preserved).

Remaining toward full Claude-Code parity:
- **Plan 3b (DONE 2026-05-31)** — ✅ sub-agents (`Task` tool → nested `AgentSession`, depth-guarded);
  ✅ PWM MCP tools exposed natively (`pwm_validate/judge_cassi/status/lookup_artifact` — reconnects
  common mode to the science layer); ✅ stdio MCP client (namespaced `mcp__server__tool`);
  ✅ combined registry (core ∪ PWM ∪ task ∪ MCP) + `/agents` `/mcp` REPL commands. Out of scope:
  HTTP/OAuth MCP transports (stdio only); config-surface to pass external MCP servers into the REPL.
- **Plan 3c (DONE 2026-05-31)** — ✅ `@mentions` (typing `@path` inlines a text file's content, or
  attaches an image file as a multimodal image); ✅ image input across all 3 adapters (Anthropic
  base64 source, OpenAI data-URI image_url, Gemini inline_data). **Common mode is now at full
  Claude-Code parity.** Out of scope: clipboard image paste (terminal-dependent) — images are
  referenced by file path.
- **Plan 3d (DONE 2026-05-31)** — hardening: ✅ hard wall-clock bash timeout (reader thread +
  process-group kill, so a `sleep 1000`-style hang is killed promptly, not orphaned);
  ✅ bash-command sandbox guard (blocks `judge/`/`hidden_tests/`/parent-escape refs, incl.
  `;|&`-chained, even in auto-yes); ✅ Anthropic input-token metering (from `message_start`);
  ✅ loop-cap truncation signal; ✅ multi/parallel tool-call adapter coverage.
  Out of scope (future): OS-level bash isolation (bubblewrap/chroot) — the cmd guard is
  heuristic, not airtight against deliberate obfuscation — and real recorded provider stream
  fixtures (need live API creds; CI uses synthetic streams).

---

## Plan 3e — common mode runs LIVE (2026-05-31, verified)

The harness adapters were rewritten **SDK-free** to stream over the project's existing
REST endpoints (stdlib `urllib` SSE), reusing the credential resolvers (`llm/gemini`,
`llm/openai_compat`). No heavy SDKs; no new keys.

- **Verified live:** `ai4science chat --mode common` → `/model gemini` → "read app.py and
  tell me what it does" → Gemini streamed an answer derived from *actually reading the file*
  via the `read` tool round-trip, with token metering. Common mode genuinely works.
- **Reachable now (current creds):** gemini, openai*, deepseek, qwen (OpenAI-compat). Anthropic
  is key-gated (set `ANTHROPIC_API_KEY`) — its `claude` subscription CLI doesn't expose a key.
  (*openai-by-key returned 401 against api.openai.com — the env key isn't a direct OpenAI key;
  use gemini or set a real `OPENAI_API_KEY`.)
- **Default brand** = first reachable in the orchestration chain.
- **Gemini quirk fixed:** its OpenAI-compat endpoint requires echoing `extra_content.google.
  thought_signature` on tool round-trips (threaded via `ToolCall.extra`), else it 400s.

Common mode is now both feature-complete (Plans 1/3a/3b/3c/3d) AND live (Plan 3e).

---

## Plan 4 — research mode runs on the harness (2026-06-01)

`--mode research` now routes to the native harness via `run_common_repl`, using
`build_research_registry` and `RESEARCH_PROMPT` (built in Plan 4 / Task 3).

**What research mode adds on top of common mode:**
- `pwm_principles` / `pwm_principle` — list or fetch a registered Principle (L1).
- `pwm_benchmarks` / `pwm_benchmark` — list or fetch a registered Benchmark (L3).
- `pwm_solutions` — registered SOTA solutions + scores per benchmark.
- `pwm_overview` — top-level registry stats (principles, specs, benchmarks, solutions).
- A grounding system prompt that instructs the agent to consult registered baselines
  before proposing new solutions and to use chain_status to check mainnet/testnet state.

**Common mode** deliberately excludes these PWM data tools — that is the product moat.
Both modes share the same harness, session persistence, `--continue`/`--resume`, and
brand-switching (`/model`). Data is served from the PWM explorer API.

---

## Agent framework (2026-06-05)

**`/mode` menu** — lists `common` / `research` / `specific ▸ (N)` in the REPL. Type-to-search
with `/mode specific <query>`; switch directly with `/mode <name>`. New agents are
auto-discovered: drop an `AgentSpec`-exposing `.py` file into
`ai4science/harness/agents/specs/` and it appears in the menu on the next reload (plug-and-play).

**Two tiers / the moat:**
- `tier=open` (`common`) — pure Claude Code base, **no PWM tools, no PWM dataset**. Its
  `task` dispatch tool can reach only other `open` agents (never `research`, `paper`, or
  any `specific` domain agent). This is the hard wall.
- `tier=science` (`research` + all `specific` domain agents) — full Claude-Code base **plus**
  the PWM registry/dataset capabilities (`pwm-actions`, `pwm-data`). Science agents can
  dispatch each other freely.

**main-XOR-sub invariant** — the `task` dispatch tool is injected only when an agent runs as
MAIN (`is_subagent=False`). A sub-agent never receives a `task` tool, so named-agent nesting
depth is exactly 1 (no recursive delegation chains).

### Paper mode

`--mode paper` is a `tier=science` agent — it sits behind the same moat as research and
specific domain agents; common mode cannot dispatch to it. It exposes one tool: `paper_review`.

**Deep review** (gated) runs a deterministic multi-agent panel: three specialist reviewers
(novelty / soundness / clarity) plus an area-chair meta-review that synthesises their verdicts
into an **accept / borderline / reject** decision. Deep reviewers may call PWM registry tools
(`pwm_principles`, `pwm_benchmarks`, `pwm_solutions`) to ground novelty claims against
registered SOTA.

**Shallow review** (default, free) runs a single generalist reviewer; the decision is derived
directly from its numeric rating, with no panel overhead and no registry calls.

Both depths accept a PDF, Markdown, or LaTeX file by path. Output is a `ReviewBundle` written
as JSON + Markdown under `<workspace>/.ai4science/reviews/`. The JSON is the artifact that
`aixiv.physicsworldmodel.org` will consume.

The PWM charge for deep review is a **stubbed seam**: a `payment_gate` function keyed to env
var `AI4SCIENCE_PAPER_DEEP` (default enabled). The real charge-to-reviewer-wallet mechanics
are specified in the separate economics spec and are not implemented here.

### Specific domain agents

**Reusable pattern.** A domain agent is a `specs/<domain>.py` file that exports an
`AgentSpec` (`tier=science`, `category=specific`, domain expert system prompt, and a
capability list). A matching capability bundle in `capabilities.py` registers the domain's
tools under a named key. New domains (biology, chemistry, …) copy this shape: one spec
file, one capabilities entry.

**computational-imaging** is the first exemplar. Launch with `--mode computational-imaging`
(REPL: `/mode specific imaging`). It adds the `computational-imaging` capability bundle
from `cassi_tools.py` with four tools:

- `cassi_solutions` — lists **all** registered imaging solutions across mainnet and testnet;
  each entry is tagged with its chain (sources two chain-scoped explorer bases via env vars
  `PWM_EXPLORER_BASE_MAINNET` / `PWM_EXPLORER_BASE_TESTNET`).
- `cassi_forward_check` — computes the local CASSI physics residual ‖Φx−y‖/‖y‖ (CPU only,
  no GPU required).
- `cassi_dispatch` — submits a solver to the sub-GPU compute provider; **cost-guarded** by
  default: returns a PREVIEW showing the PWM cost and solution provider address unless
  `confirm=true` is passed. Running a registered solution charges PWM to the solution
  provider (genesis CASSI = third-founder `0xde81…1A29`); the actual debit is deferred to
  the economics layer.
- `cassi_result` — polls the dispatched job and invokes the judge to return PSNR / score_q.

**Moat.** All four tools are `tier=science`; the common-mode hard wall prevents common
agents from reaching them.

### Research onboarding (PWM contribution)

Research mode is the PWM **easy-onboarding UX layer**: it walks a contributor through
authoring an artifact (Principle, digital-twin, Benchmark, or Solution), submitting it to
the registry, and earning PWM tokens. This covers the off-chain author → quality-gate →
reward loop. On-chain promotion via the PWMRegistrar relay is a separate, later phase and
is explicitly out of scope here.

The `onboarding` capability bundle (`ai4science/harness/onboard_tools.py`) adds four tools:

- `onboard_guide(type)` — returns the required fields and a how-to for a given artifact
  type (`principle` / `digital-twin` / `benchmark` / `solution`).
- `onboard_submit(type, fields, confirm)` — POSTs to the live `pwm_nonprofit` API.
  **Confirm-guarded**: without `confirm=true` it returns a preview (no token required);
  passing `confirm=true` performs the actual submit (requires auth). On acceptance the
  server runs the S1–S4 quality gate and auto-awards PWM.
- `onboard_status()` — queries `/api/v1/pwm-token/transactions` to show recent ledger
  activity for the authenticated user.
- `onboard_balance()` — queries `/api/v1/pwm-token/balance` to show the current PWM
  balance.

**Auth.** A personal API key (`pwm_…`) is passed as `Authorization: Bearer <key>` and
read from env `PWM_ONBOARD_TOKEN`. The API base is `PWM_ONBOARD_BASE` (default
`physicsworldmodel.org`).

**Moat.** `onboarding` is `tier=science`; common mode cannot reach these tools.

---

### PWM usage gate (no free tier)

Every AI4Science agent turn costs PWM. There is no free tier. PWM is **earned only by
contributing** — mining artifacts (principles, digital-twins, benchmarks, solutions) and
making project contributions. The platform **never sells PWM**: the per-turn cost is a peer
transfer of earned PWM from the user's balance to the provider wallet that supplied the
turn's LLM/compute, not a platform fee.

**Gate implementation** (`ai4science/harness/pwm_gate.py`, class `PwmGate`)

- **Before each turn** — checks the user's earned PWM balance via `GET /api/v1/pwm-token/balance`.
  At ≤ 0 the turn is blocked and the agent returns an "earn PWM by contributing" message; no
  LLM call is made.
- **After each turn** — debits the metered per-turn PWM to the provider wallet via
  `POST /api/v1/pwm-token/spend` (handles 402 responses; idempotent on a per-turn key so
  retries don't double-charge). The agent already meters PWM per provider wallet; the gate
  posts the result.

**Config** — the gate is active only when `AI4SCIENCE_PWM_GATE` is set **and** a `pwm_…`
token is present (`PWM_TOKEN` or `PWM_ONBOARD_TOKEN`). The API base is `PWM_BASE` /
`PWM_ONBOARD_BASE` (default `physicsworldmodel.org`). Without those env vars the gate is
disabled, so dev and CI run free.

**Bootstrap** — a newcomer earns their first PWM via the free web onboarding flow (`/cli`
free-Haiku turn + `/submit` artifact), then spends it running the agent locally.

**Ledger** — off-chain today; on-chain settlement is the separate M6 relayer track.


## Option A landed — `--mode claude-code` runs the REAL Claude Code engine (2026-06-10)

**Honest correction first:** between 2026-05-31 (native harness) and today,
`ai4science chat --mode claude-code` ran on the brand-agnostic native harness —
same tool surface, but NOT the product experience this document's earlier
sections describe (those described the then-dormant claude-agent-sdk path: no
Claude Code system prompt, no TodoWrite, no plan mode, no compaction/hooks in
the native REPL).

**Now:** `--mode claude-code` routes to `harness/sdk_repl.py`, which runs the
**claude-agent-sdk** — the actual engine inside Claude Code — with:

- Claude Code's own system prompt (`system_prompt={"type":"preset","preset":"claude_code"}`)
- TodoWrite, plan mode (`--plan` → `permission_mode="plan"`), auto-compaction,
  hooks, sub-agents, CLAUDE.md project memory (`setting_sources=["user","project"]`)
- Anthropic maintains the experience; we don't chase parity feature-by-feature.

**PWM wrapper** (the AI4Science layer on top): `gate.check()` per turn;
`gate.charge()` metered from the SDK's per-model usage (bills the ACTUAL served
model — verified live: Claude Code routed a trivial turn to `claude-sonnet-4-6`,
ledger row `ai4science:claude-code:claude-sonnet-4-6`, 1.7e-05 PWM); non-base
tool uses → `post_usage`; `/feedback` intercepted locally (sustenance path).

**Fallback:** when the SDK or `claude` CLI is missing, chat prints why and
drops to the native harness — other modes untouched. Install:
`pip install 'pwm-ai4science[claude]'` + `claude login`.
Tests: `tests/test_sdk_repl.py` (5) + live verification 2026-06-10.

**The differentiator vs. stock Claude Code (director, 2026-06-10):** AI4Science's
claude-code can use **GPU compute from PWM GPU providers** (currently the
sub-GPU server) from inside the session — the harness compute tools
(`compute_providers` / `compute_dispatch` / `compute_result`) are bridged into
the engine as an in-process MCP server (`mcp__ai4science__*`, pre-allowed).
Verified live: the engine called `compute_providers` and listed
founder-1-subgpu + founder-gpu at $1.50/hr. Original Claude Code has no GPU
provider layer; this is PWM's addition on top of the genuine product
experience. GPU tool usage in paid turns is also logged for agent-mining
attribution (`post_usage`, mcp prefix stripped).


## codex mode runs the REAL OpenAI codex engine too (2026-06-10)

`--mode codex` now drives the installed **codex CLI** (`codex exec --json`) —
OpenAI's genuine agentic loop (their prompts, shell + apply_patch, AGENTS.md
project memory, session resume via thread_id) — wrapped with the same PWM
layer as claude-code (per-turn charge from the `turn.completed` usage event,
/feedback intercept, post_usage for MCP tools). Fallback to the native
harness when the CLI/login is missing.

**GPU service for codex:** the new stdio MCP server
(`ai4science/harness/mcp_compute_server.py`, registered via `codex mcp add
ai4science`) exposes compute_providers / compute_dispatch / compute_result to
any MCP-speaking engine. **Upstream limitation** (openai/codex #24135): codex
exec auto-cancels MCP calls non-interactively with no config override — so GPU
tools (and broken-bwrap hosts) require full-trust mode (`--yes` or
AI4SCIENCE_CODEX_GPU=1 → `--dangerously-bypass-approvals-and-sandbox`). The
PWM paid-dispatch guard still applies independently: even a full-trust codex
session cannot spend GPU PWM without AI4SCIENCE_COMPUTE_AUTOCONFIRM=1.

**Live-verified (2026-06-10):** AGENTS.md memory obeyed (planted MAGNOLIA rule,
every reply); coding loop apply_patch + shell → "self-test passed"
(independently re-run); multi-turn resume; the real codex called
mcp__ai4science compute_providers and summarized both GPU providers; 4 prod
ledger rows `ai4science:codex:gpt-5.5`. Units: tests/test_codex_repl.py (5).

## Interaction-UX parity — the terminal experience (2026-06-11)

After the real engines landed, a round of field use on real terminals (agent
host, Windows PowerShell, the UTSW cluster) surfaced the remaining gaps
between our REPL and Anthropic's Claude Code TUI. All fixed; the interaction
now matches the product's feel, not just its engine. Applies across the
native (research/unified-LLM), claude-code, and codex REPLs unless noted.

| Capability | Status | How |
|---|---|---|
| **Tool lines like the product** | ✅ (engine modes) | `⏺ Bash(ls /home/x)`, `⏺ Read(/a/b)`, `⏺ Todos [1/2] ✔…/▸…`; result summary `  ⎿ first line (+n lines)` / `  ⎿ ERROR: …` (`_fmt_tool`/`_fmt_result`, sdk_repl) |
| **Shining-star working indicator** | ✅ all 3 | animated `✶✷✸…` + elapsed seconds while thinking and while a tool runs, cleared on first streamed token (`harness/spinner.py`); no-op on pipes/CI |
| **Arrow keys + command history** | ✅ all 3 | ↑/↓ history, ←/→ cursor via readline (`harness/lineedit.py`); persisted per-mode `~/.config/ai4science/history_<mode>`; Windows via `pyreadline3` |
| **`/model` live switch** | ✅ all 3 | claude-code uses the SDK's native `set_model` (context kept); native/codex re-route per turn; aliases fable/opus/sonnet/haiku; billing follows the served model |
| **Interactive permission prompts** | ✅ claude-code | default mode on a TTY → `allow? [y/N/a(lways)]` per tool via `can_use_tool`; `--yes` = acceptEdits, `--plan` = read-only plan |
| **Clean exit** | ✅ all 3 | bare `exit`/`quit`/`q`/`:q`, `/exit`, Ctrl-D, or **Ctrl-C twice** (first cancels input) — no "trapped" state |
| **Input hygiene** | ✅ engine modes | strips tmux focus events (`^[[O`/`^[[I`), bracketed-paste markers, stray CSI; unwraps quote-pasted slash commands; disables focus reporting for the session (`_clean_input` + `\x1b[?1004l/2004l`) |
| **`❯` prompt + turn separators** | ✅ claude-code | matches the TUI's visual structure |

## The bordered TUI — Anthropic's full visual shell, for all agents (2026-06-11)

The last cosmetic mile is closed. `harness/tui.py` (prompt_toolkit) gives every
agent the product's visual shell, in three tiers via `AI4SCIENCE_TUI`:

| `AI4SCIENCE_TUI` | Experience |
|---|---|
| *(unset)* | plain line-REPL — default, zero regression |
| `1` / `box` | Claude-coral **rounded bordered input box** `╭─ ai4science · mode ─╮` with title, status row (`model · cwd`), hint row, Alt+Enter newline, per-mode FileHistory |
| `full` | **full-screen app like Anthropic's TUI**: output pane managed by the app (alt-screen), bordered input fixed at the bottom, persistent status bar with the **pulsing coral working star**, `/exit`/Ctrl-C/Ctrl-D restore the screen |

Architecture (full mode): the existing REPL loops run **unchanged** in a worker
thread. Their prints land in the pane through a stdout proxy (inline spinners
self-silence — the status bar owns the star), and every `input()` — the prompt,
claude-code's `allow? [y/N/a(lways)]` permission, the native per-edit confirm —
routes through `tui.read_input`, which blocks only the worker. So the engine
parity layer (PWM metering, `/feedback`, GPU tools) is untouched, and we still
never launch the raw `claude` binary.

**PTY-verified (2026-06-11), both paths:** native unified-LLM — alt-screen
entered, box+title rendered, `❯` echo, real LLM reply in the pane, star frames
animating, `/exit` killed the process and restored the screen (7/7 checks);
claude-code engine — `⏺ Bash` tool line, `⎿` result, reply, title, all in the
managed pane (5/5 checks). Suite 158/158 green.

**Versions:** exit `0.3.1` · arrow keys/history `0.3.3`–`0.3.4` (pyreadline3) ·
shining-star spinner `0.3.5` (engines) / `0.3.6` (native) · bordered box +
status bar `0.4.0`–`0.4.2` · **full-screen TUI `0.5.0`**. Pick up any build
with `pip install --user --force-reinstall --no-cache-dir
"pwm-ai4science[claude] @ https://github.com/integritynoble/AI4Science/archive/refs/heads/main.zip"`
(the `--no-cache-dir` matters — pip caches the GitHub zip by URL).
