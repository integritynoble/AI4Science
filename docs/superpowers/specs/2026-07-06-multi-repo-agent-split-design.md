# PWM Agents as Independent, Composable Repos — Design

**Date:** 2026-07-06
**Status:** Approved design, ready for implementation planning
**Scope:** Split each PWM agent out of the monolithic AI4Science repo into its own
GitHub repo. Each agent is installable and usable standalone (like AI4Science
itself), embeddable back into AI4Science, and cross-callable from sibling agents.
AI4Science becomes the framework that combines them and is itself one agent.

---

## 1. Problem & goals

Today all agents live as builtin specs inside one repo
(`integritynoble/AI4Science`, `ai4science/harness/agents/specs/*.py`) running on a
shared harness runtime (`ai4science/harness/…` + vendored `pwm_core`). There is
already a plugin standard (`PLUGIN_STANDARD.md`) for external manifest+MCP agents,
and runtime cross-calling via `_agent_dispatch_tool`.

We want each first-party agent to become an **independent GitHub repo** that:

1. Installs and runs **standalone**, exactly like AI4Science today
   (`curl | bash` installer, `login`, a TUI/CLI), scoped to that one agent.
2. **Embeds into AI4Science** with zero glue — installing the package makes the
   agent appear in AI4Science automatically.
3. Is **cross-callable** from sibling agents (agent A can dispatch to agent B).
4. Shares **one runtime** and **one PWM identity** with every other agent so there
   is no code drift and no repeated login.

AI4Science stops being the container of all agents and becomes the **framework**
that depends on them all, plus its own meta-agent that combines them.

## 2. Non-goals

- No change to the existing external plugin path (JSON/TOML manifest + MCP server).
  It stays supported alongside the new entry-point path so current contributors
  are not broken.
- No auto-install-on-demand and no remote/hosted dispatch. Cross-calling is
  **local-only**: an agent can call whatever sibling packages are installed in the
  same environment (with an install hint when one is missing).
- The plain `claude_code` / `codex` passthrough modes (no GPU, no PWM) do **not**
  get their own repos; they remain in the AI4Science framework.

## 3. Architecture

```
pwm-agent-core        ← the harness, as an installable library (no agents, no top-level CLI)
        ▲
        │ depends on
   ┌────┼──────────────────────────────────────────────────────┐
   │    │        │       │        │      │       │        │      │
 unified research paper imaging  drug  cancer claude-gpu codex-gpu   ← 8 agent packages
   each: one AgentSpec + prompts + tools + a console entrypoint
        ▲
        │ depends on all 8 agent packages
   AI4Science (pwm-ai4science)  ← the framework: core + every agent + an "ai4science" meta-agent
                                  + the plain claude_code/codex passthrough modes
```

### 3.1 `pwm-agent-core` (shared runtime library)

Owns everything generic, extracted from today's `ai4science/harness` + `pwm_core`:

- The Claude-Code tool base (fs read/write/edit/grep/glob, bash), MCP client.
- LLM routing / backends / pricing / execute / ledger.
- `login`, wallet, PWM billing (single credential store — see §6).
- The TUI (`prompt_toolkit` full-screen + inline) and the base CLI.
- `AgentSpec` (dataclass, unchanged from today), the registry, and discovery (§4).
- The cross-call dispatch tool (`_agent_dispatch_tool`) and its tier gating
  (`_can_dispatch`).
- **GPU compute plumbing** (`compute serve --http`, provider-wallet job dispatch)
  — a core capability available to every agent (§7).

Core ships **no agents of its own** and exposes **no top-level user command**; it is
a library other packages boot.

### 3.2 Agent packages (8)

Each is small and uniform: one `AGENT = AgentSpec(...)`, its system prompt, its
domain tools, a console-script entrypoint, an `install.sh`, and a `pyproject.toml`
that depends on `pwm-agent-core>=X,<Y` and advertises its spec (§4).

| Agent | Repo | pip package | CLI command |
|---|---|---|---|
| shared runtime | `pwm-agent-core` | `pwm-agent-core` | — (library) |
| unified LLM | `pwm-agent-unified` | `pwm-agent-unified` | `pwm-unified` |
| research | `pwm-agent-research` | `pwm-agent-research` | `pwm-research` |
| paper | `pwm-agent-paper` | `pwm-agent-paper` | `pwm-paper` |
| computational imaging | `pwm-agent-imaging` | `pwm-agent-imaging` | `pwm-imaging` |
| drug design | `pwm-agent-drug` | `pwm-agent-drug` | `pwm-drug` |
| cancer | `pwm-agent-cancer` | `pwm-agent-cancer` | `pwm-cancer` |
| Claude Code + GPU | `pwm-agent-claude-gpu` | `pwm-agent-claude-gpu` | `pwm-claude-gpu` |
| Codex + GPU | `pwm-agent-codex-gpu` | `pwm-agent-codex-gpu` | `pwm-codex-gpu` |
| framework | `AI4Science` (existing) | `pwm-ai4science` | `ai4science` |

All repos under the `integritynoble` org.

### 3.3 AI4Science framework

Depends on core + all 8 agent packages. Adds:

- An `ai4science` meta-agent spec — the "combine them all" agent that can dispatch
  to every installed sibling. AI4Science is therefore *itself one agent* as well as
  the framework.
- The plain `claude_code` / `codex` passthrough modes (no GPU, no PWM).

Because the 8 agents are dependencies, a fresh AI4Science install has all of them
present, so cross-calling is always complete inside the framework.

## 4. Discovery interface

Each agent package advertises its spec through a Python entry point:

```toml
# in each agent repo's pyproject.toml
[project.entry-points."pwm_agent.specs"]
research = "pwm_agent_research:AGENT"
```

At startup, core's registry loads, in order:

1. Any builtin specs shipped with the runner (framework only).
2. **Every `pwm_agent.specs` entry point** discovered in the current environment
   (`importlib.metadata.entry_points`).
3. Plugin manifests (the existing JSON/TOML plugin path — unchanged).

"Installed = available." This generalizes today's `_SPECS_DIR` directory scan; the
`AgentSpec` dataclass is unchanged, it simply lives in core now. Adding an agent
requires editing no central list — publish the package and it appears.

## 5. Standalone use

Installing one agent yields a dedicated command that boots the shared runtime
pinned to that agent. Example for the research agent (the pattern is identical for
every agent — `pwm-imaging`, `pwm-codex-gpu`, …):

```bash
curl -fsSL https://raw.githubusercontent.com/integritynoble/pwm-agent-research/main/install.sh | bash
pwm-research login       # shared ~/.ai4science credentials (single PWM identity)
pwm-research             # opens the same TUI, defaulted to the research agent
```

`pwm-<agent>` is a thin wrapper over core's existing CLI/TUI with `--agent <name>`
as the default. Login, wallet, backends, and TUI are all core's, so standalone use
behaves exactly like AI4Science but scoped to one agent. The dispatch list for a
standalone agent = whatever sibling agent packages are also installed in that
environment.

## 6. Login & identity

All agents — standalone or inside AI4Science — read/write the **same** credential
and wallet store (`~/.ai4science` / `~/.config/ai4science`), which lives in core.
Log in once from any agent (or from AI4Science) and every agent on the machine is
authenticated against the same single PWM wallet and billing account. No per-agent
credentials.

## 7. GPU compute (a core capability)

GPU compute lives in `pwm-agent-core` and is available to **every** agent
(research, imaging, drug, cancer, unified, paper — all can request GPU jobs via the
`compute serve --http` / provider-wallet loop). GPU is **not** exclusive to any
repo.

The `claude-gpu` and `codex-gpu` repos exist purely to **disambiguate from the
original Claude Code and Codex**, which do not support GPU:

- Plain `claude_code` / `codex` (in the framework) = faithful passthrough to the
  official tools, no GPU, no PWM — matching how Anthropic/OpenAI ship them.
- `pwm-agent-claude-gpu` / `pwm-agent-codex-gpu` = the PWM versions that add GPU
  compute and PWM billing on top of the same Claude Code / Codex experience.

So `+GPU` is a **label signalling "this variant has GPU, unlike the original,"** not
a claim that GPU is unique to these two. Every other agent supports GPU without
`+GPU` in its name, because for them GPU is simply expected.

## 8. Cross-calling (local-only, graceful, with hints)

The existing `_agent_dispatch_tool` builds a Task tool over `dispatchable_targets`.
Post-split, targets = every installed agent whose entry point is present and whose
tier permits dispatch (`_can_dispatch` unchanged: `open` callable by all; `science`
callable only by `science`). Dispatching to an agent that is **not** installed
returns a hint:

```
research agent not installed — run: pip install pwm-agent-research
```

Inside AI4Science all 8 are dependencies, so cross-calling is seamless there.
Standalone, it works for whatever sibling packages you have added.

## 9. Versioning & compatibility contract

`pwm-agent-core`'s public surface — the `AgentSpec` dataclass, the registry /
discovery API, the dispatch tool, the login/wallet API, and the compute-client API
— is the **versioned interface**. Each agent package pins `pwm-agent-core>=X,<Y`.
Breaking that surface is a minor-version bump on core and a coordinated pin bump on
the agents.

## 10. Migration phases

Extract-in-place, core first. Each phase is independently shippable and leaves a
working system.

### Phase 1 — Core extraction
Draw the `pwm-agent-core` boundary inside the existing repo (harness + `pwm_core` +
compute plumbing + login/wallet + registry/discovery), publish it as a package, and
make AI4Science depend on it. Prove AI4Science still runs identically on the
extracted core. Nothing user-visible changes.

### Phase 2 — Pilot agent end-to-end (`research`)
Split `research` into `pwm-agent-research` first — the flagship science agent,
which exercises the hardest paths: `tier=science` moat, PWM registry read tools,
login/billing, the standalone CLI, embed-back-into-AI4Science via entry point, and
cross-call in both directions. Acceptance:

- `pwm-research` installs, logs in, and runs standalone.
- AI4Science still resolves `research` via its entry point (unchanged UX).
- Cross-call works both ways; missing-sibling install hint fires when a target is
  absent.

### Phase 3 — Split the rest
Repeat the proven Phase-2 pattern for `paper`, `imaging`, `drug`, `cancer`,
`unified`, `claude-gpu`, `codex-gpu`. Each is a mechanical repeat once the pilot
validates the pattern.

## 11. Testing strategy

- **Core:** unit tests for registry discovery (builtin + entry-point + plugin
  layers), dispatch gating, login/wallet, and the compute client.
- **Per agent:** an entry-point discovery test (spec loads from the installed
  package), a standalone-boot smoke test, and the agent's own domain-tool tests.
- **Integration (framework):** assert all 8 entry points resolve and the cross-call
  target set is complete; a "one-agent-only" environment test asserting graceful
  missing-sibling hints.
- **Compatibility:** a test that agents pin a core version range satisfied by the
  published core.

## 12. Open items to confirm during planning

- Exact module/package layout of `pwm-agent-core` (namespace: keep `ai4science` for
  back-compat imports, or new top-level `pwm_agent_core`? Recommend a compatibility
  shim so existing imports keep working during migration).
- Whether the standalone installers vendor a pinned core or always pull the latest
  compatible core.
- Where per-agent repos live relative to the shared memory / CI (org-level reusable
  workflow for install+test).
```
