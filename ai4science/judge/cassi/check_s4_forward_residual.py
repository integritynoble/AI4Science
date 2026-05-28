"""S4a — forward-residual consistency check.

If both data/measurement_y.npy and results/reconstruction_xhat.npy are
present, compute the relative forward residual:

    r = ||y - A(x_hat)||_2 / ||y||_2

Where A is the forward operator. Two modes:

  - **CASSI mode** (preferred): if data/coded_aperture_phi.npy exists,
    the judge applies its OWN SD-CASSI forward operator (independent of
    the contributor's code). This is the physically meaningful check.
  - **channel-sum fallback**: if no mask is shipped, A is approximated by
    a per-channel sum. Coarse, but lets the check run on minimal data.

Verdict bands (relative to the spec's tolerance_epsilon):
  r < tol            → pass
  tol <= r < 10*tol  → warning
  r >= 10*tol        → fail

If either array is missing, returns 'not_available' with the reason.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from ai4science.judge import CheckResult
from ai4science.judge.cassi.forward import cassi_forward, infer_channels
from ai4science.schemas import parse_front_matter


def check_s4_forward_residual(workspace: Path) -> CheckResult:
    y_path = workspace / "data" / "measurement_y.npy"
    x_path = workspace / "results" / "reconstruction_xhat.npy"
    mask_path = workspace / "data" / "coded_aperture_phi.npy"

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
        y = np.load(y_path).astype(np.float64)
        x = np.load(x_path).astype(np.float64)
    except Exception as e:
        return CheckResult("fail", f"could not load measurement / reconstruction: {e}")

    y_pred, forward_kind, err = _apply_forward(x, y, mask_path)
    if err is not None:
        return CheckResult("fail", err)

    # Align shapes if a fallback forward produced a mismatch.
    if y_pred.shape != y.shape:
        if y_pred.ndim != y.ndim:
            return CheckResult(
                "fail",
                f"shape mismatch: y={y.shape}, A(x_hat)={y_pred.shape} "
                f"(forward={forward_kind})",
            )
        slices = tuple(slice(0, min(a, b)) for a, b in zip(y_pred.shape, y.shape))
        y_pred = y_pred[slices]
        y = y[slices]

    eps = 1e-12
    y_norm = float(np.linalg.norm(y) + eps)
    r = float(np.linalg.norm(y - y_pred) / y_norm)

    spec_data, _ = parse_front_matter(workspace / "spec.md")
    tol = float((spec_data or {}).get("tolerance_epsilon", 0.01))

    evidence = {
        "residual": r,
        "tolerance": tol,
        "forward": forward_kind,
        "y_shape": list(y.shape),
        "x_shape": list(x.shape),
    }

    if r < tol:
        return CheckResult("pass", f"forward residual {r:.4g} < tol {tol:.4g} "
                                   f"(forward={forward_kind})", evidence)
    if r < 10 * tol:
        return CheckResult("warning", f"forward residual {r:.4g} in "
                                      f"[{tol:.4g}, {10*tol:.4g}) (forward={forward_kind})",
                           evidence)
    return CheckResult("fail", f"forward residual {r:.4g} >= 10x tolerance "
                               f"({10*tol:.4g}) (forward={forward_kind})", evidence)


def _apply_forward(x: np.ndarray, y: np.ndarray, mask_path: Path):
    """Return (y_pred, forward_kind, error_message)."""
    if mask_path.exists() and x.ndim == 3:
        try:
            mask = np.load(mask_path).astype(np.float64)
        except Exception as e:
            return None, "cassi", f"could not load coded aperture: {e}"
        # Verify the mask is dimensionally consistent with x.
        H, W, C = x.shape
        if mask.shape == (H, W):
            try:
                return cassi_forward(x, mask), "cassi", None
            except ValueError as e:
                return None, "cassi", f"CASSI forward failed: {e}"
        # Mask present but wrong shape — fall through to channel-sum.
    # Fallback: channel sum.
    if x.ndim == 3:
        return x.sum(axis=-1), "channel-sum", None
    if x.ndim == 2:
        return x, "identity", None
    return None, "unknown", f"unexpected reconstruction shape {x.shape!r}"
