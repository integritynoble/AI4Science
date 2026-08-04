"""Sparse-view low-dose CT: a phantom, a sinogram, and a low-contrast lesion.

The lesion is the point. A denoiser raises PSNR most easily by smoothing, and
the first thing smoothing removes is exactly this disk — so the benchmark
carries a signal whose disappearance the judge can see.
"""
import argparse, json
import numpy as np
from scipy.ndimage import rotate

N, ANGLES, I0 = 96, 60, 40000.0         # sparse views, low photon count


def phantom(rng):
    y, x = np.mgrid[0:N, 0:N]
    img = np.zeros((N, N), float)
    img[((x - N/2)**2 / (0.40*N)**2 + (y - N/2)**2 / (0.30*N)**2) <= 1] = 1.0
    img[((x - 0.38*N)**2 + (y - 0.42*N)**2) <= (0.09*N)**2] = 1.35   # high contrast
    img[((x - 0.62*N)**2 + (y - 0.58*N)**2) <= (0.07*N)**2] = 0.72
    # the lesion: 14% contrast against the body, the thing that must
    # survive. Low enough that smoothing erases it, high enough that a
    # competent reconstruction keeps it — a benchmark no method can pass
    # cannot tell a good method from a bad one.
    # SMALL and low contrast. Size is the point: a large lesion survives any
    # amount of blurring, so a benchmark built on one cannot show the failure
    # this agent exists to catch. At ~3 px a Gaussian that maximises PSNR
    # erases it, and an edge-preserving prior does not.
    les = ((x - 0.55*N)**2 + (y - 0.36*N)**2) <= (0.032*N)**2
    img[les] = 1.13
    return img, les


def radon(img, angles):
    return np.stack([rotate(img, a, reshape=False, order=1).sum(axis=0)
                     for a in angles])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default="."); ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    ws, rng = a.workspace, np.random.default_rng(a.seed)
    import os
    os.makedirs(os.path.join(ws, "data"), exist_ok=True)
    img, les = phantom(rng)
    angles = np.linspace(0., 180., ANGLES, endpoint=False)
    sino = radon(img, angles)
    # Poisson counting statistics at a low dose
    expected = I0 * np.exp(-sino / sino.max() * 2.2)
    counts = rng.poisson(np.clip(expected, 1e-6, None)).astype(float)
    noisy = -np.log(np.clip(counts, 1.0, None) / I0) / 2.2 * sino.max()
    np.save(os.path.join(ws, "data", "sinogram.npy"), noisy)
    np.save(os.path.join(ws, "data", "angles.npy"), angles)
    np.save(os.path.join(ws, "data", "ground_truth.npy"), img)      # the answer key
    np.save(os.path.join(ws, "data", "lesion_mask.npy"), les)       # also withheld
    print(json.dumps({"n": N, "angles": ANGLES, "I0": I0, "seed": a.seed}))


if __name__ == "__main__":
    main()
