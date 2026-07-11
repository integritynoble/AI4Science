"""SD-CASSI forward / adjoint operators (reference solver copy).

This is the contributor-side operator used by the GAP-TV solver. The
Physics Judge has its OWN independent copy in
ai4science/judge/cassi/forward.py — by design, the judge does not trust
this file. Keeping the math identical here is what lets a correct solver
pass S4.
"""
from __future__ import annotations

import numpy as np


def forward(x: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """x:(H,W,C), mask:(H,W) → y:(H, W+C-1)."""
    H, W, C = x.shape
    masked = x * mask[:, :, None]
    y = np.zeros((H, W + C - 1), dtype=np.float64)
    for c in range(C):
        y[:, c:c + W] += masked[:, :, c]
    return y


def adjoint(y: np.ndarray, mask: np.ndarray, channels: int) -> np.ndarray:
    """y:(H, W+C-1), mask:(H,W) → x:(H,W,C)."""
    H, Wc = y.shape
    W = Wc - channels + 1
    x = np.zeros((H, W, channels), dtype=np.float64)
    for c in range(channels):
        x[:, :, c] = y[:, c:c + W] * mask
    return x


def forward_sum(mask: np.ndarray, channels: int) -> np.ndarray:
    """Phi-sum normalizer: A(ones) — per-measurement-pixel sensitivity.

    For a binary mask this equals sum_c mask shifted into measurement
    space, which is the diagonal of A A^T used by GAP-TV's step size.
    """
    H, W = mask.shape
    ones = np.ones((H, W, channels), dtype=np.float64)
    return forward(ones * mask[:, :, None], mask)
