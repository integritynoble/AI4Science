---
artifact_type: spec
name: "CASSI Reconstruction (32x32x8 synthetic)"
parent_principle_id: "L1-025"
domain: "Computational Imaging / Hyperspectral"
problem_statement: |
  Reconstruct a hyperspectral data cube x in R^{32 x 32 x 8} from a
  single 2D coded snapshot y in R^{32 x 39} given the calibrated
  sheared coded-aperture operator A (SD-CASSI).
omega_domain: "x in R^{32 x 32 x 8}, y in R^{32 x 39}"
equations:
  - "y = A(x) + n, n ~ N(0, sigma^2 I)"
  - "A is a sheared coded-aperture operator: y[:, c:c+W] += (x[:,:,c] * mask); y has width W + C - 1"
boundary_conditions: "Spatial: mask applied per channel; spectral shear by channel index"
initial_conditions: "x_0 = A^T y (adjoint / matched-filter initialization)"
observable: "y = A(x) + n, y in R^{32 x 39}"
noise_sigma: 0.01
tolerance_epsilon: 0.01
input_format: "y: numpy .npy float32 of shape (32, 39); mask: numpy .npy of shape (32, 32)"
output_format: "x_hat: numpy .npy float32 of shape (32, 32, 8)"
---

# CASSI Reconstruction (32x32x8 synthetic)

## Problem

Recover the hyperspectral cube `x` of shape `(32, 32, 8)` from a single coded
snapshot `y` of shape `(32, 39)` produced by the sheared coded-aperture operator
`A` and a binary mask of shape `(32, 32)`.

## Forward model

`A` maps `x:(H,W,C)` and `mask:(H,W)` to `y:(H, W+C-1)` by masking each channel and
summing with a one-pixel-per-channel spectral shear: `y[:, c:c+W] += x[:,:,c] * mask`.
Here `H=W=32`, `C=8`, so `y` has width `32 + 8 - 1 = 39`.

## Inputs / outputs

| Path | Shape | Meaning |
|---|---|---|
| `data/measurement_y.npy` | `(32, 39)` | coded snapshot `y` |
| `data/coded_aperture_phi.npy` | `(32, 32)` | binary mask |
| `results/reconstruction_xhat.npy` | `(32, 32, 8)` | your reconstruction `x_hat` |

## Six-tuple summary

| Element | Value |
|---|---|
| Ω (domain) | `x in R^{32 x 32 x 8}`, `y in R^{32 x 39}` |
| E (equations) | `y = A(x) + n` |
| B (boundary) | per-channel mask + spectral shear |
| I (initial) | adjoint `A^T y` |
| O (observable) | `y in R^{32 x 39}` |
| ε (tolerance) | 0.01 |
