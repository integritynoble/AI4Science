---
artifact_type: benchmark
name: "TODO: short name for the benchmark"
parent_spec_id: "TODO: L2-XXX of the parent spec"
dataset_description: |
  TODO: source, scale, ground-truth provenance.
data_paths:
  - "data/measurement_y.npy"
  - "data/ground_truth_x.npy"
train_validation_test_split: "TODO: e.g. '70/15/15' or 'fixed splits in data/splits.json'"
metrics:
  - "PSNR"
  - "SSIM"
physics_checks:
  - "S1"
  - "S2"
  - "S3"
  - "S4"
baseline_methods:
  - "TODO: classical baseline (e.g. GAP-TV)"
  - "TODO: learned baseline (e.g. DGSMP)"
success_threshold: "TODO: e.g. 'PSNR >= 25.0 dB on test split'"
reproducibility_command: "TODO: e.g. 'bash code/run_solver.sh'"
---

# {{name}}

## Dataset

TODO: dataset details, link to public source if any.

## Metrics

TODO: metric definitions.

## Baselines

TODO: numerical results table for each baseline.
