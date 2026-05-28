"""S4b — noise consistency check.

If the spec declares an additive-Gaussian noise model with std sigma,
and y + x_hat (+ optionally the coded aperture) are available, check that
the std of the residual e = y - A(x_hat) is statistically consistent
with sigma.

A is the judge's own forward operator: real SD-CASSI when
data/coded_aperture_phi.npy is present, else a channel-sum fallback.

Bands:
  |std(e) - sigma| / sigma <= 0.25 → pass
                            <= 0.50 → warning
                            else    → fail

sigma comes from spec.md's ``noise_sigma``. If not declared, the check
is not_available (we don't invent a noise level).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from ai4science.judge import CheckResult
from ai4science.judge.cassi.forward import cassi_forward
from ai4science.schemas import parse_front_matter


def check_s4_noise_consistency(workspace: Path) -> CheckResult:
    y_path = workspace / "data" / "measurement_y.npy"
    x_path = workspace / "results" / "reconstruction_xhat.npy"
    mask_path = workspace / "data" / "coded_aperture_phi.npy"
    if not y_path.exists() or not x_path.exists():
        return CheckResult(
            "not_available",
            "noise-consistency check requires data/measurement_y.npy and "
            "results/reconstruction_xhat.npy",
        )

    spec_data, _ = parse_front_matter(workspace / "spec.md")
    if not spec_data or "noise_sigma" not in spec_data:
        return CheckResult(
            "not_available",
            "noise_sigma not declared in spec.md; noise-consistency check skipped",
        )
    declared_sigma = float(spec_data["noise_sigma"])

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

    e = (y - y_pred).ravel()
    if e.size < 2:
        return CheckResult("not_available", "residual has <2 elements; cannot estimate std")
    est_sigma = float(e.std(ddof=1))

    rel_err = abs(est_sigma - declared_sigma) / max(declared_sigma, 1e-12)
    evidence = {
        "declared_sigma": declared_sigma,
        "estimated_sigma": est_sigma,
        "relative_error": rel_err,
        "forward": forward_kind,
    }

    if rel_err <= 0.25:
        return CheckResult("pass", f"noise std consistent (rel_err={rel_err:.2%}, "
                                   f"forward={forward_kind})", evidence)
    if rel_err <= 0.50:
        return CheckResult("warning", f"noise std partially consistent "
                                      f"(rel_err={rel_err:.2%})", evidence)
    return CheckResult("fail", f"noise std inconsistent (rel_err={rel_err:.2%})", evidence)


def _forward(x: np.ndarray, y: np.ndarray, mask_path: Path):
    """Apply the judge's forward; CASSI if a valid mask is present."""
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
