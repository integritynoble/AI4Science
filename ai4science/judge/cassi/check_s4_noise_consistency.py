"""S4b — noise consistency check.

If the spec declares an additive-Gaussian noise model with std sigma,
and both y and x_hat are available, check that the std of the residual
e = y - forward(x_hat) is statistically consistent with sigma.

Concretely (v0.1):
- pass    if |std(e) - sigma| / sigma <= 0.25 (within 25%)
- warning if within 50%
- fail    otherwise

Looks for sigma in spec.md front-matter under "noise_sigma" first, then
falls back to a default of 0.01 (matching the CASSI example spec).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from ai4science.judge import CheckResult
from ai4science.schemas import parse_front_matter


def check_s4_noise_consistency(workspace: Path) -> CheckResult:
    y_path = workspace / "data" / "measurement_y.npy"
    x_path = workspace / "results" / "reconstruction_xhat.npy"
    if not y_path.exists() or not x_path.exists():
        return CheckResult(
            "not_available",
            "noise-consistency check requires data/measurement_y.npy and results/reconstruction_xhat.npy",
        )

    try:
        y = np.load(y_path).astype(np.float64)
        x = np.load(x_path).astype(np.float64)
    except Exception as e:
        return CheckResult("fail", f"could not load arrays: {e}")

    if x.ndim == 3:
        y_pred = x.sum(axis=-1)
    elif x.ndim == 2:
        y_pred = x
    else:
        return CheckResult("fail", f"unexpected reconstruction ndim={x.ndim}")

    # Match shapes by center-crop.
    if y_pred.shape != y.shape:
        slices = tuple(slice(0, min(a, b)) for a, b in zip(y_pred.shape, y.shape))
        y_pred = y_pred[slices]
        y = y[slices]

    # Look up declared sigma in spec.md (custom field). Per the user spec,
    # if noise parameters are not declared, this check is not_available —
    # we deliberately don't pretend a default.
    spec_data, _ = parse_front_matter(workspace / "spec.md")
    if not spec_data or "noise_sigma" not in spec_data:
        return CheckResult(
            "not_available",
            "noise_sigma not declared in spec.md; noise-consistency check skipped",
        )
    declared_sigma = float(spec_data["noise_sigma"])

    e = (y - y_pred).ravel()
    if e.size < 2:
        return CheckResult("not_available", "residual has <2 elements; cannot estimate std")
    est_sigma = float(e.std(ddof=1))

    rel_err = abs(est_sigma - declared_sigma) / max(declared_sigma, 1e-12)
    evidence = {
        "declared_sigma": declared_sigma,
        "estimated_sigma": est_sigma,
        "relative_error": rel_err,
    }

    if rel_err <= 0.25:
        return CheckResult("pass", f"noise std consistent (rel_err={rel_err:.2%})", evidence)
    if rel_err <= 0.50:
        return CheckResult("warning", f"noise std partially consistent (rel_err={rel_err:.2%})", evidence)
    return CheckResult("fail", f"noise std inconsistent (rel_err={rel_err:.2%})", evidence)
