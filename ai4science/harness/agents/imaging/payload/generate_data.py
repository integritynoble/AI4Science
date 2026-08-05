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


def make_mask(seed: int = 1, H: int = H, W: int = W) -> np.ndarray:
    """Random binary coded aperture, ~50% open.

    Takes its dimensions rather than closing over the module constants: a real
    scene sets the size, and the constants are only the fallback shape."""
    rng = np.random.default_rng(seed)
    return (rng.random((H, W)) > 0.5).astype(np.float64)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default=".", help="Workspace root.")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--from-truth", action="store_true",
                    help="build the measurement from an existing real scene at "
                         "data/ground_truth_x.npy rather than synthesising one")
    args = ap.parse_args()

    ws = Path(args.workspace).resolve()
    data = ws / "data"
    data.mkdir(parents=True, exist_ok=True)

    if args.from_truth:
        # A real hyperspectral scene, already written by the seeder. Its shape
        # drives everything below — the synthetic path's H, W, C are a fallback
        # for when no corpus is present, not the benchmark's dimensions.
        x = np.load(data / "ground_truth_x.npy").astype(np.float64)
    else:
        x = make_cube(seed=args.seed)
    h, w, c = x.shape
    mask = make_mask(seed=args.seed + 1, H=h, W=w)
    rng = np.random.default_rng(args.seed + 2)
    y_clean = forward(x, mask)

    # Noise is specified RELATIVE to the measurement, not as an absolute sigma.
    #
    # A fixed SIGMA silently changes both the difficulty and the solvability
    # when the scene changes. On real CAVE scenes the old SIGMA=0.01 put the
    # forward residual of the GROUND TRUTH at 0.0239 against the judge's 0.01
    # tolerance — so a perfect reconstruction failed the physics check and the
    # benchmark was unsolvable. The sanity test that submits ground truth is
    # what caught it.
    #
    # Targeting a relative residual of ~0.3x tolerance keeps a correct
    # reconstruction comfortably inside the check while leaving the problem
    # genuinely noisy.
    rel_target = 0.003
    scale = float(np.sqrt((y_clean ** 2).mean()))
    sigma = rel_target * scale if scale > 0 else SIGMA
    y = y_clean + rng.normal(0.0, sigma, size=(h, w + c - 1))

    np.save(data / "ground_truth_x.npy", x.astype(np.float32))
    np.save(data / "coded_aperture_phi.npy", mask.astype(np.float32))
    np.save(data / "measurement_y.npy", y.astype(np.float32))

    print(f"Wrote data/ground_truth_x.npy   {x.shape}")
    print(f"Wrote data/coded_aperture_phi.npy {mask.shape} ({mask.mean()*100:.0f}% open)")
    # The spec must state what was ACTUALLY done. The judge cross-checks the
    # observed noise against the declared noise_sigma, and changing the data
    # without updating the declaration is an 82% mismatch it catches — which is
    # the check working, not an obstacle. Dimensions likewise: the spec named a
    # 32x32x8 cube while a real scene is 64x64x8.
    spec = ws / "spec.md"
    if spec.exists():
        text = spec.read_text()
        wc = w + c - 1
        subs = {
            "noise_sigma:": "noise_sigma: %.6g" % sigma,
            "omega_domain:": 'omega_domain: "x in R^{%d x %d x %d}, y in R^{%d x %d}"'
                             % (h, w, c, h, wc),
            "observable:": 'observable: "y = A(x) + n, y in R^{%d x %d}"' % (h, wc),
            "input_format:": 'input_format: "y: numpy .npy float32 of shape (%d, %d); '
                             'mask: numpy .npy of shape (%d, %d)"' % (h, wc, h, w),
            "output_format:": 'output_format: "x_hat: numpy .npy float32 of shape '
                              '(%d, %d, %d)"' % (h, w, c),
        }
        out = []
        for line in text.splitlines():
            key = line.split(" ", 1)[0] if line else ""
            out.append(subs.get(key, line))
        spec.write_text("\n".join(out) + "\n")

    print(f"Wrote data/measurement_y.npy    {y.shape}  (sigma={sigma:.5g}, "
          f"relative to the measurement)")


if __name__ == "__main__":
    main()
