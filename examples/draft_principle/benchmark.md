---
artifact_type: benchmark
name: 1D Heat Diffusion — Dirichlet Unit Interval Benchmark
parent_spec_id: 1d-heat-diffusion-unit-interval-dirichlet-bcs
dataset_description: |
  Analytically generated dataset derived from the exact solution
    u(x, t) = exp(−α π² t) sin(π x),  α = 0.01 m²/s.
  Inputs: uniform spatial grid x_i = i/N, N = 100 (101 points including endpoints),
  output times t ∈ {0.1, 0.5, 1.0} s.
  Ground-truth arrays are computed by code/generate_data.py and stored as NPZ.
  No external data source required — the benchmark is fully reproducible from the
  closed-form solution.
data_paths:
  - data/exact_solution.npz    # ground truth: arrays x (101,), t_out (3,), u_exact (3×101)
  - data/inputs.json           # inputs: alpha, N, t_out
train_validation_test_split: |
  Not applicable — there is no learned model split.
  The dataset contains a single deterministic test set (3 output snapshots × 101 grid
  points). Solvers are evaluated solely on this test set; no training data is provided.
metrics:
  - "E_inf [primary]: max_{i,t} |u_predicted(x_i, t) − u_exact(x_i, t)|  [K]"
  - "E_rms [diagnostic]: sqrt(mean_{i,t} (u_predicted − u_exact)²)  [K]"
physics_checks:
  - "boundary_conditions: |u_predicted(0,t)| ≤ 1e-10 and |u_predicted(1,t)| ≤ 1e-10 for all t_out"
  - "energy_monotone_decay: ∫₀¹ u(x,t) dx non-increasing in time (max principle, slack 1e-12)"
  - "non_negativity: u_predicted(x,t) ≥ −1e-8 for all x,t (maximum principle)"
baseline_methods:
  - "Forward Euler FD: Δx=0.01, Δt=4e-5 (r≈0.4); expected E_inf ~5e-3"
  - "Crank–Nicolson FD: Δx=0.01, Δt=1e-3 (unconditionally stable); expected E_inf ~2e-5"
  - "Oracle (exact formula): u=exp(−α π² t)sin(π x); E_inf = 0"
success_threshold: |
  E_inf ≤ 1.0e-3   (matches spec tolerance_epsilon)
  AND all three physics_checks pass.
reproducibility_command: |
  # 1. Generate ground-truth data
  python code/generate_data.py

  # 2. Run solver (replace with submission entry-point)
  python code/solver.py --input data/inputs.json --output results/u_pred.npz

  # 3. Evaluate
  python code/evaluate.py --pred results/u_pred.npz --gt data/exact_solution.npz
---

# Benchmark — 1D Heat Diffusion on Unit Interval

L3 benchmark derived from
[1D Heat Diffusion on Unit Interval with Dirichlet BCs](spec.md).

## Dataset

The ground truth is the closed-form solution
`u(x, t) = exp(−α π² t) sin(π x)` at three snapshots
(t = 0.1, 0.5, 1.0 s) on a uniform 101-point grid.
Run `python code/generate_data.py` to produce `data/exact_solution.npz`.

## Metrics

| Metric | Role |
|---|---|
| E_inf = max\|u_pred − u_exact\| | **Primary** — must be ≤ 1 × 10⁻³ |
| E_rms | Diagnostic |

## Physics checks

All three must pass:
1. BCs satisfied to 1 × 10⁻¹⁰
2. Energy monotonically non-increasing
3. Non-negativity (maximum principle)

## Baselines

| Method | Expected E_inf |
|---|---|
| Forward Euler (Δx=0.01, Δt=4×10⁻⁵) | ~5 × 10⁻³ |
| Crank–Nicolson (Δx=0.01, Δt=10⁻³) | ~2 × 10⁻⁵ |
| Oracle (exact formula) | 0 |

## Success threshold

**E_inf ≤ 1 × 10⁻³** and all physics checks pass.
