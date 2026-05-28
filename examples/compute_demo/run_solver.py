"""SOTA-grade GPU solver stand-in for the compute demo.

A real provider would run an actual GPU solver here (RDLUF-MixS2, DAUHST,
PnP-HDNet, ...). For a self-contained, dependency-light demo we synthesize
a near-perfect reconstruction from the ground truth so the deterministic
Physics Judge has a passing result to verify. Swap this file for your real
solver on an actual GPU box.

Reads:  data/ground_truth_x.npy   (demo only — a real solver never sees GT)
        data/measurement_y.npy, data/coded_aperture_phi.npy
Writes: results/reconstruction_xhat.npy, results/results.json
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

ws = Path(".")
gt_path = ws / "data" / "ground_truth_x.npy"
if not gt_path.exists():
    raise SystemExit("data/ground_truth_x.npy missing — run generate_data.py first")

gt = np.load(gt_path).astype(np.float64)
# Simulate a strong GPU solver (~38 dB): GT plus small reconstruction error.
xhat = gt + np.random.default_rng(0).normal(0.0, 0.003, size=gt.shape)

(ws / "results").mkdir(exist_ok=True)
np.save(ws / "results" / "reconstruction_xhat.npy", xhat.astype(np.float32))

mse = float(np.mean((gt - xhat) ** 2))
psnr = 10.0 * np.log10(max(gt.max(), 1.0) ** 2 / mse)
(ws / "results" / "results.json").write_text(json.dumps({"PSNR": round(psnr, 2)}))
print(f"solver done: PSNR {psnr:.2f} dB")
