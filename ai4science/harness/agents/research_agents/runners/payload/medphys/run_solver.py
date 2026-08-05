"""Inverse planning on a real head-and-neck case.

Beamlets from a coplanar arc, weights found by multiplicative updates against
the protocol's own cost: cover each target to its prescription, spare each
organ to its limit. The protocol is read, never written.

Output is a plan CANDIDATE. There is no file this can write that means approved
— that is a physicist's signature and it does not live on disk here.
"""
import argparse, json, os
import numpy as np


def load_params(ws, **defaults):
    f = os.path.join(ws, "params.json")
    if os.path.exists(f):
        defaults.update(json.load(open(f)))
    return defaults
from scipy.ndimage import gaussian_filter, rotate, shift as ndshift

ANGLES = tuple(range(0, 360, 40))
STRIDE = 4


def beamlets(shape, angle, cy, cx):
    """Per-column fields through the slice, aimed at (cy, cx).

    The aim is the whole point and was missing in the first version of this:
    without the shift every beam converges on the image centre instead of the
    tumour, which put 2144 Gy in the middle of a patient's neck while every
    target constraint still read as met."""
    ny, nx = shape
    z = np.linspace(0.0, 1.0, ny)
    depth = ((1.0 - np.exp(-z / 0.07)) * np.exp(-1.1 * z))[:, None]
    dy, dx = float(cy - ny / 2.0), float(cx - nx / 2.0)
    out = []
    for c in range(0, nx, STRIDE):
        f = np.zeros((ny, nx))
        f[:, c:c + STRIDE] = 1.0
        f = gaussian_filter(f * depth, 1.0)
        f = rotate(f, angle, reshape=False, order=1)
        # Zero fill, not a cyclic roll: a rolled beam re-enters on the far side
        # and stacks its entrance dose there.
        out.append(ndshift(f, (dy, dx), order=1, mode="constant", cval=0.0))
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--workspace", default=".")
    ws = ap.parse_args().workspace
    dpath = lambda n: os.path.join(ws, "data", n)
    proto = json.load(open(dpath("protocol.json")))
    possible = np.load(dpath("possible.npy"))

    # Work on the axial slice carrying most of the primary target.
    ptv = np.load(dpath("PTV70.npy"))
    k = int(np.argmax(ptv.sum(axis=(0, 1))))
    sl = lambda a: a[:, :, k]
    tgt = {n: sl(np.load(dpath("%s.npy" % n))) for n in proto
           if n.startswith("PTV") and os.path.exists(dpath("%s.npy" % n))}
    oars = {n: sl(np.load(dpath("%s.npy" % n))) for n in proto
            if not n.startswith("PTV") and os.path.exists(dpath("%s.npy" % n))}
    body = sl(possible)
    prim = tgt["PTV70"]
    if not prim.any():
        raise SystemExit("no PTV70 on the chosen slice")
    cy, cx = np.argwhere(prim).mean(axis=0)

    A = np.stack([b for ang in ANGLES for b in beamlets(prim.shape, ang, cy, cx)])
    K = len(A)
    At = {n: A[:, m] for n, m in tgt.items()}
    Ao = {n: A[:, m] for n, m in oars.items() if m.any()}
    Ab = A[:, body]
    rx = proto["PTV70"]["prescription"]

    pr = load_params(ws, oar_weight=6.0, hot_weight=3.0, step=0.6, iters=900,
                     under_weight=20.0)

    # Projected gradient on a TWO-SIDED objective.
    #
    # The previous cost penalised target UNDERDOSE only — `clip(rx - d, 0)` —
    # so nothing anywhere pushed the target dose down, and normalising D99 to
    # the prescription then dragged the whole slice up with it: target mean
    # 101.9 Gy against a 70 Gy prescription, target max 148, and 381 of 655
    # body voxels above 80. The plan met D99 because D99 is the COLDEST
    # percentile, which is exactly the statistic that cannot see an overdose.
    #
    # Deviation from prescription is penalised in both directions now, which is
    # what a clinical objective does and why uniformity is stated as D99 >= 95%
    # AND D1 <= 107% rather than a floor alone.
    def grad_and_cost(w):
        g = np.zeros(K)
        cost = 0.0
        for n, Am in At.items():
            resid = (w @ Am) - proto[n]["prescription"]       # BOTH directions
            # Asymmetric, as clinical objectives are: missing the tumour is
            # worse than a modest hot spot inside it. Symmetric weighting left
            # D99 at 62.2 against a 66.5 floor — uniform, and uniformly too
            # cold, because the cold tail counts no more than the warm one.
            wgt = np.where(resid < 0, pr["under_weight"], 1.0)
            g += 2.0 * (Am @ (wgt * resid)) / max(Am.shape[1], 1)
            cost += float((wgt * resid ** 2).mean())
        for n, Am in Ao.items():
            lim = proto[n].get("Dmax") or proto[n].get("Dmean")
            over = np.clip((w @ Am) - lim * 0.85, 0, None)
            g += pr["oar_weight"] * 2.0 * (Am @ over) / max(Am.shape[1], 1)
            cost += pr["oar_weight"] * float((over ** 2).mean())
        hot = np.clip((w @ Ab) - rx * 1.07, 0, None)
        g += pr["hot_weight"] * 2.0 * (Ab @ hot) / max(Ab.shape[1], 1)
        cost += pr["hot_weight"] * float((hot ** 2).mean())
        return g, cost

    w = np.full(K, rx / max(float(A[:, prim].sum(axis=0).mean()), 1e-9))
    step = float(pr["step"])
    _, cost = grad_and_cost(w)
    for _ in range(int(round(float(pr["iters"])))):
        g, _ = grad_and_cost(w)
        gn = float(np.linalg.norm(g))
        if not np.isfinite(gn) or gn < 1e-12:
            break
        trial = np.clip(w - step * g / gn * max(float(w.mean()), 1e-9), 0.0, None)
        _, tcost = grad_and_cost(trial)
        if tcost < cost:                    # accept and grow
            w, cost, step = trial, tcost, min(step * 1.1, 2.0)
        else:                               # overshot: shrink
            step *= 0.5
            if step < 1e-6:
                break

    dose = np.tensordot(w, A, axes=(0, 0)) * body
    os.makedirs(os.path.join(ws, "results"), exist_ok=True)
    np.save(os.path.join(ws, "results", "dose.npy"), dose)
    np.save(os.path.join(ws, "results", "slice_index.npy"), np.array([k]))
    json.dump({"status": "candidate",
               "requires": "sign-off by a qualified medical physicist",
               "slice": int(k), "beams": len(ANGLES), "beamlets": int(K)},
              open(os.path.join(ws, "results", "plan_candidate.json"), "w"))
    print("plan candidate written for slice", k)


if __name__ == "__main__":
    main()
