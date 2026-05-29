# Draft-a-contribution demo (agent drafting, full L1 → L4 chain)

What the `ai4science` chat agent produces from plain-English prompts — a
complete, schema-valid PWM contribution across **all four layers**: an **L1
Principle**, a matching **L2 Spec**, an **L3 Benchmark**, and an **L4 Solution**
with a *runnable* solver, written directly to the workspace (not pasted by
hand). All four pass `ai4science validate` (`status: ok`), and the solver
beats the benchmark threshold by ~140×.

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

## Extending into a benchmark (L3)

A third turn extends the spec into a runnable benchmark:

> This workspace has principle.md and spec.md for the 1D heat equation on [0,1].
> Draft a matching benchmark.md (L3): dataset_description, data_paths,
> train_validation_test_split, metrics, physics_checks, baseline_methods,
> success_threshold, reproducibility_command. Reference the spec via
> parent_spec_id. The exact solution is the ground truth. Then run validate.

[`benchmark.md`](benchmark.md) links to the spec via `parent_spec_id`, uses the
closed-form solution as analytic ground truth, and defines a primary metric
(`E_inf`), three physics checks tied to the heat equation's maximum principle,
baseline methods with expected errors, and a success threshold matching the
spec's tolerance. (The benchmark is the most field-heavy artifact, so it takes a
few more `validate → Edit` rounds to converge.)

## Completing the chain — a runnable solution (L4)

A fourth turn closes the loop by writing **working solver code** and an L4
solution artifact:

> Complete the chain with an L4 solution: write the solver code the benchmark
> expects (`code/generate_data.py`, `code/solver.py`, `code/evaluate.py`),
> following benchmark.md's reproducibility_command. Run all three and report
> E_inf (must be ≤ 1e-3). Then draft solution.md referencing the benchmark via
> parent_benchmark_id, and run validate.

The agent wrote a pure-NumPy **Crank-Nicolson** solver (Thomas tridiagonal
solve, no SciPy), ran the full `generate_data → solver → evaluate` pipeline,
and self-corrected until it passed. [`solution.md`](solution.md) records the
real measured result, and the code lives in [`code/`](code):

| Metric | Value | Threshold | Status |
|---|---|---|---|
| E_inf (primary) | 7.35 × 10⁻⁶ | ≤ 1 × 10⁻³ | **PASS** (~140× margin) |
| Physics checks (BCs, energy decay, non-negativity) | all PASS | — | — |

The committed `solution.md` claims are not taken on faith — the pipeline is
reproducible (`code/` + the run commands regenerate `data/` and `results/`), and
the deterministic Physics Judge is the actual authority on any submission.

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

This covers the **entire** four-layer flow (Principle → Spec → Benchmark →
Solution), every artifact agent-drafted and schema-valid, ending in a runnable
solver that beats the benchmark. For the GPU-compute loop, see
[`../compute_demo`](../compute_demo) and [`../gitsync_compute`](../gitsync_compute).

## Files

| Path | Layer | Role |
|---|---|---|
| `principle.md` | L1 | the physical law (1D heat equation) |
| `spec.md` | L2 | concrete six-tuple instance on [0,1], Dirichlet BCs |
| `benchmark.md` | L3 | dataset, metrics, physics checks, baselines, threshold |
| `solution.md` | L4 | Crank-Nicolson solver submission + measured results |
| `code/` | — | runnable solver (`generate_data.py`, `solver.py`, `evaluate.py`) |

`data/` and `results/` are **not** committed — they're regenerated by `code/`.
