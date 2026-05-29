---
artifact_type: spec
name: 1D Heat Diffusion on Unit Interval with Dirichlet BCs
parent_principle_id: 1d-heat-equation-fourier-diffusion
domain: thermodynamics / continuum mechanics
problem_statement: |
  Solve the 1D heat equation on the unit interval [0, 1] with fixed-temperature
  Dirichlet boundary conditions and a sinusoidal initial condition. The exact
  solution is known analytically, enabling rigorous numerical verification.
omega_domain: |
  x ∈ [0, 1]  (length L = 1 m)
  t ∈ [0, 1]  (s)
equations:
  - "∂u/∂t = α ∂²u/∂x²"
  - "α = 0.01  [m²/s]"
boundary_conditions: |
  Dirichlet:
    u(0, t) = 0   for all t ≥ 0
    u(1, t) = 0   for all t ≥ 0
initial_conditions: |
  u(x, 0) = sin(π x)   for x ∈ [0, 1]

  Exact solution: u(x, t) = exp(−α π² t) sin(π x)
observable: |
  Pointwise temperature field u(x, t) evaluated on a uniform grid
  x_i = i/N, i = 0, …, N  at output times t ∈ {0.1, 0.5, 1.0} s.
  Primary comparison quantity: max-norm error
    E_∞ = max_{i,t} |u_predicted(x_i, t) − u_exact(x_i, t)|
tolerance_epsilon: 1.0e-3
input_format: |
  alpha: float        # thermal diffusivity [m²/s]
  N: int              # number of spatial grid points (excluding endpoints)
  t_out: list[float]  # output times [s]
output_format: |
  u: array of shape (len(t_out), N+1)  # temperature field at each output time
---

# Spec — 1D Heat Diffusion on Unit Interval

Concrete problem instance derived from the
[1D Heat Equation (Fourier Diffusion)](principle.md) principle.

## Problem summary

| Field | Value |
|---|---|
| Domain Ω | x ∈ [0, 1], t ∈ [0, 1] |
| Diffusivity α | 0.01 m²/s |
| BCs | u(0,t) = u(1,t) = 0 (Dirichlet) |
| IC | u(x,0) = sin(πx) |
| Observable | u(x,t) on uniform grid; max-norm vs. exact |
| Tolerance ε | 1 × 10⁻³ |

## Exact solution

Because the IC is a single Fourier mode, the solution is closed-form:

```
u(x, t) = exp(−α π² t) sin(π x)
```

This allows exact evaluation of the error without a reference solver.

## Rationale for choices

- **α = 0.01**: diffusion time-scale ~L²/α = 100 s; at t = 1 s the mode has
  decayed by factor exp(−0.01 π²) ≈ 0.906, giving a non-trivial but
  well-conditioned test.
- **Zero Dirichlet BCs**: preserve the single-mode structure and suppress
  Gibbs artefacts.
- **ε = 1 × 10⁻³**: achievable with a modest finite-difference solver
  (e.g. Crank–Nicolson, Δx = 0.01, Δt = 0.001) while filtering trivial submissions.
