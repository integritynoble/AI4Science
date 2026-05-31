# Common Mode — Brand-Agnostic Claude-Code Experience + Ensemble Power Mode

**Status:** Design (approved 2026-05-31; redesigned 2026-05-31 after UX review)
**Component:** AI4Science CLI — `common` session mode
**Author:** Director + Claude
**Related:** `docs/CLAUDE_CODE_PARITY.md`, `ai4science/llm/routing.py` (design point 10), roadmap items #1 (common mode), #6 (competition)

---

## 0. Why this was redesigned

The first design made common mode an *always-ensemble* pipeline (N agents run a task in
parallel, a judge panel picks a winner). UX review found this does **not** reproduce the
Claude Code experience: it loses live token streaming, per-edit confirmation, mid-task
steering, incremental feedback, and a single continuous conversation. An ensemble is
inherently a **fire-and-review batch tool**, not an interactive pair-programming REPL.

**Resolution:** common mode is split into two layers —
1. **Interactive common mode (default)** — *the* Claude Code experience, brand-swappable.
2. **Ensemble (opt-in power mode)** — best-of-N for hard/background/self-improvement/competition tasks.

And to make *every brand feel identical to Claude Code* (not import each vendor CLI's own
look-and-feel), the interactive layer is built on a **native streaming agentic harness**
(Approach A) with per-provider adapters — reversing the earlier "wrap vendor agents (B)" and
"always-ensemble default" decisions.

## 1. Summary

Common mode is the Claude-Code-equivalent developer experience. Its **default** is a single,
live, streaming agent you steer turn by turn — with per-edit confirmation, slash commands,
@mentions, and plan mode — where the **LLM brand is swappable** (Anthropic / ChatGPT / Gemini)
and the experience is identical across brands because they all drive **one native harness**.
Layered on top is an **opt-in ensemble** (`/ensemble`, or non-interactive `ensemble-run`):
the executor→judge best-of-N, reused for hard tasks, background runs, recursive
self-improvement (roadmap #1 goal 2), and the competition (#6).

Science mode (research pipeline + deterministic Physics Judge) is unchanged by this spec.

## 2. Goals / Non-goals

**Goals**
- **Experience parity:** interactive common mode matches Claude Code on streaming, per-edit
  confirmation + diff preview, plan/read-only/auto-yes modes, slash commands, @mentions,
  session resume, `/model`, `/cost` — *on any brand*.
- **Brand-agnostic by construction:** one native streaming tool-loop; Anthropic / OpenAI /
  Gemini are interchangeable **adapters**; switching brand mid-session (`/model`) changes
  nothing about the UX.
- **Ensemble as a power mode:** the executor→judge best-of-N is explicitly invoked, not the
  default; it is built on top of the harness (each executor is a harness instance bound to a brand).
- **PWM accounting:** every model call (interactive or ensemble) meters token→USD→PWM to the
  serving wallet/provider via the existing ledger.
- **Self-improvement substrate:** owning the loop (native harness) is what later lets the
  agent modify its own harness.

**Non-goals (this spec)**
- Recursive self-improvement itself (forward hook; the harness is the enabler).
- The on-chain mining competition economics (#6) — the ensemble is reusable for it; #6 is out of scope.
- Changing science/research mode or the deterministic Physics Judge.

## 3. Experience-parity requirements (the bar for "same as Claude Code")

| Capability | Requirement |
|---|---|
| Live streaming | Token-level streaming of the single active agent; live tool-call display (reading file, running bash). |
| Per-edit confirmation | Mutating tools (Edit/Write/Bash) prompt with a diff/command preview; respect `--yes` / `--read-only` / `/plan`. |
| Mid-task steering | User can interject between turns; conversation history persists. |
| Slash commands | `/help /exit /clear /model /mode /plan /cost /files /validate /judge /status /resume` etc. preserved. |
| @mentions, images | File @mentions and image inputs supported. |
| Brand switch | `/model` switches the active brand/model live with no UX change. |
| Session resume | `--continue` / `--resume <id>` work. |

Anthropic already meets this via `claude-agent-sdk`. The redesign's work is meeting it for
**OpenAI and Gemini** through the native harness so the bar is met uniformly.

## 4. Current state (what exists)

- `commands/chat.py` — REPL hardwired to `claude_agent_sdk` (`ClaudeSDKClient`); "Chat mode only supports `--agent claude`".
- `agents/` — `BaseAgent` ABC, `AgentResult` dataclass (`status, message, changed_files, suggestions`); `ClaudeAgent` (full loop), `CodexAgent` (one-shot), `NoneAgent`.
- `llm/routing.py` — roles `orchestration/checking/fast` as ordered fallback chains; `Route`, `resolve()`, `backend_available()`, `_select_source(backend) -> (source, provider_id, wallet, mult)`.
- `llm/execute.py` — per-backend **non-streaming** single-call executors `_run_anthropic/_run_openai/_run_gemini/_oc_executor`; `run_agent()`; its own `AgentResult` NamedTuple (`text, usage, route, error, cost`). These hold the **credential/client setup** (API keys, Vertex config) the new streaming adapters reuse.
- `llm/ledger.py` — `record(agent, backend, model, wallet, usage, cost)` JSONL ledger; `summary()`.
- `llm/pricing.py` — `price_call(model, usage, price_multiplier) -> {usd_official, usd_billed, pwm}`.
- `user.py` — `preference()`, `has_own_for(backend)`, config at `~/.config/ai4science/user.json`.

## 5. Architecture — interactive common mode (native harness, Approach A)

```
REPL (commands/chat.py)
   │  user input / slash commands / @mentions
   ▼
AgentSession  (ai4science/harness/session.py)
   │  holds message history + active brand + modes (read_only/auto_yes/plan)
   ▼
Agent loop  (harness/loop.py)
   │  call adapter.stream(messages, tools) → events
   │  ├─ text delta            → render to terminal (streaming)
   │  ├─ tool_call(name, args) → permission gate → execute tool → append result → continue
   │  └─ usage                 → meter to ledger
   ▼
Provider adapter  (harness/adapters/{anthropic,openai,gemini}.py)
   │  translate (messages, tool schemas) ↔ each brand's streaming function-calling API
   ▼
Tool registry  (harness/tools/*.py: read, write, edit, bash, grep, glob)
   │  uniform JSON-schema tools; mutating tools route through the permission gate
```

- **`AgentAdapter` interface:** `stream(messages, tools, *, model, reasoning) -> Iterator[Event]` where `Event` ∈ {TextDelta, ToolCall, Usage, Done}. One adapter per brand; reuses `llm/execute`'s client/credential setup. Switching brand = switching adapter; history is brand-neutral (normalized message list).
- **Tool registry:** uniform tools (`read, write, edit, bash, grep, glob`) with JSON schemas the adapters expose to each provider's function-calling. Mutating tools (`write, edit, bash`) pass through the **permission gate**.
- **Permission gate:** in `--read-only` blocks mutations; in `--yes` auto-approves; otherwise prompts with a diff/command preview (Claude Code behavior). `/plan` = read-only until the plan is approved.
- **Agent loop:** maintains normalized history; drives adapter streaming; dispatches tool calls; renders live; meters usage. Identical regardless of brand.
- **REPL:** `chat.py` uses `AgentSession` for **all** brands (Anthropic adapter routes through the harness too, for a uniform experience). `claude-agent-sdk` is retained only as an optional reference/fallback, not the interactive path.
- **PWM moat:** the tool registry enforces that the sandbox cannot touch `judge/`, `hidden_tests/`, locked benchmark files, or parent PWM folders — enforced uniformly in the gate (an advantage of owning the loop).

### Parity scope split
- **Harness MVP (Plan 1):** streaming + tool-calling adapters (3 brands), core tools (read/write/edit/bash/grep/glob), permission gate, REPL wiring, `/model` brand switch, accounting.
- **Parity extras (Plan 3):** MCP servers, sub-agents (`Task`), context compaction, custom slash commands, @mentions/images across the native harness.

## 6. Architecture — ensemble power mode (opt-in)

Unchanged best-of-N machinery, now **built on the harness** and **invoked explicitly**:

```
/ensemble <task>  (or:  ai4science ensemble-run "<task>")
   ▼ EXECUTOR STAGE (parallel, isolated)   each executor = a harness AgentSession bound to one brand,
   ├─ Opus 4.8      ┐ run non-interactively (auto-approve) in its own git worktree
   ├─ Sonnet 4.6    │ → Candidate{diff, answer, trace, cost, check_result}
   ├─ GPT-5.5       │
   └─ Gemini 3.1 Pro┘
   ▼ JUDGE STAGE (panel, non-agentic)  checking ∪ fast score all candidates (rubric + check_result)
   ▼ SELECT + APPLY  aggregate (senior-judge = Opus 4.8 tie-break); synthesis when top-2 within ε; apply winner diff
```

Because executors are harness sessions in auto-approve mode, the batch UX (no live steering)
is acceptable — the user opted in. The ensemble is also the substrate for self-improvement
and the #6 competition.

## 7. Model pools (both layers)

Roles become **pools**. Change from May-29: drop Opus 4.7 → use **Opus 4.8**.

| Pool | Role | Members (model id) |
|---|---|---|
| **Executor / interactive brands** | `orchestration` | `claude-opus-4-8`, `claude-sonnet-4-6`, `gpt-5.5`, `gemini-3.1-pro-preview` |
| **Judge** | `checking` | `gpt-5.5`, `claude-opus-4-8`, `gemini-3.1-pro-preview`, `deepseek-ai/deepseek-r1-0528-maas` |
| **Judge (fast)** | `fast` | `gemini-3.5-flash`, `claude-haiku-4-5`, `gpt-5.5-nano`, `qwen/qwen3-235b-a22b-instruct-2507-maas` |

Interactive mode uses one member at a time (user-selected via `/model`, default the first
reachable executor). The ensemble uses the full reachable pool. Judges run only in the ensemble.

## 8. Data flow, error handling, accounting

- **Interactive:** standard agent loop; tool errors surface inline; an unreachable brand falls back to the next reachable executor member (with a notice). Each adapter call meters usage to the ledger.
- **Ensemble:** executor error/timeout → candidate dropped; unreachable brand excluded; only-one-executor → skip panel, apply directly; judge failure → drop that score; diff-apply conflict → re-run winner on current state, else surface diff. Per-task token ceiling is the only backstop.
- **Accounting:** `pricing.price_call` + `ledger.record` per call. Interactive adapters surface usage natively (we own the loop), so interactive metering is exact — unlike the wrapped-SDK path.

## 9. Testing

- **Harness:** unit-test the tool registry (read/edit/write/bash/grep/glob) with `tmp_path`; the permission gate (read_only/auto_yes/prompt); the agent loop with a **stub adapter** emitting scripted events (text + tool calls) — no real LLM in CI. Each provider adapter has a parse/translate unit test against a recorded streaming fixture; real provider calls are manual/opt E2E.
- **Ensemble:** stub harness sessions returning canned candidates + deterministic stub judges → full pipeline (as in the existing ensemble plan).
- **Parity:** existing `chat.py` slash-command/streaming tests adapted to the harness.

## 10. Plan roadmap — execution order (Director's priority 2026-05-31: A first, then full Claude-Code parity, then ensemble)

1. **Plan 1 — Native interactive harness (FIRST).** `harness/` package: adapter interface + Anthropic/OpenAI/Gemini streaming-tool adapters, core tools, permission gate, agent loop, REPL wiring, `/model` brand switch, accounting. Delivers the *self-owned, uniform* core live experience on all three brands — the recursive-self-improvement substrate.
   File: `docs/superpowers/plans/2026-05-31-native-interactive-harness.md`
2. **Plan 3 — Full Claude-Code parity (SECOND).** REQUIRED to reach "same experience as Claude Code" under Option A: live bash streaming, rich diff rendering, sub-agents (`Task`), MCP, context compaction, session persistence, @mentions/images, hooks, full slash-command set. (Plan doc to be written after Plan 1 lands.)
3. **Plan 2 — Ensemble power mode (THIRD).** The executor→judge best-of-N, built on harness sessions, invoked via `/ensemble` / `ensemble-run`. (Re-scoped from the original core-pipeline plan.)
   File: `docs/superpowers/plans/2026-05-31-common-mode-ensemble-core-pipeline.md`

## 11. Resolved design decisions (settled 2026-05-31)

1. **Common-mode default = interactive single live agent** (Claude Code experience), brand-swappable. Ensemble is **opt-in**, not default.
2. **Interactive harness = native streaming loop (Approach A), chosen 2026-05-31 for recursive self-improvement (goal #2).** All brands — *including Anthropic* — route through our own harness for a uniform, fully self-owned substrate the agent can later read and modify. `claude-agent-sdk` is NOT the interactive path (optional fallback/reference only). **Accepted trade-off:** Anthropic is a reimplementation that will not match `claude-agent-sdk`'s polish until the harness matures — so **Plan 3 (parity extras: live bash streaming, rich diff rendering, sub-agents, MCP, compaction, session persistence, @mentions/images, hooks) is REQUIRED for full Claude-Code parity, not optional.** Independence from `claude-agent-sdk` and uniform PWM-sandbox enforcement are deliberate benefits of this choice.
3. **Judge panel = `checking ∪ fast`**; senior-judge tie-break = `claude-opus-4-8`.
4. **Synthesis** only when top-two aggregate scores are within `synthesis_epsilon` (default 0.05).
5. **Per-task token ceiling** (ensemble) generous, default ~2,000,000 tokens; user config + per-invocation override.
6. **`check_result`** auto-detect (`pytest` → `npm test` → `cargo test` → `go test`) with per-workspace override; omitted if none found.
7. **Executor concurrency** (ensemble) = config `max_parallel_executors`, default 4.
8. **Opus 4.7 → Opus 4.8** across all routing chains.
