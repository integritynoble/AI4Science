"""FISTA-TV reconstruction for SD-CASSI.

A genuine accelerated proximal-gradient solver (Beck & Teboulle 2009)
for the regularized inverse problem

    min_x  (1/2) ||y - A x||^2 + lambda * TV(x),   x >= 0

with a Chambolle (2004) TV proximal operator applied per spectral
channel. Pure NumPy, no learned components.

Why FISTA and not the textbook GAP projection: the SD-CASSI operator's
A A^T is not diagonal (adjacent channels share spatial positions), so
the diagonal-approximated GAP projection overshoots and diverges. A
proximal-gradient step with step size 1/L (L = ||A^T A|| estimated by
power iteration) is unconditionally stable.
"""
from __future__ import annotations

import numpy as np

from cassi import forward, adjoint


def _grad(u):
    gx = np.zeros_like(u); gy = np.zeros_like(u)
    gx[:-1, :] = u[1:, :] - u[:-1, :]
    gy[:, :-1] = u[:, 1:] - u[:, :-1]
    return gx, gy


def _div(px, py):
    tx = np.zeros_like(px); ty = np.zeros_like(py)
    tx[1:-1, :] = px[1:-1, :] - px[:-2, :]
    tx[0, :] = px[0, :]
    tx[-1, :] = -px[-2, :]
    ty[:, 1:-1] = py[:, 1:-1] - py[:, :-2]
    ty[:, 0] = py[:, 0]
    ty[:, -1] = -py[:, -2]
    return tx + ty


def tv_chambolle(g: np.ndarray, weight: float = 0.05, n_iter: int = 25,
                 tau: float = 0.125) -> np.ndarray:
    """Chambolle TV prox: argmin_u ||u-g||^2 + 2*weight*TV(u)."""
    if weight <= 0:
        return g
    px = np.zeros_like(g); py = np.zeros_like(g)
    for _ in range(n_iter):
        u = g - weight * _div(px, py)
        ux, uy = _grad(u)
        norm = np.sqrt(ux ** 2 + uy ** 2)
        denom = 1.0 + (tau / weight) * norm
        px = (px + (tau / weight) * ux) / denom
        py = (py + (tau / weight) * uy) / denom
    return g - weight * _div(px, py)


def tv_prox_cube(x: np.ndarray, weight: float, n_iter: int = 20) -> np.ndarray:
    out = np.empty_like(x)
    for c in range(x.shape[2]):
        out[:, :, c] = tv_chambolle(x[:, :, c], weight=weight, n_iter=n_iter)
    return out


def estimate_lipschitz(mask: np.ndarray, channels: int, n_iter: int = 30) -> float:
    """Largest eigenvalue of A^T A via power iteration."""
    H, W = mask.shape
    rng = np.random.default_rng(0)
    v = rng.random((H, W, channels))
    v /= np.linalg.norm(v) + 1e-12
    lam = 1.0
    for _ in range(n_iter):
        w = adjoint(forward(v, mask), mask, channels)
        lam = float(np.linalg.norm(w))
        v = w / (lam + 1e-12)
    return lam + 1e-6


def gap_tv(y: np.ndarray, mask: np.ndarray, channels: int,
           n_iters: int = 120, tv_weight: float = 0.01,
           verbose: bool = False) -> np.ndarray:
    """FISTA-TV reconstruction of the (H, W, C) cube from snapshot y.

    (Named gap_tv for continuity with the benchmark's baseline_methods;
    the algorithm is accelerated proximal gradient.)"""
    L = estimate_lipschitz(mask, channels)
    step = 1.0 / L

    x = adjoint(y, mask, channels)
    z = x.copy()
    t = 1.0
    for it in range(n_iters):
        grad = adjoint(forward(z, mask) - y, mask, channels)
        x_new = z - step * grad
        x_new = tv_prox_cube(x_new, weight=step * tv_weight)
        x_new = np.clip(x_new, 0.0, None)
        t_new = 0.5 * (1.0 + np.sqrt(1.0 + 4.0 * t * t))
        z = x_new + ((t - 1.0) / t_new) * (x_new - x)
        x, t = x_new, t_new
        if verbose and (it % 30 == 0 or it == n_iters - 1):
            res = np.linalg.norm(y - forward(x, mask)) / (np.linalg.norm(y) + 1e-12)
            print(f"  iter {it:3d}  relative residual {res:.5f}")
    return x
