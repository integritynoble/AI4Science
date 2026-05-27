---
artifact_type: spec
name: "TODO: short name for the formal problem statement"
parent_principle_id: "TODO: L1-XXX of the parent principle"
domain: "TODO: e.g. 'Computational Imaging'"
problem_statement: |
  TODO: 1-2 paragraphs. State the inverse / forward problem in plain English.
omega_domain: "TODO: e.g. '256x256x28 hyperspectral cube, x in R^{256x256x28}'"
equations:
  - "TODO: governing equation 1"
  - "TODO: governing equation 2"
boundary_conditions: "TODO: e.g. 'periodic in spatial dimensions'"
initial_conditions: "TODO: e.g. 'zero initial reconstruction'"
observable: "TODO: e.g. 'y = Phi x + n where Phi is the coded aperture'"
tolerance_epsilon: 1.0e-3
input_format: "TODO: e.g. 'numpy .npy float32 of shape (256,256)'"
output_format: "TODO: e.g. 'numpy .npy float32 of shape (256,256,28)'"
---

# {{name}}

## Problem

TODO: full mathematical formulation.

## Six-tuple summary

| Element | Value |
|---|---|
| Ω (domain) | TODO |
| E (equations) | TODO |
| B (boundary) | TODO |
| I (initial) | TODO |
| O (observable) | TODO |
| ε (tolerance) | TODO |
