---
artifact_type: solution
name: "TODO: short name for your solver / method"
parent_benchmark_id: "TODO: L3-XXX of the parent benchmark"
method_name: "TODO: e.g. 'PnP-DnCNN', 'GAP-TV', 'HDNet'"
code_path: "code/"
run_command: "TODO: e.g. 'python code/run_solver.py --config code/config.yaml'"
environment: "code/environment.yml"
results_path: "results/"
claims:
  - "TODO: e.g. 'PSNR = 28.4 dB on test split'"
  - "TODO: e.g. 'wall-clock < 30 s on single A100'"
limitations:
  - "TODO: limitation 1"
license: "MIT"
---

# {{name}}

## Method

TODO: 1-2 paragraphs explaining the solver.

## Reproducibility

TODO: how to run from a clean checkout. Reference `run_command` and `environment`.

## Results

TODO: numerical results vs. each metric in the benchmark.
