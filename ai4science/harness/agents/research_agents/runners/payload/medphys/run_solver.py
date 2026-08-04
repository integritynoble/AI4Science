"""Inverse planning on a real head-and-neck case.

Beamlets from a coplanar arc, weights found by multiplicative updates against
the protocol's own cost: cover each target to its prescription, spare each
organ to its limit. The protocol is read, never written.

Output is a plan CANDIDATE. There is no file this can write that means approved
— that is a physicist's signature and it does not live on disk here.
"""
import argparse, json, os
import numpy as np
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
    want = np.zeros(prim.shape)
    for n, m in sorted(tgt.items()):
        want[m] = proto[n]["prescription"]

    At = {n: A[:, m] for n, m in tgt.items()}
    Ao = {n: A[:, m] for n, m in oars.items() if m.any()}
    Ab = A[:, body]
    w = np.ones(K)

    def normalise(v):
        d = v @ At["PTV70"]
        p = float(np.percentile(d, 1)) if d.size else 0.0
        return v * (proto["PTV70"]["prescription"] / p) if p > 1e-9 else v

    w = normalise(w)
    for _ in range(400):
        pull = np.zeros(K)
        for n, m in tgt.items():
            cold = np.clip(proto[n]["prescription"] - (w @ At[n]), 0, None)
            if cold.sum() > 0:
                pull += (At[n] @ cold) / cold.sum()
        push = np.zeros(K)
        for n, Am in Ao.items():
            lim = proto[n].get("Dmax") or proto[n].get("Dmean")
            # Push from well below the limit, and hard: the cord abuts the
            # target in head and neck, so sparing it is the constraint that
            # actually shapes the plan.
            over = np.clip((w @ Am) - lim * 0.6, 0, None)
            if over.sum() > 0:
                push += 8.0 * (Am @ over) / over.sum()
        hot = np.clip((w @ Ab) - proto["PTV70"]["prescription"] * 1.02, 0, None)
        if hot.sum() > 0:
            push += 10.0 * (Ab @ hot) / hot.sum()
        drive = pull - push
        w = np.clip(w * np.exp(0.3 * drive / max(float(np.abs(drive).max()), 1e-12)),
                    1e-9, None)
        # Smooth along the leaf direction, per beam: a plan asking for a spike
        # in one leaf and nothing beside it is undeliverable, and it is also
        # how a single beamlet burns a hole nobody notices in the DVH.
        ncol = len(w) // len(ANGLES)
        f = w.reshape(len(ANGLES), ncol)
        kern = np.array([0.25, 0.5, 0.25])
        w = np.apply_along_axis(
            lambda r: np.convolve(r, kern, mode="same"), 1, f).reshape(-1)
        w = normalise(w)

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
