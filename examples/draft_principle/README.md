# Draft-a-contribution demo (agent drafting, L1 → L2)

What the `ai4science` chat agent produces from plain-English prompts — a
complete, schema-valid PWM **L1 Principle** and a matching **L2 Spec**, written
directly to the workspace (not pasted by hand). Both pass `ai4science validate`
(`status: ok`).

## How it was generated

In an empty workspace, a single bare-`ai4science` chat session (Claude Code-like)
with this prompt:

> Draft a new principle.md here for the 1D heat equation (heat diffusion). Use
> the canonical PWM principle field names in the YAML front matter. Keep it tight.

The agent's actual loop (auto-approve on):

```
⏺ Bash(ls .)                  # check the empty workspace
⏺ Write(principle.md)         # draft the artifact
⏺ Bash(ai4science validate)   # exit 1 — caught a schema issue
⏺ Edit(principle.md)          # self-correct
⏺ Bash(ai4science validate)   # passes
```

[`principle.md`](principle.md) is the verbatim result — it passes
`ai4science validate` (`status: ok`, no errors, no warnings).

## Extending into a spec (L2)

A second chat turn, in the same workspace, extends the principle into a concrete
problem instance:

> This workspace has a principle.md for the 1D heat equation. Draft a matching
> spec.md — fill the six-tuple (omega_domain, equations, boundary_conditions,
> initial_conditions, observable, tolerance_epsilon) for a concrete
> heat-diffusion problem instance on [0,1] with Dirichlet BCs. Reference the
> principle. Then run validate.

The agent reads `principle.md`, writes [`spec.md`](spec.md) (a six-tuple with
`parent_principle_id` linking back to the principle, plus a closed-form exact
solution for verification), then `validate → Edit → validate` until both pass.

## Reproduce it

```bash
ai4science                 # bare command → chat session (needs the [claude] extra + claude CLI)
# then type the prompt above, or one-shot:
ai4science "Draft a principle.md for the 1D heat equation. Canonical PWM fields. Tight."
ai4science validate        # confirm it's schema-valid
```

## What it shows

- **The agent acts, not narrates** — it writes the file and validates it, rather
  than printing a draft to copy.
- **Canonical fields** — `artifact_type`, `name`, `domain`,
  `governing_equation_or_operator`, `inputs`, `outputs`, `assumptions`,
  `validity_range`, `known_limitations`, `references`.
- **Self-correction** — a first draft that fails `validate` is fixed in the same
  turn, so what you get is schema-valid.

This covers the first two layers of the four-layer flow (Principle → Spec →
Benchmark → Solution). For the full compute loop, see
[`../compute_demo`](../compute_demo) and [`../gitsync_compute`](../gitsync_compute).
