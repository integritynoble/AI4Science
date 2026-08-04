"""Inverse planning: per-beamlet fluence, optimised against the protocol.

Whole-beam weights cannot meet a protocol whose organ at risk abuts the target —
the only free choice is how much of each beam to use, and every beam that covers
the target also crosses the OAR. Modulating *within* the beam is the move the
field actually makes, and it is why IMRT exists.

So each beam is decomposed into beamlets (one per collimator column), and their
weights are found by projected gradient descent on the protocol's own cost:
cover the target, spare the organ, no hot spots. The protocol is input. Nothing
here can relax a constraint — an agent that could would make every plan pass,
and the passing plan is the one delivered.

The output is a plan CANDIDATE. There is no file this can write that means
approved; that is a physicist's signature and it does not live on disk here.
"""
import argparse, json, os
import numpy as np
from scipy.ndimage import gaussian_filter, rotate, shift as ndshift

N = 64
ANGLES = (0.0, 25.0, -25.0, 50.0, -50.0, 75.0, -75.0, 105.0, -105.0)
STRIDE = 2                      # collimator resolution


def beamlets(angle, cy, cx):
    """One dose map per open collimator column, aimed at (cy, cx)."""
    # A megavoltage percent-depth-dose curve: dose builds up from the surface
    # to d_max before attenuating. Skin sparing is the reason a 6 MV beam does
    # not burn the entrance, and modelling the entrance as the maximum — a bare
    # decaying exponential — invents a hot spot the machine does not produce.
    z = np.linspace(0.0, 1.0, N)
    depth = ((1.0 - np.exp(-z / 0.07)) * np.exp(-1.15 * z))[:, None]
    dy, dx = float(cy - N / 2), float(cx - N / 2)
    out = []
    for c in range(0, N, STRIDE):
        f = np.zeros((N, N))
        f[:, c:c + STRIDE] = 1.0
        f = gaussian_filter(f * depth, 1.1)
        f = rotate(f, angle, reshape=False, order=1)
        # Shift with zero fill, NOT np.roll: rolling is cyclic, so a beam
        # leaving the far side re-enters at row 0 and several beams pile their
        # phantom entrance dose on the same edge. That artefact read as a
        # 125 Gy hot spot while every target constraint looked fine.
        out.append(ndshift(f, (dy, dx), order=1, mode="constant", cval=0.0))
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--workspace", default=".")
    ws = ap.parse_args().workspace
    target = np.load(os.path.join(ws, "data", "target.npy"))
    oar = np.load(os.path.join(ws, "data", "oar.npy"))
    proto = json.load(open(os.path.join(ws, "data", "protocol.json")))
    ty, tx = np.argwhere(target).mean(axis=0)

    A = np.stack([b for a in ANGLES for b in beamlets(a, ty, tx)])   # (K, N, N)
    K = len(A)
    At, Ao, Ab = A[:, target], A[:, oar], A.reshape(K, -1)
    rx = proto["prescription"]
    # Multiplicative updates: a beamlet's weight is scaled up where it covers
    # cold target and down where it feeds the organ or a hot spot. Weights stay
    # positive by construction and the scale is fixed by renormalising to D95
    # every step, so every penalty is evaluated at the dose that will actually
    # be delivered. (An additive step with the same renormalisation oscillates
    # between collapse and overshoot — that is what produced NaN here.)
    l_oar, l_hot, eta = 2.5, 10.0, 0.35
    n_cols = N // STRIDE
    w = np.ones(K)

    def normalise(v):
        d95 = float(np.percentile(v @ At, 5))
        return v * (rx / d95) if np.isfinite(d95) and d95 > 1e-9 else v

    def smooth_fluence(v):
        """An MLC cannot deliver a spike in one leaf and nothing beside it, and
        a plan that asks for one is undeliverable. Smoothing along the leaf
        direction is standard IMRT practice, and here it is also what stops a
        single beamlet burning a 125 Gy hole in the entrance skin while every
        target constraint reads fine."""
        f = v.reshape(len(ANGLES), n_cols)
        k = np.array([0.25, 0.5, 0.25])
        f = np.apply_along_axis(lambda r: np.convolve(r, k, mode="same"), 1, f)
        return f.reshape(-1)

    w = normalise(w)
    for _ in range(300):
        dose_t, dose_o, dose_all = w @ At, w @ Ao, w @ Ab
        # Absolute violations in Gy. Normalising each term by its own sum — the
        # previous version — makes a 60 Gy overdose and a 0.1 Gy one pull with
        # the same force, which is why the hot spot never came down.
        cold = np.clip(rx - dose_t, 0, None)
        over = np.clip(dose_o - proto["oar_Dmean"], 0, None)
        hot = np.clip(dose_all - proto["hot_spot_max"] * 0.88, 0, None)
        # Each term normalised by the extent of its own violation, so a
        # constraint that is barely broken does not shout as loudly as one that
        # is broken badly, and none of them is drowned by voxel count.
        drive = ((At @ cold) / max(cold.sum(), 1e-9)
                 - l_oar * (Ao @ over) / max(over.sum(), 1e-9)
                 - l_hot * (Ab @ hot) / max(hot.sum(), 1e-9))
        scale = max(float(np.abs(drive).max()), 1e-12)
        w = np.clip(w * np.exp(eta * drive / scale), 1e-9, None)
        w = normalise(smooth_fluence(w))

    dose = np.tensordot(w, A, axes=(0, 0))
    os.makedirs(os.path.join(ws, "results"), exist_ok=True)
    np.save(os.path.join(ws, "results", "dose.npy"), dose)
    np.save(os.path.join(ws, "results", "fluence.npy"), w)
    with open(os.path.join(ws, "results", "plan_candidate.json"), "w") as f:
        json.dump({"status": "candidate",
                   "requires": "sign-off by a qualified medical physicist",
                   "beams": len(ANGLES), "beamlets": int(K),
                   "target_D95": float(np.percentile(dose[target], 5)),
                   "oar_Dmax": float(dose[oar].max()),
                   "oar_Dmean": float(dose[oar].mean()),
                   "hot_spot": float(dose.max())}, f)
    print("plan candidate written")


if __name__ == "__main__":
    main()
