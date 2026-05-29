---
artifact_type: solution
name: Crank-Nicolson FD Solver — 1D Heat Diffusion
parent_benchmark_id: 1d-heat-diffusion-dirichlet-unit-interval-benchmark
method_name: Crank-Nicolson finite difference
code_path: code/
run_command: |
  python code/generate_data.py
  python code/solver.py --input data/inputs.json --output results/u_pred.npz
  python code/evaluate.py --pred results/u_pred.npz --gt data/exact_solution.npz
environment: |
  Python >= 3.10
  numpy >= 1.24        # numpy >= 2.0 also supported (trapz -> trapezoid handled)
  No other dependencies required.
results_path: results/u_pred.npz
claims:
  - "E_inf = 7.35e-06 (threshold 1e-3; 140x below threshold)"
  - "E_rms = 3.39e-06"
  - "All three physics checks pass: boundary conditions, energy monotone decay, non-negativity"
  - "Runtime < 5 s on a single CPU core (pure NumPy, no GPU required)"
limitations:
  - "Solver is specific to the single-mode IC u(x,0) = sin(pi*x) and zero Dirichlet BCs"
  - "Fixed dt=1e-3; no adaptive time-stepping"
  - "1D only; does not generalise to 2D/3D without rewriting"
  - "Thomas algorithm is serial; not parallelised"
license: MIT
---

# Crank-Nicolson FD Solver — 1D Heat Diffusion

## Method

The solver implements the **Crank-Nicolson (CN) scheme** for the 1D heat equation
on a uniform grid with N = 100 interior intervals (dx = 0.01) and time step
dt = 1e-3.  The scheme is second-order accurate in both space and time, and
unconditionally stable for any r = alpha * dt / dx².  With the chosen parameters,
r = 0.1, far inside the stability margin.

At each time step the CN update solves a tridiagonal system

    (I - r/2 * D) u^{n+1} = (I + r/2 * D) u^n

where D is the standard second-difference operator.  The system is solved with
a pure-NumPy Thomas (LU-tridiagonal) algorithm — no external dependencies
(scipy is not required).  Dirichlet boundary nodes are held at zero throughout
and are excluded from the linear system.

## Reproducibility

All code lives in `code/`; no compiled extensions or external data downloads
are needed.

```bash
# 1. Generate ground-truth data (writes data/)
python code/generate_data.py

# 2. Run the solver (writes results/u_pred.npz)
python code/solver.py --input data/inputs.json --output results/u_pred.npz

# 3. Evaluate (prints metrics and physics checks)
python code/evaluate.py --pred results/u_pred.npz --gt data/exact_solution.npz
```

Requirements: Python >= 3.10, numpy >= 1.24 (numpy 2.x supported).

## Results

Results obtained by running the pipeline above on the benchmark test set
(3 snapshots × 101 grid points, alpha = 0.01, t_out = [0.1, 0.5, 1.0] s).

| Metric | Value | Threshold | Status |
|--------|-------|-----------|--------|
| E_inf (primary) | 7.35 × 10⁻⁶ | ≤ 1 × 10⁻³ | PASS |
| E_rms (diagnostic) | 3.39 × 10⁻⁶ | — | — |

| Physics check | Status |
|---------------|--------|
| Boundary conditions (\|u(0,t)\|, \|u(1,t)\| ≤ 1e-10) | PASS |
| Energy monotone decay | PASS |
| Non-negativity (u ≥ −1e-8) | PASS |
