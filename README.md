# AI4Science CLI

**Open-source contribution tool for Physics World Model (PWM).**

Create, validate, package, and submit Principles, Specs, Benchmarks, and Solutions for verified AI4Science workflows — from your terminal.

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

Requires Python ≥ 3.10.

```bash
git clone https://github.com/integritynoble/AI4Science.git
cd AI4Science
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

For development:

```bash
pip install -e ".[dev]"
pytest
```

## 5. Quickstart

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

## 6. Prompt-first usage

Like `claude` or `codex`, you can invoke `ai4science` with a free-form English prompt in quotes:

```bash
ai4science "Help me create a CASSI spec and benchmark"
ai4science "Validate my PWM contribution and tell me what is missing"
ai4science "Prepare a solution submission for this benchmark"
```

v0.1 routes prompts via a **simple rule-based intent detector** — no LLM yet. Phase A2 will swap the router for a real agent backend (Claude Agent SDK for the contributor role, OpenAI Codex for the Overseer role).

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
