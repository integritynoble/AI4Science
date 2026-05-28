"""Synthesize a small CASSI scene: ground-truth cube, coded aperture, measurement.

Writes into the workspace ``data/`` directory:
  ground_truth_x.npy      (H, W, C)  float32 in [0, 1]
  coded_aperture_phi.npy  (H, W)     binary {0, 1}
  measurement_y.npy       (H, W+C-1) float32, = A(x) + N(0, sigma^2)

This is a synthetic stand-in for real KAIST-like hyperspectral data so
the full pipeline (solve → judge S4) runs end-to-end without a large
download. Scale is small (32x32x8) for fast iteration.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from cassi import forward

H, W, C = 32, 32, 8
SIGMA = 0.01


def _gaussian_blob(H, W, cy, cx, r):
    yy, xx = np.mgrid[0:H, 0:W]
    return np.exp(-(((yy - cy) ** 2 + (xx - cx) ** 2) / (2.0 * r ** 2)))


def make_cube(seed: int = 0) -> np.ndarray:
    """A few spatial blobs, each with a distinct smooth spectral signature."""
    rng = np.random.default_rng(seed)
    x = np.zeros((H, W, C), dtype=np.float64)
    blobs = [(8, 8, 4.0), (22, 10, 5.0), (14, 24, 3.5)]
    for (cy, cx, r) in blobs:
        spatial = _gaussian_blob(H, W, cy, cx, r)
        # smooth spectral signature: a shifted raised cosine across channels
        peak = rng.uniform(0, C - 1)
        spectrum = 0.5 + 0.5 * np.cos((np.arange(C) - peak) / C * np.pi)
        x += spatial[:, :, None] * spectrum[None, None, :]
    x /= x.max()
    return x.astype(np.float64)


def make_mask(seed: int = 1) -> np.ndarray:
    """Random binary coded aperture, ~50% open."""
    rng = np.random.default_rng(seed)
    return (rng.random((H, W)) > 0.5).astype(np.float64)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default=".", help="Workspace root.")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    ws = Path(args.workspace).resolve()
    data = ws / "data"
    data.mkdir(parents=True, exist_ok=True)

    x = make_cube(seed=args.seed)
    mask = make_mask(seed=args.seed + 1)
    rng = np.random.default_rng(args.seed + 2)
    y = forward(x, mask) + rng.normal(0.0, SIGMA, size=(H, W + C - 1))

    np.save(data / "ground_truth_x.npy", x.astype(np.float32))
    np.save(data / "coded_aperture_phi.npy", mask.astype(np.float32))
    np.save(data / "measurement_y.npy", y.astype(np.float32))

    print(f"Wrote data/ground_truth_x.npy   {x.shape}")
    print(f"Wrote data/coded_aperture_phi.npy {mask.shape} ({mask.mean()*100:.0f}% open)")
    print(f"Wrote data/measurement_y.npy    {y.shape}  (sigma={SIGMA})")


if __name__ == "__main__":
    main()
