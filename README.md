# AI4Science CLI

[![PyPI](https://img.shields.io/pypi/v/pwm-ai4science.svg)](https://pypi.org/project/pwm-ai4science/)
[![Python](https://img.shields.io/pypi/pyversions/pwm-ai4science.svg)](https://pypi.org/project/pwm-ai4science/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![CI](https://github.com/integritynoble/AI4Science/actions/workflows/ci.yml/badge.svg)](https://github.com/integritynoble/AI4Science/actions/workflows/ci.yml)

**Open-source contribution tool for Physics World Model (PWM).**

Create, validate, package, and submit Principles, Specs, Benchmarks, and Solutions for verified AI4Science workflows — from your terminal.

**Install (one line, no root / pipx / admin needed):**

```bash
# Linux / macOS
curl -fsSL https://raw.githubusercontent.com/integritynoble/AI4Science/main/install.sh | bash
```
```powershell
# Windows PowerShell
irm https://raw.githubusercontent.com/integritynoble/AI4Science/main/install.ps1 | iex
```

Then run `ai4science --help`. The installer sets up an isolated environment under `~/.ai4science` and puts the `ai4science` command on your PATH — works on locked-down HPC login nodes too. (Once published, `pipx install pwm-ai4science` or `pip install pwm-ai4science` also work.)

---

## 1. What is AI4Science CLI?

`ai4science` is a session-style command-line tool (in the spirit of `claude` or `codex`) that helps you contribute reproducible scientific work to the **Physics World Model (PWM)** protocol. It's the user-facing product layer; PWM is the protocol, registry, and verification layer underneath.

The CLI runs **locally** in v0.1: nothing leaves your machine. You can:

- Create a four-layer contribution (Principle → Spec → Benchmark → Solution) from templates or examples.
- Validate the YAML front matter and required fields with Pydantic.
- Run the **CASSI Physics Judge** locally (deterministic Python, **no LLM in the verdict path**) and get a `judge_report.json`.
- Run a local **Overseer review** that combines validate + judge + claim-vs-results checks + suspicion scans.
- Package your submission into a self-contained `.zip` with a SHA256 certificate.
- Dry-run a submission so you can see exactly what would be sent before going live.

## 2. What is Physics World Model?

PWM is a four-layer protocol for verifiable AI-for-science:

| Layer | Artifact | What it is |
|---|---|---|
| **L1** | **Principle** | A physical law as a first-class registry artifact (e.g. "Beer-Lambert Law for FRET"). |
| **L2** | **Spec** | A formal six-tuple (Ω, E, B, I, O, ε) that fixes a problem instance from the principle. |
| **L3** | **Benchmark** | A reproducible task: dataset + metric + baseline + success threshold. |
| **L4** | **Solution** | A solver / AI-assisted submission against a benchmark, scored deterministically. |

PWM's permanent moat is **not** the LLM, **not** the agent framework, and **not** the UI. It is the eight protocol assets that no replaceable worker can substitute for:

1. `spec.md` format
2. benchmark protocol
3. submission format
4. certificate format
5. deterministic Physics Judge
6. public registry
7. governance rules
8. token / reward economy

Claude Code, OpenAI Codex, Claude Agent SDK, OpenHands, and other agents are **replaceable workers**. They produce drafts; the deterministic Physics Judge produces verdicts.

## 3. Artifact hierarchy

```
L1 Principle  ──anchors→  L2 Spec  ──anchors→  L3 Benchmark  ──hosts→  L4 Solution
```

Each artifact is a Markdown file with a **YAML front-matter block** (between two `---` lines). The front matter is the structured spec validated by `ai4science validate` and consumed by the Physics Judge. The body below the front matter is free prose.

## 4. Installation

One command, global (like `npm install -g` for Claude Code):

```bash
pipx install pwm-ai4science      # → the `ai4science` command
ai4science --help
```

The PyPI package is `pwm-ai4science`; the command is `ai4science` (same package-vs-command split as `@anthropic-ai/claude-code` → `claude`). Plain pip works too: `pip install pwm-ai4science`.

For the chat agent (interactive REPL, sub-agents, MCP): `pipx install "pwm-ai4science[claude]"` and install the `claude` CLI (`claude login` or `ANTHROPIC_API_KEY`).

**Before the first PyPI release**, install from GitHub (still one command):
```bash
pipx install "git+https://github.com/integritynoble/AI4Science.git"
```

From source (to modify / run tests): `git clone … && pip install -e ".[dev]" && pytest`. Full step-by-step for any OS incl. Windows: [`docs/INSTALL.md`](docs/INSTALL.md). Maintainers: [`docs/RELEASING.md`](docs/RELEASING.md).

## 5. Quickstart

**Just like Claude Code, run the bare command to start an interactive session:**

```bash
ai4science          # no arguments → drops you into a chat session (like `claude`)
```

(That needs the chat agent — `pwm-ai4science[claude]` + the `claude` CLI. Without it, `ai4science` prints a short getting-started panel. The deterministic commands below always work, offline.)

```bash
ai4science init cassi-demo          # creates a workspace seeded with the CASSI example
cd cassi-demo
ai4science status                   # show what's in the workspace
ai4science validate                 # parse + Pydantic-validate all four artifacts
ai4science judge cassi --submission .   # run the deterministic Physics Judge
ai4science overseer review --submission .
ai4science package                  # zip + SHA256 certificate
ai4science submit --dry-run         # show what would be submitted
```

After `judge` you'll find `reports/judge_report.json`. After `overseer`, `reports/overseer_report.{md,json}`. After `package`, an `ai4science_submission_<timestamp>.{zip,manifest.json}` pair.

### Interactive REPL chat (Claude Code-like)

For a persistent conversation with the agent — preserves state across follow-ups, supports tool use with confirmation prompts, has slash commands:

```bash
ai4science chat                       # opens a REPL with --agent claude
ai4science chat --read-only           # text-only; no file edits
ai4science chat --yes                 # auto-approve all Edit/Write/Bash
```

Inside the session:

```
ai4science> What does spec.md currently declare for tolerance_epsilon?
[Claude reads the file and answers]

ai4science> Change it to 0.005 and update the table row too
[Claude proposes Edit(s); you confirm y/N for each unless --yes]

ai4science> /validate          # run deterministic validate without leaving
ai4science> /help              # list slash commands
ai4science> /exit              # leave
```

Slash commands: `/help`, `/exit`, `/clear`, `/files`, `/validate`, `/judge`, `/status`, `/cost`. The conversation state and the SDK's Read/Edit/Write/Bash tools are all preserved across turns within a session.

### File @mentions

Reference any file in your workspace by typing `@path/to/file` inside a prompt. The file gets attached (read-only) to that turn, in both chat and one-shot modes:

```bash
# Chat session
ai4science> @code/run_solver.py — what's wrong with this solver?

# One-shot
ai4science --agent claude "@code/run_solver.py what's wrong here?"
```

Sandbox rules: absolute paths (`@/etc/passwd`), traversal (`@../escape`), and references to non-existent files are silently ignored — so writing about the `@property` decorator or someone's `alice@example.com` won't accidentally attach anything.

### Image input

`@`-mention an image file (`.png` `.jpg` `.jpeg` `.gif` `.webp`) in `chat` and the agent sees it — useful for reconstructions, plots, optical diagrams:

```bash
ai4science> @recon.png — what artifacts do you see in this reconstruction?
ai4science> @psnr_curve.png does this look converged?
```

The image is attached as a multimodal content block (text files still inline as before); images over 5 MB are rejected.

### Custom slash commands

Define reusable prompt templates as `<name>.md` files — like Claude Code's `.claude/commands/`. A file becomes `/<name>`:

```
.ai4science/commands/tighten.md     →  /tighten     (project)
~/.config/ai4science/commands/*.md  →  user-global commands
```

`tighten.md`:
```markdown
Edit spec.md to change tolerance_epsilon to $ARGUMENTS (YAML + table row), then re-validate.
```

In a session, `/tighten 0.004` expands the template (substituting `$ARGUMENTS`, or positional `$1`, `$2`…) and sends it as a turn. `/commands` lists what's available; project commands override user-global ones of the same name.

### Plan mode

Sometimes you want a structured plan before any edits happen — what changes, where, in what order, with risks called out. Plan mode runs the agent with read-only tools and a planning-specific system prompt:

```bash
# One-shot plan
ai4science --agent claude --plan "Add a T2 benchmark tier with mild calibration drift"

# Whole-session plan mode in chat
ai4science chat --plan

# Single-turn plan inside a regular chat session
ai4science> /plan refactor the solver to use ADMM instead of GAP-TV
```

In plan mode:
- The agent can `Read` / `Grep` / `Glob` to investigate the workspace.
- The agent **cannot** `Edit`, `Write`, or run `Bash` — the SDK enforces this via `permission_mode="plan"`.
- The system prompt asks for a structured plan with concrete file paths, actions, rationale, and risks.
- The output is a plan you review and approve — then re-run without `--plan` (or follow up in chat) to execute.

When mixing flags, the precedence is **plan > read-only > tool-use** — `--plan` always disables editing regardless of `--yes`.

### Sub-agents

The main agent can delegate focused tasks to specialized PWM sub-agents (via the SDK's `Task` tool). Each sub-agent has its own system prompt and a restricted tool set, so it can't accidentally edit files the main agent didn't ask about.

| Sub-agent | Tools | Job |
|---|---|---|
| `physics-reviewer` | Read, Grep, Glob | Critique a submission for physical realism — noise-model consistency, ε realism, claim plausibility under spec constraints |
| `schema-validator` | Read, Grep, Glob, Edit | Check YAML front matter against canonical PWM schemas and apply minimal-edit fixes for violations only |
| `benchmark-architect` | Read, Grep, Glob | Design a new L3 benchmark tier (T2 / T3 / ...) — produces a plan with success threshold calibrated against existing baselines |

Sub-agents are on by default for `--agent claude`. Disable with `--no-subagents`. The main agent decides when to delegate based on each sub-agent's `description`.

### PWM MCP tools

An in-process MCP server (built with `claude-agent-sdk`'s `create_sdk_mcp_server`) exposes PWM-specific deterministic tools to the agent:

| Tool | Purpose |
|---|---|
| `pwm_validate` | Run the deterministic ai4science validator and return a structured report |
| `pwm_judge_cassi` | Invoke the CASSI Physics Judge and return the same JSON as `reports/judge_report.json` |
| `pwm_status` | Workspace summary (artifacts, dirs, reports, config) |
| `pwm_lookup_artifact` | Read one canonical artifact file (principle / spec / benchmark / solution) with parsed YAML |

All four tools are **deterministic** — no LLM under the hood. The PWM moat is preserved: the agent can _call_ `pwm_judge_cassi`, but it cannot override the judge's output.

MCP is on by default. Disable with `--no-mcp`.

### Multi-tier benchmarks

A single spec can have several benchmark tiers (T1 nominal, T2 mild drift, T3 adversarial...). Each tier is its own benchmark file:

```
my-cassi/
  principle.md
  spec.md
  benchmark.md         # T1 (canonical)
  benchmark_t2.md      # T2
  benchmark_t3.md      # T3
  solution.md
```

Artifacts are discovered by their `artifact_type` front-matter field, not by filename — so all benchmark tiers are picked up automatically:

```bash
ai4science validate                          # validates every tier file
ai4science judge cassi                        # judges benchmark.md (default)
ai4science judge cassi --benchmark benchmark_t2.md   # judges the T2 tier
```

Tier reports are written to `reports/judge_report_<stem>.json` (the canonical `benchmark.md` keeps `reports/judge_report.json`). The `Benchmark` schema has optional `benchmark_id` and `tier` fields so tier metadata has a canonical home. The PWM MCP tools (`pwm_validate`, `pwm_status`, `pwm_judge_cassi`) are all multi-tier aware too.

## 6. Prompt-first usage

Like `claude` or `codex`, you can invoke `ai4science` with a free-form English prompt in quotes:

```bash
ai4science "Help me create a CASSI spec and benchmark"
ai4science "Validate my PWM contribution and tell me what is missing"
ai4science "Prepare a solution submission for this benchmark"
```

Prompt routing is two-tier:

1. **Utility prompts** (validate / judge / package / submit / status / overseer) always dispatch to the deterministic command — an LLM adds nothing, and it costs you nothing. `ai4science "validate my contribution"` just runs `validate`.
2. **Open-ended prompts** (drafting, questions, edits) route to a **real agent**. By default the agent is `auto`: it picks the best available backend in order **claude → codex → none**. So if you have the Claude backend installed (`pip install 'ai4science[claude]'` + `claude login`), a bare `ai4science "draft a CASSI principle"` behaves like `claude "…"`. If no agent is available, it falls back to the rule-based template router.

Override the auto-selection with `--agent claude` / `--agent codex` / `--agent none`, or set `AI4SCIENCE_AGENT`. Utility prompts stay deterministic regardless of agent.

## 7. Template-based usage

If you prefer explicit subcommands:

```bash
ai4science contribute principle    # creates principle.md from template
ai4science contribute spec
ai4science contribute benchmark
ai4science contribute solution
```

Each command writes the template into your CWD (without overwriting) and opens it in `$EDITOR`.

## 8. Validation and CASSI Judge

`ai4science validate` parses the YAML front matter in each artifact and validates it against Pydantic schemas:

- Required fields present
- Correct types
- Front matter well-formed

`ai4science judge cassi` runs four deterministic check families:

| Check | What it verifies | v0.1 behavior |
|---|---|---|
| **S1 — finite specifiability** | `spec.md` exists, well-formed, every required field present and well-typed | pass / fail |
| **S2 — Hadamard stability** | Required physical parameters declared | warning (full proof not encoded in v0.1) |
| **S3 — approximability** | `benchmark.md` declares dataset, metrics, threshold, reproducibility command | pass / fail |
| **S4 — certifiability** | 4 sub-checks: forward residual, noise consistency, Fourier consistency, spatial coherence | pass / fail / warning / not_available |

The judge writes `reports/judge_report.json` and surfaces a `silent_failure` flag when S1 + S3 pass but an S4 check fails — exactly the "looks valid on paper, doesn't physically reproduce" pattern the protocol exists to catch.

**The judge is deterministic Python with no LLM call in the verdict path.** This is a hard rule of the protocol.

## 9. Agent providers: none, Claude, Codex

`ai4science/agents/` ships three pluggable providers:

| Provider | Status | When to use |
|---|---|---|
| `none` | ✅ ships | Default. Prints instructions; no LLM call. |
| `claude` | 🟡 stub | Phase A2 wires Claude Agent SDK (Anthropic family — contributor role) |
| `codex` | 🟡 stub | Phase A2 wires OpenAI Codex CLI (OpenAI family — Overseer role) |

The provider is configurable per workspace via `.ai4science/config.yaml`:

```yaml
agent_provider: none   # 'none' | 'claude' | 'codex'
```

**Hard rule:** AI4Science (contributor) and AI Overseer must use **different LLM families**.

## 10. Security and sandboxing

When an agent provider actually runs (Phase A2+), these rules are non-negotiable:

- Agent workers may edit **only the current contribution workspace**.
- Agents must **not** modify `hidden_tests/`, `judge/`, locked benchmark files, or any parent PWM folders.
- Changed files are surfaced to the user before being accepted.
- **The final scientific decision is never made by the LLM.** It belongs to the deterministic Physics Judge.

## 11. Open source vs. governed by PWM

| Asset | Open source (this repo, MIT) | Governed by PWM protocol |
|---|---|---|
| CLI surface (`ai4science`) | ✅ | — |
| Templates | ✅ | — |
| Pydantic schemas | ✅ | Format is governed; field set is canonical |
| CASSI Physics Judge v0.1 | ✅ | Verdict format is canonical |
| Agent providers (`none`, `claude`, `codex`) | ✅ | — |
| **spec.md / benchmark.md / submission format** | ✅ (reference impl) | **PWM canonical** |
| **certificate format + hash scheme** | ✅ (reference impl) | **PWM canonical** |
| **deterministic Physics Judge** | ✅ (CASSI v0.1) | **PWM canonical (other domains via PWM)** |
| public registry | — | PWM-operated |
| governance rules | — | PWM founders multisig |
| token / reward economy | — | PWM-operated |

You can fork the CLI; you cannot fork the protocol.

## 11b. GPU compute providers (Phase 0)

The agent can dispatch a real solver run to a **wallet-bound GPU provider** and reward it for **verified** work. Design: [`docs/COMPUTE_PROVIDERS_DESIGN.md`](docs/COMPUTE_PROVIDERS_DESIGN.md).

**Why it's safe to use untrusted GPU:** the deterministic Physics Judge re-verifies every result independently (recomputes `A(x_hat)` + the S1–S4 gates). A provider that returns fake or broken results fails S4 → earns nothing. Providers are *verified*, not *trusted*.

```bash
# Bind a GPU provider to a wallet (founder tier)
ai4science compute providers-add \
    --id founder-1-subgpu \
    --wallet 0x… \
    --endpoint ~/.ai4science/compute_jobs --tier founder

ai4science compute providers                      # list
ai4science compute dispatch -p founder-1-subgpu \ # send a job (file-inbox)
    --benchmark L3-003-001-001-T1
ai4science compute status <job_id> -p founder-1-subgpu
ai4science compute verify <job_id> -p founder-1-subgpu   # judge re-verifies → credit
ai4science compute credits                        # verified-job credits per wallet
```

On the **GPU box**, the provider runs the poller, which watches the inbox, runs dispatched solvers, and writes results back:

```bash
# On the sub-GPU host (executes dispatched code — only on a trusted host):
ai4science compute serve -p founder-1-subgpu --allow-exec        # poll forever
ai4science compute serve -p founder-1-subgpu --once --allow-exec  # cron-friendly
```

The poller acks each job, runs its `run_command` (cwd = the job's workspace), computes a content-addressed `certificate_hash` over the reconstruction, and writes `job_<id>.result.json`. Then `compute verify` runs the deterministic judge locally; a **pass** records one verified-job credit bound to the provider's wallet, a **fail** records zero. `--allow-exec` is a required safety gate (the poller refuses to execute dispatched code without it). Credits are unit-less in v1 — the PWM-per-credit conversion and on-chain settlement are platform-owned governance decisions; **the CLI never moves tokens.**

Full loop: `dispatch` (agent) → `serve` (GPU box runs the solver) → `verify` (judge → credit).

**Try it locally (one machine, no GPU, never touches a real remote):**
- [`examples/gitsync_compute`](examples/gitsync_compute) — the full loop with the dispatcher and provider on **separate git clones**, exercising `--git-sync` (the real CPU↔Windows-GPU transport).
- [`examples/compute_demo`](examples/compute_demo) — the same loop in-process (no git), as a single script.

**Setting up a GPU box:** see [`docs/SUBGPU_SETUP_WINDOWS.md`](docs/SUBGPU_SETUP_WINDOWS.md) for a step-by-step Windows + CUDA setup (install, wallet binding, shared-inbox options, Task Scheduler / NSSM service, and a test job).

## 12. Roadmap

**v0.1 (this release)** — local CLI with deterministic CASSI judge + agent stubs.

**v0.2** — Phase A2 agent wiring: ClaudeAgent and CodexAgent call their respective SDKs.

**v0.3** — Real submission flow: `ai4science submit --for-real` with cryptographic signing.

**v0.4** — Additional domain judges (CT reconstruction, fluid dynamics, etc.).

**v1.0** — Stable schema, public registry sync, multi-chain support.

## 13. License

[MIT](LICENSE). The CLI is open source. The PWM **protocol** (registry, governance, judge specifications) is governed separately by the PWM organization.

---

## Companion docs

- [PWM AI4Science Product Strategy (2026-05-27)](https://github.com/integritynoble/pwm/blob/main/pwm-team/plan/Product/PWM_AI4SCIENCE_PRODUCT_STRATEGY_2026-05-27.md)
- [PWM AI Researcher + Overseer Architecture (2026-05-27)](https://github.com/integritynoble/pwm/blob/main/pwm-team/plan/Oversight_Committee/PWM_AI_RESEARCHER_OVERSEER_SYSTEM_2026-05-27.md)
- [Hybrid Path Roadmap (2026-05-27)](https://github.com/integritynoble/pwm/blob/main/pwm-team/plan/Oversight_Committee/PWM_HYBRID_PATH_ROADMAP_2026-05-27.md)
