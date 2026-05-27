"""S4d — spatial coherence (smoothness) sanity check.

A valid CASSI hyperspectral reconstruction should have bounded
neighbor-pixel differences (natural scenes are not white noise).
v0.1 reports the mean absolute neighbor difference normalized by the
recon std. Extreme values (>> noise scale) suggest a degenerate
reconstruction.

  - pass    if 0.01 <= TV/std <= 2.0
  - warning if TV/std in [2.0, 5.0)
  - fail    if TV/std outside [0.01, 5.0)
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from ai4science.judge import CheckResult


def check_s4_spatial_coherence(workspace: Path) -> CheckResult:
    x_path = workspace / "results" / "reconstruction_xhat.npy"
    if not x_path.exists():
        return CheckResult(
            "not_available",
            "spatial-coherence check requires results/reconstruction_xhat.npy",
        )
    try:
        x = np.load(x_path).astype(np.float64)
    except Exception as e:
        return CheckResult("fail", f"could not load reconstruction: {e}")

    if x.ndim < 2:
        return CheckResult("fail", f"unexpected reconstruction ndim={x.ndim}")

    # Pick a 2-D slice (first channel if 3-D).
    sl = x[..., 0] if x.ndim == 3 else x
    if min(sl.shape) < 4:
        return CheckResult(
            "not_available",
            f"need 2-D slice with min dim >= 4; got shape {sl.shape}",
        )

    dx = np.abs(sl[1:, :] - sl[:-1, :]).mean()
    dy = np.abs(sl[:, 1:] - sl[:, :-1]).mean()
    tv = 0.5 * (dx + dy)
    std = float(sl.std() + 1e-12)
    ratio = float(tv / std)
    evidence = {"tv_over_std": ratio, "tv": float(tv), "std": std, "slice_shape": list(sl.shape)}

    if 0.01 <= ratio <= 2.0:
        return CheckResult("pass", f"spatial coherence ratio {ratio:.3f} in [0.01, 2.0]", evidence)
    if 2.0 < ratio < 5.0:
        return CheckResult("warning", f"spatial coherence ratio {ratio:.3f} in [2.0, 5.0)", evidence)
    return CheckResult("fail", f"spatial coherence ratio {ratio:.3f} outside [0.01, 5.0)", evidence)
