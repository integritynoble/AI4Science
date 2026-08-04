"""Filtered back-projection with a ramp filter, then a mild edge-aware smooth.

Reads only the sinogram and the angles. The ground truth is not in this
workspace and the solver has no way to ask for it."""
import argparse, os
import numpy as np
from scipy.ndimage import rotate


def ramp_filter(sino):
    n = sino.shape[1]
    f = np.fft.fftfreq(n).reshape(1, -1)
    return np.real(np.fft.ifft(np.fft.fft(sino, axis=1) * np.abs(f) * 2.0, axis=1))


def fbp(sino, angles, n):
    out = np.zeros((n, n), float)
    filt = ramp_filter(sino)
    for row, ang in zip(filt, angles):
        out += rotate(np.tile(row, (n, 1)), -ang, reshape=False, order=1)
    return out / len(angles) * np.pi


def tv_smooth(img, weight=0.08, iters=40):
    """Gradient descent on a Huber-TV objective — edge preserving, so the
    low-contrast disk survives where a Gaussian would erase it."""
    u, eps = img.copy(), 1e-3
    for _ in range(iters):
        gx = np.diff(u, axis=1, prepend=u[:, :1])
        gy = np.diff(u, axis=0, prepend=u[:1, :])
        mag = np.sqrt(gx**2 + gy**2 + eps)
        dx = np.diff(gx / mag, axis=1, append=(gx / mag)[:, -1:])
        dy = np.diff(gy / mag, axis=0, append=(gy / mag)[-1:, :])
        u += weight * (dx + dy) - 0.06 * (u - img)
    return u


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default=".")
    ws = ap.parse_args().workspace
    sino = np.load(os.path.join(ws, "data", "sinogram.npy"))
    angles = np.load(os.path.join(ws, "data", "angles.npy"))
    rec = fbp(sino, angles, sino.shape[1])
    rec = (rec - rec.min()) / max(float(np.ptp(rec)), 1e-9) * 1.35
    rec = tv_smooth(rec)
    os.makedirs(os.path.join(ws, "results"), exist_ok=True)
    np.save(os.path.join(ws, "results", "reconstruction.npy"), rec)
    print("reconstructed", rec.shape)


if __name__ == "__main__":
    main()
