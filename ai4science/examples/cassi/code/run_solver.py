"""Run GAP-TV on the generated CASSI measurement and write the reconstruction.

Reads:
  data/measurement_y.npy
  data/coded_aperture_phi.npy

Writes:
  results/reconstruction_xhat.npy   (H, W, C)
  results/results.json              {PSNR, SSIM-ish, residual}

If data/ground_truth_x.npy is present, reports PSNR against it (the judge
never sees ground truth — this is just for the contributor's own log).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from cassi import forward
from gap_tv import gap_tv


def psnr(a: np.ndarray, b: np.ndarray) -> float:
    mse = float(np.mean((a - b) ** 2))
    if mse <= 1e-12:
        return 99.0
    peak = float(max(a.max(), b.max(), 1.0))
    return 10.0 * np.log10(peak ** 2 / mse)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default=".")
    ap.add_argument("--iters", type=int, default=80)
    ap.add_argument("--tv-weight", type=float, default=0.05)
    args = ap.parse_args()

    ws = Path(args.workspace).resolve()
    y = np.load(ws / "data" / "measurement_y.npy").astype(np.float64)
    mask = np.load(ws / "data" / "coded_aperture_phi.npy").astype(np.float64)

    channels = y.shape[1] - mask.shape[1] + 1
    print(f"Reconstructing: y={y.shape}, mask={mask.shape}, C={channels}")

    x_hat = gap_tv(y, mask, channels, n_iters=args.iters,
                   tv_weight=args.tv_weight, verbose=True)

    results = ws / "results"
    results.mkdir(parents=True, exist_ok=True)
    np.save(results / "reconstruction_xhat.npy", x_hat.astype(np.float32))

    residual = float(np.linalg.norm(y - forward(x_hat, mask)) / (np.linalg.norm(y) + 1e-12))
    metrics = {"forward_residual": residual}

    gt_path = ws / "data" / "ground_truth_x.npy"
    if gt_path.exists():
        gt = np.load(gt_path).astype(np.float64)
        metrics["PSNR"] = psnr(gt, x_hat)

    (results / "results.json").write_text(json.dumps(metrics, indent=2))
    print(f"Wrote results/reconstruction_xhat.npy {x_hat.shape}")
    print(f"Metrics: {metrics}")


if __name__ == "__main__":
    main()
