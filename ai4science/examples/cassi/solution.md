---
artifact_type: solution
name: "GAP-TV baseline for CASSI-256x256x28 T1"
parent_benchmark_id: "L3-025-001-001-T1"
method_name: "GAP-TV"
code_path: "code/"
run_command: "python code/run_solver.py --config code/config.yaml"
environment: "code/environment.yml"
results_path: "results/"
claims:
  - "PSNR = 21.5 dB averaged across test split"
  - "SSIM = 0.55 averaged across test split"
  - "Wall-clock < 60 s per scene on a single CPU"
limitations:
  - "Classical TV prior under-smooths edges in high-frequency regions"
  - "60 iterations was tuned for this configuration; not adaptive"
license: "MIT"
---

# GAP-TV baseline for CASSI-256x256x28 T1

## Method

Generalized Alternating Projection (GAP) iteration with a Total-Variation
proximal step. 60 outer iterations; TV-prox uses Chambolle-Pock with 5
inner iterations.

## Reproducibility

`python code/run_solver.py --config code/config.yaml`

## Results

| Metric | Value |
|---|---|
| PSNR (mean, test split) | 21.5 dB |
| SSIM (mean, test split) | 0.55 |
