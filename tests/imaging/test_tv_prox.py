"""The TV prox must actually be a prox, and PSNR must not flatter the estimate.

Both of these shipped broken and both were invisible on the synthetic fixture.
`tv_chambolle` had its dual step sign inverted, which made it an *expansion*:
at weight 0.2 it raised the objective it claims to minimise 54-fold. Inside the
proximal-gradient loop that compounds every iteration, so the solver diverged —
reconstruction values reached 18.6 against a ground truth bounded by 1.0, a
true PSNR of -16.79 dB. Gaussian blobs are nearly piecewise-constant and carry
almost no total variation, so the term barely engaged and nothing complained.

`run_solver.psnr` then hid the divergence, because it took the peak from
`max(reference, estimate)`: a reconstruction that blew up set its own
denominator and reported 8.61 dB while it was at -16.79.

These are tested as properties — a prox lowers its objective, a distortion
metric does not reward distortion — rather than as remembered numbers. A test
asserting "PSNR > 20 on seed 42" would have passed the day the sign flipped.
"""
from __future__ import annotations

import sys

import numpy as np
import pytest

from ai4science.harness.agents.imaging import PAYLOAD_DIR

sys.path.insert(0, str(PAYLOAD_DIR))
from gap_tv import _grad, tv_chambolle, tv_prox_cube   # noqa: E402
from run_solver import psnr                            # noqa: E402

WEIGHTS = (0.001, 0.01, 0.05, 0.2)


def _objective(u: np.ndarray, g: np.ndarray, weight: float) -> float:
    """0.5||u-g||^2 + weight*TV(u) — what tv_chambolle claims to minimise."""
    gx, gy = _grad(u)
    return 0.5 * float(((u - g) ** 2).sum()) \
        + weight * float(np.sqrt(gx ** 2 + gy ** 2).sum())


def _textured_image(seed: int = 0) -> np.ndarray:
    """Something with real total variation. The bug is invisible without it."""
    rng = np.random.default_rng(seed)
    x = np.linspace(0, 6, 64)
    img = np.outer(np.sin(x), np.cos(x)) + 0.4 * rng.standard_normal((64, 64))
    return np.clip(img - img.min(), 0.0, None)


@pytest.mark.parametrize("weight", WEIGHTS)
def test_tv_prox_lowers_the_objective_it_minimises(weight):
    g = _textured_image()
    out = tv_chambolle(g, weight=weight, n_iter=25)
    assert _objective(out, g, weight) < _objective(g, g, weight), (
        "the prox returned a point worse than its own input at weight %g — "
        "it is not solving argmin 0.5||u-g||^2 + w*TV(u)" % weight)


@pytest.mark.parametrize("weight", WEIGHTS)
def test_tv_prox_does_not_amplify(weight):
    """A prox of a convex penalty is non-expansive; smoothing cannot add energy."""
    g = _textured_image()
    out = tv_chambolle(g, weight=weight, n_iter=25)
    assert np.linalg.norm(out) <= np.linalg.norm(g) * 1.01, (
        "TV smoothing grew the norm by %.2fx at weight %g"
        % (np.linalg.norm(out) / np.linalg.norm(g), weight))


def test_stronger_tv_smooths_more():
    """Monotone in the knob: more weight, less total variation. It ran backwards."""
    g = _textured_image()

    def total_variation(u):
        gx, gy = _grad(u)
        return float(np.sqrt(gx ** 2 + gy ** 2).sum())

    tvs = [total_variation(tv_chambolle(g, weight=w, n_iter=25)) for w in WEIGHTS]
    assert tvs == sorted(tvs, reverse=True), \
        "total variation did not fall monotonically with the weight: %s" % tvs
    assert tvs[-1] < total_variation(g)


def test_tv_prox_cube_is_stable_per_channel():
    rng = np.random.default_rng(3)
    cube = np.clip(rng.random((32, 32, 8)), 0.0, None)
    out = tv_prox_cube(cube, weight=0.05, n_iter=20)
    assert np.all(np.isfinite(out))
    assert np.linalg.norm(out) <= np.linalg.norm(cube) * 1.01


def test_psnr_peak_comes_from_the_reference_not_the_estimate():
    """A diverging reconstruction must not be able to inflate its own score."""
    rng = np.random.default_rng(5)
    ref = rng.random((16, 16, 4))
    blown_up = ref * 20.0
    assert psnr(ref, blown_up) < psnr(ref, ref * 1.05), \
        "a 20x scale error scored no worse than a 5% one"
    # Scaling the estimate further from the reference can only lose points.
    scores = [psnr(ref, ref * k) for k in (1.5, 3.0, 10.0, 30.0)]
    assert scores == sorted(scores, reverse=True), \
        "PSNR rose as the estimate got further from the reference: %s" % scores
