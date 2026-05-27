---
artifact_type: spec
name: "CASSI Reconstruction (256x256x28, KAIST-like)"
parent_principle_id: "L1-025"
domain: "Computational Imaging / Hyperspectral"
problem_statement: |
  Reconstruct a hyperspectral data cube x in R^{256 x 256 x 28} from a
  single 2D coded snapshot y in R^{256 x 283} given the calibrated
  coded-aperture operator Phi.
omega_domain: "x in R^{256 x 256 x 28}, y in R^{256 x 283}"
equations:
  - "y = Phi(x) + n, n ~ N(0, sigma^2 I)"
  - "Phi is a known, calibrated linear operator"
boundary_conditions: "Spatial: zero-padded reflective boundary in coded-aperture mask"
initial_conditions: "x_0 = Phi^T y (matched filter initialization)"
observable: "y = Phi x + n, y in R^{256 x 283}"
noise_sigma: 0.01
tolerance_epsilon: 0.01
input_format: "y: numpy .npy float32 of shape (256, 283)"
output_format: "x_hat: numpy .npy float32 of shape (256, 256, 28)"
---

# CASSI Reconstruction (256x256x28, KAIST-like)

## Problem

Recover the hyperspectral cube `x` from a single coded snapshot `y`.

## Six-tuple summary

| Element | Value |
|---|---|
| Ω (domain) | `R^{256 x 256 x 28}` |
| E (equations) | `y = Phi x + n` |
| B (boundary) | zero-padded reflective |
| I (initial) | matched-filter `Phi^T y` |
| O (observable) | `y in R^{256 x 283}` |
| ε (tolerance) | 0.01 |
