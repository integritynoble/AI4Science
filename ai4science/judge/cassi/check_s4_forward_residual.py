"""S4a — forward-residual consistency check.

If both data/measurement_y.npy and results/reconstruction_xhat.npy are
present (and shapes line up), compute the simple residual:

    r = ||y - sum_c x_hat[:,:,c]||_2 / ||y||_2

v0.1 uses a deliberately minimal "forward operator": a per-channel sum,
which mimics CASSI's spatial-multiplex aggregation without requiring the
calibrated Phi to be shipped. This is a coarse but deterministic signal:

  - r < tolerance_epsilon  → pass
  - tolerance_epsilon <= r < 10*tolerance_epsilon  → warning
  - r >= 10*tolerance_epsilon  → fail

If either file is missing, returns 'not_available' with a clear reason.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from ai4science.judge import CheckResult
from ai4science.schemas import parse_front_matter


def check_s4_forward_residual(workspace: Path) -> CheckResult:
    y_path = workspace / "data" / "measurement_y.npy"
    x_path = workspace / "results" / "reconstruction_xhat.npy"

    if not y_path.exists() or not x_path.exists():
        present, missing = [], []
        for label, p in (("data/measurement_y.npy", y_path),
                         ("results/reconstruction_xhat.npy", x_path)):
            (present if p.exists() else missing).append(label)
        return CheckResult(
            "not_available",
            f"forward-residual check requires {missing} (present: {present})",
            evidence={"present": present, "missing": missing},
        )

    try:
        y = np.load(y_path)
        x = np.load(x_path)
    except Exception as e:
        return CheckResult("fail", f"could not load measurement / reconstruction: {e}")

    # v0.1 toy forward: channel sum (last axis if 3-D, identity if 2-D).
    if x.ndim == 3:
        y_pred = x.sum(axis=-1)
    elif x.ndim == 2:
        y_pred = x
    else:
        return CheckResult(
            "fail",
            f"unexpected reconstruction shape {x.shape!r}; expected 2-D or 3-D array",
        )

    # Spatial broadcast: trim or pad y_pred to match y's spatial extent.
    if y_pred.shape != y.shape:
        # Try a simple center-crop fallback. If shapes are wildly different, fail.
        if y_pred.ndim != y.ndim:
            return CheckResult(
                "fail",
                f"shape mismatch: y={y.shape}, y_pred (channel-sum)={y_pred.shape}",
            )
        # Crop to the min in each axis.
        slices = tuple(slice(0, min(a, b)) for a, b in zip(y_pred.shape, y.shape))
        y_pred = y_pred[slices]
        y = y[slices]

    eps = 1e-12
    y_norm = float(np.linalg.norm(y) + eps)
    r = float(np.linalg.norm(y - y_pred) / y_norm)

    # Look up tolerance from spec.md if available; else default 0.01.
    spec_path = workspace / "spec.md"
    data, _ = parse_front_matter(spec_path)
    tol = float((data or {}).get("tolerance_epsilon", 0.01))

    evidence = {
        "residual": r,
        "tolerance": tol,
        "y_norm": y_norm,
        "y_shape": list(y.shape),
        "x_shape": list(x.shape),
    }

    if r < tol:
        return CheckResult("pass", f"forward residual {r:.4g} < tol {tol:.4g}", evidence)
    if r < 10 * tol:
        return CheckResult(
            "warning",
            f"forward residual {r:.4g} in [{tol:.4g}, {10*tol:.4g})",
            evidence,
        )
    return CheckResult(
        "fail",
        f"forward residual {r:.4g} >= 10x tolerance ({10*tol:.4g})",
        evidence,
    )
