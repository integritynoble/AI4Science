# Common Mode — Multi-Brand Executor-Ensemble → Judge-Panel

**Status:** Design (approved 2026-05-31)
**Component:** AI4Science CLI — `common` session mode
**Author:** Director + Claude
**Related:** `docs/CLAUDE_CODE_PARITY.md`, `ai4science/llm/routing.py` (design point 10), roadmap items #1 (common mode), #6 (competition)

---

## 1. Summary

Common mode is the Claude-Code-equivalent agentic developer experience. Today it is driven
by a **single** backend hardwired to the Claude Agent SDK (`commands/chat.py`); ChatGPT runs
only one-shot and Gemini is chat-only. This spec replaces the single-driver model with a
**multi-brand executor-ensemble → judge-panel** pipeline: every common-mode task is attempted
in parallel by several brand-driven agentic loops, scored by a panel of judge models, and the
winning candidate is applied. This is how "use several brands (Anthropic, ChatGPT, Gemini)"
is realized — and it is the substrate for later recursive self-improvement (roadmap #1, goal 2).

There is **one** common mode and it **is** the ensemble (no separate single-model common mode).
Science mode (research pipeline + deterministic Physics Judge) is unchanged by this spec.

## 2. Goals / Non-goals

**Goals**
- Each of Anthropic / OpenAI / Gemini drives a full agentic tool-loop (Read/Edit/Write/Bash/Grep/Glob/Task + MCP + permissions).
- Every common-mode task runs the full executor pool in parallel (always-ensemble), then a judge panel selects a winner, which is applied to the workspace.
- Per-candidate objective signal: the repo's own tests/build run against each candidate worktree feed the judges (verification, not vibes — mirrors the Physics-Judge philosophy).
- All executor + judge calls accrue token→USD→PWM to the serving wallet/provider via the existing ledger.
- The ensemble layer is written once against the existing `BaseAgent`/`AgentResult` seam so individual vendor drivers can later be swapped for native provider adapters (Approach A) without changing the ensemble.

**Non-goals (this version)**
- Recursive self-improvement (forward hook only; unlocked by the native-loop migration).
- The on-chain mining competition / two-winner economics (roadmap #6) — the judge panel is reusable for it later, but #6 is out of scope here.
- Changing science/research mode or the deterministic Physics Judge.
- Cost-based throttling of the ensemble (decision: always-ensemble; only a hard per-task token ceiling guards runaway).

## 3. Current state (what exists)

- `commands/chat.py` — interactive REPL, **hardwired to `claude_agent_sdk`** (`ClaudeSDKClient`); line ~112: "Chat mode only supports `--agent claude`".
- `agents/` — `BaseAgent` ABC with `run_task(prompt, workspace) -> AgentResult`; `ClaudeAgent` (full loop), `CodexAgent` (one-shot prompt), `NoneAgent` (stub). No Gemini agent.
- `llm/routing.py` — `AGENT_CHAINS` defines roles `orchestration` / `checking` / `fast` as **ordered fallback chains** (pick first reachable). Resolves chosen backend → wallet provider. `AGENT_REASONING` per role.
- `llm/execute.py` — per-backend single-call executors (`_run_anthropic/_run_openai/_run_gemini/_oc_executor`) and `run_agent(agent, prompt)` (single LLM call along a role chain). Backends live: anthropic, openai (codex), gemini, deepseek (Vertex), qwen (Vertex).
- `llm/ledger.py`, `compute/pricing.py` — token→USD→PWM accounting per wallet.
- `compute/gitsync.py` — git worktree / sync machinery (reuse for isolation).

The model membership already matches the Director's plan; the gap is **ensemble + judge-panel + aggregation** plus making OpenAI/Gemini full agentic drivers.

## 4. Model pools

Roles become **pools** (all reachable members run in parallel for the ensemble), not first-pick chains.
Change from the May-29 design: **drop Opus 4.7 everywhere → use Opus 4.8.**

| Pool | Role | Members (model id) |
|---|---|---|
| **Executor** | `orchestration` | `claude-opus-4-8`, `claude-sonnet-4-6`, `gpt-5.5`, `gemini-3.1-pro-preview` |
| **Judge** | `checking` | `gpt-5.5`, `claude-opus-4-8`, `gemini-3.1-pro-preview`, `deepseek-ai/deepseek-r1-0528-maas` |
| **Judge (fast)** | `fast` | `gemini-3.5-flash`, `claude-haiku-4-5`, `gpt-5.5-nano`, `qwen/qwen3-235b-a22b-instruct-2507-maas` |

- Executors are **agentic** (drive tool-loops). Judges are **non-agentic** scoring calls.
- The full judge panel = `checking` ∪ `fast` members (configurable); fast members keep the panel cheap and break ties.
- Chinese open models (DeepSeek-R1, Qwen) participate in the judge panel; both are already wired via Vertex.
- Reasoning effort per `AGENT_REASONING` (orchestration/checking = high, fast = low).

## 5. Architecture

```
task
 │
 ▼  EXECUTOR STAGE  (parallel, isolated)
 ├─ executor[opus-4-8]    ─► worktree A ─► Candidate{diff, answer, trace, cost, check}
 ├─ executor[sonnet-4-6]  ─► worktree B ─► Candidate
 ├─ executor[gpt-5.5]     ─► worktree C ─► Candidate
 └─ executor[gemini-3.1]  ─► worktree D ─► Candidate
 │
 ▼  JUDGE STAGE  (panel, non-agentic)
 ├─ judge[gpt-5.5]       ─┐
 ├─ judge[opus-4-8]       ├─ each scores ALL candidates (rubric + check_result) ─► JudgeScore[]
 ├─ judge[gemini-3.1]     │
 ├─ judge[gemini-flash]   │
 └─ judge[deepseek-r1]   ─┘
 │
 ▼  SELECT + APPLY
 ├─ aggregate scores (mean rank; senior-judge tie-break) → winner
 ├─ optional synthesis pass (graft runner-up ideas)
 └─ apply winner.diff to real workspace; return winner.answer
```

Pure Q&A tasks (no file changes) skip worktrees: candidates are answers only; judges score answers; winner's answer is returned.

## 6. Components

### 6.1 `agents/` — brand-driven executors (Approach B)
Common contract (extends existing `BaseAgent`):

```python
@dataclass
class AgentResult:
    answer: str            # final assistant text
    diff: str | None       # unified diff of workspace changes (None for Q&A)
    trace: list            # tool-call trace (for judges / debugging)
    cost: CostRecord       # tokens, usd, pwm, wallet/provider
    check_result: dict | None  # objective test/build outcome (filled by runner)
    error: str | None
```

- `ClaudeAgent` — keep (claude-agent-sdk).
- `CodexAgent` — promote one-shot → **full agentic loop** via OpenAI Codex/Agents SDK.
- `GeminiAgent` — **new**; wrap the open-source **Gemini CLI** as a `BaseAgent`.
- Each `run_task(prompt, workspace, *, read_only, reasoning)` runs the loop in `workspace` (a worktree) and returns an `AgentResult` (diff computed by the runner via git).

### 6.2 `ensemble/` (new module)
- `pool.py` — `executor_members()` / `judge_members()`: reachable members of the pools (availability via `routing.backend_available`); applies the Opus-4.8 change; resolves each to its wallet provider.
- `runner.py` — for a coding task: create one git worktree per executor (reuse `compute/gitsync`), run executors **concurrently**, compute each `diff` via git, run the repo's configured test/build command in each worktree → `check_result`, collect `Candidate`s. Executor error/timeout → candidate dropped.
- `panel.py` — run judge members **concurrently** (non-agentic) over the candidate set with a structured rubric; each judge is invoked on a **specific** `(backend, model)` via `llm/execute`'s per-backend executors (not the first-pick `run_agent` router); return `JudgeScore[]`. Forced structured output (JSON schema) per judge.
- `select.py` — aggregate `JudgeScore[]` (mean rank; **senior-judge tie-break — senior judge = `claude-opus-4-8`**), pick winner; optional synthesis pass; return `Selection{winner, ranking, rationale}`.

### 6.3 `llm/routing.py`
- Add `ensemble_members(role) -> list[(backend, model)]` returning **all** reachable members (keep `route()` for single-pick paths used elsewhere).
- Apply Opus 4.7 → 4.8 in `AGENT_CHAINS`.

### 6.4 `commands/chat.py`
- Replace the hardwired Claude-SDK driver with `ensemble.runner` for common mode. The REPL turn becomes: collect input → run ensemble pipeline → stream the winner's answer + show which brand won + per-candidate cost footer → apply diff (with the existing per-edit confirmation/permission gate on the winning diff). Slash commands and session features preserved.

### 6.5 Accounting
- Each executor and judge call records its `CostRecord` to `llm/ledger.py` against the serving wallet/provider (existing token→USD→PWM path). The REPL footer shows per-task aggregate PWM.

## 7. Data flow & key types

```python
@dataclass
class Candidate:
    member: tuple[str, str]      # (backend, model)
    result: AgentResult          # answer/diff/trace/cost/check_result
    worktree: Path | None

@dataclass
class JudgeScore:
    judge: tuple[str, str]
    ranking: list[int]           # candidate indices, best→worst
    scores: dict[int, float]     # per-candidate 0..1
    rationale: str

@dataclass
class Selection:
    winner: int                  # candidate index
    ranking: list[int]
    rationale: str
```

Judge rubric inputs per candidate: task prompt, candidate `answer`, `diff`, and `check_result`
(tests passed/failed, build status). Judges must justify the ranking; `check_result` is an
objective anchor so a candidate that fails the repo's tests cannot be ranked first on style alone.

## 8. Error handling & degradation

- **Executor failure/timeout** → candidate dropped (parallel-null-filter); pipeline proceeds with the rest.
- **Backend unreachable** → excluded from the pool by availability check.
- **Only one executor reachable** → skip the panel, apply it directly (still recorded).
- **Zero executors** → hard error with a clear message (no backend configured).
- **Judge failure** → that judge's score dropped; aggregate over remaining judges; if all judges fail, fall back to the executor whose `check_result` is best (tests pass), else the senior executor (Opus 4.8).
- **Diff apply conflict** (workspace drifted while executors ran) → re-run the winner on the current workspace state; if still conflicting, surface the diff for manual apply.
- **Token ceiling** → a per-task hard cap aborts remaining calls and selects among completed candidates (always-ensemble has no soft throttle, only this backstop).

## 9. Testing

- **Unit:** `pool` resolution incl. availability filtering and the Opus-4.8 change; `select` aggregation (deterministic given fixed `JudgeScore[]`); winner selection + tie-break; worktree create/diff/collect/apply.
- **Integration:** stub `BaseAgent` backends returning canned `AgentResult`s + deterministic stub judges → run the full pipeline end-to-end with **no real LLM calls** (CI-safe, deterministic).
- **Parity:** keep existing `CLAUDE_CODE_PARITY` behaviors green; the REPL still exposes the same slash commands, permissions, MCP, @mentions.
- **Manual E2E (opt-in):** real 4-brand ensemble on a sample repo task; verify per-brand cost accrual to wallets.

## 10. Migration path (B → A) and self-improvement

- The `ensemble/` layer depends only on the `BaseAgent`/`AgentResult` contract. Migrating a vendor driver (e.g., replacing the Gemini CLI wrapper with a native Gemini function-calling loop) is a swap behind that seam — no ensemble changes.
- Prioritize native migration where tight sandbox control matters (enforcing "agents must never touch `judge/`, `hidden_tests/`, locked benchmark files") and where self-improvement requires owning the loop.
- **Self-improvement hook (future):** once drivers are native, the harness source becomes a workspace the ensemble can target — the executor pool proposes harness改进, the judge panel + tests gate them. Out of scope for v1; the seam is the enabler.

## 11. Open questions (resolve during planning)

1. Judge panel membership: `checking` only, or `checking ∪ fast`? (Default: union, fast members as cheap tie-breakers.)
2. Synthesis pass: always run, or only when no candidate dominates? (Default: only when the top two are within a score epsilon.)
3. Per-task token ceiling value and where configured (user config vs per-invocation flag).
4. Repo test/build command discovery for `check_result` (heuristic: `pytest` / `npm test` / project config) — needs a per-workspace override.
5. Worktree count vs. machine resources — cap concurrent executors to CPU budget on small hosts.
