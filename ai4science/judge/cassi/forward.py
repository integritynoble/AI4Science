"""The judge's own SD-CASSI forward operator.

This is deliberately a *separate* implementation from whatever solver the
contributor ships in their ``code/`` directory. The whole point of the
Physics Judge is that it recomputes the forward model INDEPENDENTLY — a
contributor cannot pass S4 by shipping a broken or cheating forward.

Single-disperser CASSI forward model:

    masked[:, :, c] = mask[:, :] * x[:, :, c]      (coded aperture)
    y[:, c:c+W]    += masked[:, :, c]              (spectral dispersion + sum)

So ``x`` of shape (H, W, C) and ``mask`` of shape (H, W) produce a coded
2-D snapshot ``y`` of shape (H, W + C - 1).
"""
from __future__ import annotations

import numpy as np


def cassi_forward(x: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """SD-CASSI forward. x:(H,W,C), mask:(H,W) → y:(H, W+C-1)."""
    if x.ndim != 3:
        raise ValueError(f"cube must be 3-D (H,W,C); got shape {x.shape}")
    H, W, C = x.shape
    if mask.shape != (H, W):
        raise ValueError(f"mask shape {mask.shape} != cube spatial dims {(H, W)}")
    masked = x * mask[:, :, None]
    y = np.zeros((H, W + C - 1), dtype=np.float64)
    for c in range(C):
        y[:, c:c + W] += masked[:, :, c]
    return y


def cassi_adjoint(y: np.ndarray, mask: np.ndarray, channels: int) -> np.ndarray:
    """Adjoint A^T. y:(H, W+C-1), mask:(H,W) → x:(H,W,C)."""
    if y.ndim != 2:
        raise ValueError(f"measurement must be 2-D; got shape {y.shape}")
    H, Wc = y.shape
    W = Wc - channels + 1
    if mask.shape != (H, W):
        raise ValueError(f"mask shape {mask.shape} incompatible with y {y.shape} "
                         f"and C={channels}")
    x = np.zeros((H, W, channels), dtype=np.float64)
    for c in range(channels):
        x[:, :, c] = y[:, c:c + W] * mask
    return x


def infer_channels(y: np.ndarray, mask: np.ndarray) -> int:
    """Recover C from measurement width and mask width: C = (Wc - W) + 1."""
    return y.shape[1] - mask.shape[1] + 1
