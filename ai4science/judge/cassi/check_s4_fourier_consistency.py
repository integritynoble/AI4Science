"""S4c — Fourier-domain consistency check.

The forward projection of a valid reconstruction should match the
measurement in low-frequency content. We compare the low-frequency
energy of y vs A(x_hat), where A is the judge's own forward operator
(real SD-CASSI when the coded aperture is shipped, else channel-sum).

Bands (deviation of the low-freq energy ratio from unity):
  <= 0.30 → pass
  <= 0.60 → warning
  else    → fail
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from ai4science.judge import CheckResult
from ai4science.judge.cassi.forward import cassi_forward


def check_s4_fourier_consistency(workspace: Path) -> CheckResult:
    y_path = workspace / "data" / "measurement_y.npy"
    x_path = workspace / "results" / "reconstruction_xhat.npy"
    mask_path = workspace / "data" / "coded_aperture_phi.npy"
    if not y_path.exists() or not x_path.exists():
        return CheckResult(
            "not_available",
            "fourier-consistency check requires data/measurement_y.npy and "
            "results/reconstruction_xhat.npy",
        )

    try:
        y = np.load(y_path).astype(np.float64)
        x = np.load(x_path).astype(np.float64)
    except Exception as e:
        return CheckResult("fail", f"could not load arrays: {e}")

    y_pred, forward_kind = _forward(x, y, mask_path)
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
        "forward": forward_kind,
    }

    if deviation <= 0.30:
        return CheckResult("pass", f"low-freq energy ratio {ratio:.3f} within 30% "
                                   f"(forward={forward_kind})", evidence)
    if deviation <= 0.60:
        return CheckResult("warning", f"low-freq energy ratio {ratio:.3f} within 60%", evidence)
    return CheckResult("fail", f"low-freq energy ratio {ratio:.3f} outside 60%", evidence)


def _forward(x: np.ndarray, y: np.ndarray, mask_path: Path):
    if mask_path.exists() and x.ndim == 3:
        try:
            mask = np.load(mask_path).astype(np.float64)
            H, W, _ = x.shape
            if mask.shape == (H, W):
                return cassi_forward(x, mask), "cassi"
        except Exception:
            pass
    if x.ndim == 3:
        return x.sum(axis=-1), "channel-sum"
    return x, "identity"
