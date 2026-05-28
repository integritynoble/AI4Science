# Find → fix → verify demo (agentic)

A single `ai4science chat` session that audits a PWM submission, fixes the
top issue, and verifies the result — the whole architecture in miniature:

```
physics-reviewer sub-agent  →  FIND a physical inconsistency
main agent (Edit)           →  FIX it
pwm_validate (MCP, no LLM)  →  VERIFY it still conforms
```

The LLM agent does the fast work (review + edit); the **deterministic
checks** confirm conformance — there is no LLM in the verification path.

## Run it

```bash
pip install -e ".[claude]"     # venv active; needs the claude CLI + auth
bash examples/find_fix_verify/run_demo.sh
```

Unlike [`../compute_demo`](../compute_demo) (which is deterministic), this
makes **real LLM calls**, so it needs the `claude` CLI on PATH authed via
`claude login` or `ANTHROPIC_API_KEY`. Output is non-deterministic.

## Why it reliably finds something

The shipped CASSI example (`ai4science/examples/cassi/`) intentionally
contains a physical inconsistency — a `boundary_conditions` of
**"zero-padded reflective"** (those two modes are contradictory: zero-pad
is absorbing, reflective folds spectral energy back) — plus a
tolerance-vs-noise mismatch (`tolerance_epsilon == noise_sigma == 0.01`).
So the physics-reviewer always has a real bug to catch.

## Example run (abridged)

```
⏺ Agent(physics-reviewer)
  ⎿ Blocker: "zero-padded reflective" boundary is physically contradictory…
⏺ Edit(spec.md) ×2
  Replaced "zero-padded reflective" → "zero-padded (absorbing)" in the YAML
  front matter and the six-tuple table.
⏺ mcp__pwm__pwm_validate(.)
  ⎿ {"overall": "ok", ...}
All four artifacts pass after the edit.
```

## What it proves

The agent and sub-agent can find and fix a *real physical* problem, but
the claim that it's fixed is settled by the deterministic validator/judge,
not by the LLM's say-so. That separation — fast LLM editing on top of a
verifiable protocol floor — is the point of AI4Science.

See also:
- [`../compute_demo`](../compute_demo) — wallet-bound GPU compute loop (deterministic)
- [`../../docs/COMPUTE_PROVIDERS_DESIGN.md`](../../docs/COMPUTE_PROVIDERS_DESIGN.md)
