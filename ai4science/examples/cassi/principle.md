---
artifact_type: principle
name: "Coded Aperture Snapshot Spectral Imaging (CASSI)"
domain: "Computational Imaging / Hyperspectral"
governing_equation_or_operator: "y = Phi x + n, where Phi is a coded-aperture + dispersion operator R^{H x W x C} -> R^{H x (W + C - 1)}"
inputs:
  - "Hyperspectral data cube x in R^{H x W x C}"
  - "Coded aperture pattern Phi"
outputs:
  - "Single 2D coded snapshot y in R^{H x (W + C - 1)}"
assumptions:
  - "Linear shift-invariant dispersion model"
  - "Spectral channels are spatially aligned before dispersion"
  - "Additive Gaussian noise"
validity_range: "Visible to near-IR (450-700 nm typical), spatial resolution >= 256 x 256, 28-31 spectral channels"
known_limitations:
  - "Strong spectral correlation in natural scenes is required for high-quality reconstruction"
  - "Calibration drift of Phi degrades performance"
references:
  - "Wagadarikar et al. (2008), Applied Optics 47(10):B44–B51, doi:10.1364/AO.47.000B44"
  - "Meng et al. (2020), TPAMI 43(10):3447-3461"
---

# Coded Aperture Snapshot Spectral Imaging (CASSI)

## Physical meaning

CASSI captures a hyperspectral data cube `x` in a single 2D snapshot `y`
by multiplexing spectral channels through a coded aperture and a
dispersive element. Reconstruction recovers `x` from `y` by solving the
underdetermined linear inverse problem `y = Phi x + n`.

## Mathematical statement

Forward operator: `Phi : R^{H x W x C} -> R^{H x (W + C - 1)}`.
The reconstruction problem is `argmin_x  ||y - Phi x||_2^2 + lambda R(x)`
for some prior `R` (TV, learned, plug-and-play, etc.).

## Why this matters

Anchors L2 specs that fix `H, W, C` and the noise model, which in turn
anchor L3 benchmarks with concrete datasets.

## References

See front matter.
