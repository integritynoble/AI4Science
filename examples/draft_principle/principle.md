---
artifact_type: principle
name: 1D Heat Equation (Fourier Diffusion)
domain: thermodynamics / continuum mechanics
governing_equation_or_operator: |
  ∂u/∂t = α ∂²u/∂x²

  where u(x,t) is temperature [K], x ∈ Ω ⊆ ℝ, t ≥ 0,
  and α = k / (ρ cₚ) is thermal diffusivity [m²/s]
  (k = thermal conductivity, ρ = density, cₚ = specific heat capacity).
inputs:
  - "u(x, 0): initial temperature field over the domain"
  - "boundary conditions: Dirichlet (fixed T), Neumann (fixed flux ∂u/∂x), or Robin"
  - "alpha: thermal diffusivity [m²/s] — a positive scalar for homogeneous media"
outputs:
  - "u(x, t): temperature field at all subsequent times"
assumptions:
  - Medium is homogeneous and isotropic (constant α)
  - No internal heat generation (source term q = 0)
  - Continuum hypothesis holds
  - Material properties (k, ρ, cₚ) are temperature-independent
  - 1D geometry — lateral heat losses neglected
validity_range: |
  - Spatial scale >> mean free path of heat carriers (continuum regime)
  - Time scale >> phonon relaxation time (Fourier regime; not hyperbolic)
  - Temperature gradients mild enough that property variation is negligible
  - Applicable to rods, slabs, and thin films where transverse dimensions are
    much smaller than the longitudinal scale
known_limitations:
  - Fails at nanoscale or ultrafast (femtosecond) regimes where the
    hyperbolic (Cattaneo–Vernotte) equation is needed
  - Does not capture anisotropic or heterogeneous conductivity without extension
  - No radiation or convection coupling
  - Infinite propagation speed of thermal disturbances (parabolic PDE artifact)
references:
  - "Fourier, J.-B.-J. (1822). Théorie analytique de la chaleur."
  - "Carslaw, H.S. & Jaeger, J.C. (1959). Conduction of Heat in Solids, 2nd ed. Oxford."
  - "Evans, L.C. (2010). Partial Differential Equations, 2nd ed. AMS. §2.3"
---

# 1D Heat Equation — Principle

The **1D heat equation** describes temperature diffusion along a one-dimensional
domain under Fourier's law of heat conduction.  It is the prototypical parabolic
PDE and the basis for a wide class of diffusion benchmarks in PWM.

## Governing equation

```
∂u/∂t = α ∂²u/∂x²,    x ∈ [x₀, x₁],  t > 0
```

`α > 0` is the **thermal diffusivity**; larger α means faster spreading.

## Canonical problem setup

| Element | Typical choice |
|---|---|
| Domain Ω | [0, L], L in metres |
| IC | u(x,0) = u₀(x), arbitrary smooth profile |
| BC (Dirichlet) | u(0,t) = T_L,  u(L,t) = T_R |
| BC (Neumann) | ∂u/∂x\|₀ = 0,  ∂u/∂x\|_L = 0 (insulated) |
| Observable | u(x,t) or integrated energy ∫u dx |

## Key analytic results

- **Fundamental solution** (whole line):  
  `G(x,t) = (4παt)^{-1/2} exp(−x²/(4αt))`
- **Steady state** (Dirichlet BCs): linear profile `u_∞(x) = T_L + (T_R−T_L)·x/L`
- **Separation of variables** gives eigenfunction expansion with decay rates  
  `exp(−α λₙ² t)`, `λₙ = nπ/L`
