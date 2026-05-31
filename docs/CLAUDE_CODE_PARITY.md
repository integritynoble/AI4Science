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
- **Plan 3b** — sub-agents (`Task` tool) + MCP servers (incl. PWM MCP)
- **Plan 3c** — `@mentions` + image input
- **Plan 3d (DONE 2026-05-31)** — hardening: ✅ hard wall-clock bash timeout (reader thread +
  process-group kill, so a `sleep 1000`-style hang is killed promptly, not orphaned);
  ✅ bash-command sandbox guard (blocks `judge/`/`hidden_tests/`/parent-escape refs, incl.
  `;|&`-chained, even in auto-yes); ✅ Anthropic input-token metering (from `message_start`);
  ✅ loop-cap truncation signal; ✅ multi/parallel tool-call adapter coverage.
  Out of scope (future): OS-level bash isolation (bubblewrap/chroot) — the cmd guard is
  heuristic, not airtight against deliberate obfuscation — and real recorded provider stream
  fixtures (need live API creds; CI uses synthetic streams).
