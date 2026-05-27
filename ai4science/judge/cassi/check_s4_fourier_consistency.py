"""S4c — Fourier-domain consistency check.

For a valid CASSI reconstruction, the channel-summed reconstruction
should match the measurement in low-frequency content. We compare
the low-frequency energy ratio of y vs. forward(x_hat).

v0.1: pass if the low-freq energy ratio is within 30% of unity;
warning within 60%; fail otherwise.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from ai4science.judge import CheckResult


def check_s4_fourier_consistency(workspace: Path) -> CheckResult:
    y_path = workspace / "data" / "measurement_y.npy"
    x_path = workspace / "results" / "reconstruction_xhat.npy"
    if not y_path.exists() or not x_path.exists():
        return CheckResult(
            "not_available",
            "fourier-consistency check requires data/measurement_y.npy and results/reconstruction_xhat.npy",
        )

    try:
        y = np.load(y_path).astype(np.float64)
        x = np.load(x_path).astype(np.float64)
    except Exception as e:
        return CheckResult("fail", f"could not load arrays: {e}")

    y_pred = x.sum(axis=-1) if x.ndim == 3 else x
    if y_pred.shape != y.shape:
        slices = tuple(slice(0, min(a, b)) for a, b in zip(y_pred.shape, y.shape))
        y_pred = y_pred[slices]
        y = y[slices]

    if y.ndim != 2 or min(y.shape) < 4:
        return CheckResult(
            "not_available",
            f"need 2-D arrays with min dim >= 4 for FFT comparison; got y.shape={y.shape}",
        )

    Y = np.fft.fft2(y)
    Yp = np.fft.fft2(y_pred)

    H, W = y.shape
    cy, cx = H // 4, W // 4   # low-freq quadrant
    low_y = float(np.sum(np.abs(Y[:cy, :cx]) ** 2))
    low_p = float(np.sum(np.abs(Yp[:cy, :cx]) ** 2))

    if low_y < 1e-20:
        return CheckResult("not_available", "measurement low-freq energy is ~0; check skipped")

    ratio = low_p / low_y
    deviation = abs(ratio - 1.0)
    evidence = {
        "low_freq_energy_ratio": ratio,
        "deviation_from_unity": deviation,
        "low_freq_quadrant": [cy, cx],
    }

    if deviation <= 0.30:
        return CheckResult("pass", f"low-freq energy ratio {ratio:.3f} within 30%", evidence)
    if deviation <= 0.60:
        return CheckResult("warning", f"low-freq energy ratio {ratio:.3f} within 60%", evidence)
    return CheckResult("fail", f"low-freq energy ratio {ratio:.3f} outside 60%", evidence)
