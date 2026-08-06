"""A 3D inverse treatment planner: fluence in, dose volume out.

**This plans the whole volume, not one axial slice.** The slice version could
not spare an organ sitting above or below the target, and a cord that abuts the
PTV in 3D looked adjacent-or-absent depending on which slice was picked. Every
number it produced was a statement about one plane, reported as a statement
about a patient.

The dose kernel is deliberately simple and stated plainly: exponential depth
attenuation along the ray, a lateral Gaussian for penumbra, and a Gaussian
extent along the superior-inferior axis. **This is not a Monte Carlo engine.**
What matters for a benchmark is that the operator is fixed, shared between
generation and scoring, and unreachable by the agent.

**The geometry is separable, and that is what makes 3D affordable.** The beams
are coplanar -- they rotate about the superior-inferior axis -- so a beamlet's
in-plane pattern is the same at every z, and its z-extent does not depend on x
or y. A 3D beamlet is therefore the outer product of a 2D field and a 1D
profile, so building the operator costs a few hundred 2D rotations rather than
thousands of 3D ones.

**Everything in the hot loop is float32, and that is part of the algorithm.** A
float64 weight vector against a float32 operator makes numpy upcast the whole
matrix on every matvec. Measured on this machine: 462 ms per matvec against
13 ms -- a factor of 35 -- which took one plan from under a minute to over
twenty. It was diagnosed by guessing twice and measuring once, which is the
wrong order.
"""
import argparse, json, os
import numpy as np
from scipy.ndimage import gaussian_filter, rotate, shift as ndshift


def load_params(ws, **defaults):
    f = os.path.join(ws, "params.json")
    if os.path.exists(f):
        defaults.update(json.load(open(f)))
    return defaults


ANGLES = tuple(range(0, 360, 40))     # 9 coplanar beams
LAT_STRIDE = 10                       # in-plane beamlet width, voxels
N_Z = 8                               # beamlet divisions along z
Z_SIGMA = 2.2                         # z penumbra, voxels
#: Cap on voxels entering the optimisation. Every structure voxel is kept; the
#: rest of the body is subsampled so a night stays finite. Declared here rather
#: than buried, because it is a modelling choice: the hot-spot term is computed
#: on a body sample, and the final dose is evaluated on all of it.
MAX_OPT_VOXELS = 32000


def inplane_fields(shape2d, angle, cy, cx):
    """Per-column fields through one axial plane, aimed at (cy, cx).

    The aim is the whole point and was missing in the first version of this:
    without the shift every beam converges on the image centre instead of the
    tumour, which put 2144 Gy in the middle of a patient's neck while every
    target constraint still read as met."""
    ny, nx = shape2d
    z = np.linspace(0.0, 1.0, ny)
    depth = ((1.0 - np.exp(-z / 0.07)) * np.exp(-1.1 * z))[:, None]
    dy, dx = float(cy - ny / 2.0), float(cx - nx / 2.0)
    out = []
    for c in range(0, nx, LAT_STRIDE):
        f = np.zeros((ny, nx))
        f[:, c:c + LAT_STRIDE] = 1.0
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
    possible = np.load(dpath("possible.npy")).astype(bool)
    have = lambda n: os.path.exists(dpath("%s.npy" % n))
    tgt_vol = {n: np.load(dpath("%s.npy" % n)).astype(bool) for n in proto
               if n.startswith("PTV") and have(n)}
    oar_vol = {n: np.load(dpath("%s.npy" % n)).astype(bool) for n in proto
               if not n.startswith("PTV") and have(n)}
    if "PTV70" not in tgt_vol or not tgt_vol["PTV70"].any():
        raise SystemExit("no PTV70 in this volume")

    # The voxel set: the deliverable body plus every structure voxel, so a
    # contour reaching past `possible` is still constrained rather than lost.
    V = possible.copy()
    for m in list(tgt_vol.values()) + list(oar_vol.values()):
        V |= m
    yi, xi, zi = np.nonzero(V)
    nvox = yi.size
    ny, nx, nz = V.shape
    lin = np.full(V.shape, -1, np.int64)
    lin[yi, xi, zi] = np.arange(nvox)
    tgt = {n: lin[m].ravel() for n, m in tgt_vol.items() if m.any()}
    oars = {n: lin[m].ravel() for n, m in oar_vol.items() if m.any()}

    cy, cx = np.argwhere(tgt_vol["PTV70"])[:, :2].mean(axis=0)
    zr = np.flatnonzero(V.any(axis=(0, 1)))
    z_centres = np.linspace(zr.min(), zr.max(), N_Z)

    # The operator, built factored and gathered straight onto the voxel set.
    # A beamlet's row is the elementwise product of its in-plane field at the
    # voxel's (y, x) and its z profile at the voxel's z -- which is what
    # "coplanar" means geometrically.
    zprof = np.exp(-0.5 * ((zi[None, :] - z_centres[:, None]) / Z_SIGMA) ** 2
                   ).astype(np.float32)
    rows = []
    for ang in ANGLES:
        for f in inplane_fields((ny, nx), ang, cy, cx):
            fp = f[yi, xi].astype(np.float32)
            for v in range(N_Z):
                rows.append(fp * zprof[v])
    A_full = np.asarray(rows, dtype=np.float32)          # (K, nvox)
    K = A_full.shape[0]

    keep = np.zeros(nvox, bool)
    for arr in list(tgt.values()) + list(oars.values()):
        keep[arr] = True
    budget = MAX_OPT_VOXELS - int(keep.sum())
    rest = np.flatnonzero(~keep)
    if budget > 0:
        sel = rest[:: max(1, rest.size // budget)] if rest.size > budget else rest
        keep[sel] = True
    opt = np.flatnonzero(keep)
    pos = np.full(nvox, -1, np.int64)
    pos[opt] = np.arange(opt.size)
    A = np.ascontiguousarray(A_full[:, opt])

    # Both filtered. `Ao` was guarded and `At` was not, and the asymmetry cost a
    # patient: a target with no voxels gives a zero-column submatrix,
    # `resid.mean()` over an empty array is NaN, the objective returns NaN, and
    # every `tcost < cost` is then False because NaN loses every comparison. The
    # optimiser never moved off its flat starting fluence and the plan delivered
    # 70 Gy through the whole body. It read as an impossible constraint set. It
    # was a missing `if m.any()`.
    #
    # The 3D scoping note predicted this guard would look unnecessary here,
    # because structures are far less likely to be empty in a volume, and that
    # someone would remove it. It stays.
    At = {n: np.ascontiguousarray(A[:, pos[a]]) for n, a in tgt.items() if a.size}
    Ao = {n: np.ascontiguousarray(A[:, pos[a]]) for n, a in oars.items() if a.size}
    rx = np.float32(proto["PTV70"]["prescription"])
    prim_cols = pos[tgt["PTV70"]]
    pr = load_params(ws, oar_weight=6.0, hot_weight=3.0, step=0.6, iters=250,
                     under_weight=20.0, cold_weight=8.0, tuning_rounds=2)

    # A TWO-SIDED objective. An earlier cost penalised target UNDERDOSE only, so
    # nothing pushed the dose down and normalising D99 dragged the whole volume
    # up with it: target mean 101.9 Gy against a 70 Gy prescription. The plan
    # met D99 because D99 is the COLDEST percentile, which is exactly the
    # statistic that cannot see an overdose.
    def _terms(w, wt, want_grad):
        """Cost, and the gradient only when it is asked for.

        The line search needs the cost of a trial point and nothing else.
        Computing the gradient there as well doubled the matvecs in the hottest
        loop in the program — one wasted `Am @ vec` per structure per trial,
        and a trial happens several times per iteration.
        """
        w = np.asarray(w, np.float32)
        g = np.zeros(K, np.float32) if want_grad else None
        cost = 0.0
        for n, Am in At.items():
            resid = (w @ Am) - np.float32(proto[n]["prescription"])
            # Asymmetric, as clinical objectives are: missing the tumour is
            # worse than a modest hot spot inside it.
            wgt = np.where(resid < 0, np.float32(wt["under"]), np.float32(1.0))
            if want_grad:
                g += np.float32(2.0) * (Am @ (wgt * resid)) / max(Am.shape[1], 1)
            cost += float((wgt * resid ** 2).mean())
            # A cold-tail term, on the constraint as it is actually written. The
            # criterion is D99 >= floor: the coldest one percent. A mean of
            # squares barely sees a handful of cold edge voxels, and raising
            # `under` lifts the whole distribution -- mean dose and hot spot
            # with it -- without touching the tail that decides the verdict.
            floor = proto[n].get("D99_min")
            if floor:
                cold = np.clip(np.float32(floor) - (w @ Am), 0.0, None)
                if want_grad:
                    g -= np.float32(wt["cold"] * 2.0) * (Am @ cold) / max(Am.shape[1], 1)
                cost += wt["cold"] * float((cold ** 2).mean())
        for n, Am in Ao.items():
            lim = np.float32((proto[n].get("Dmax") or proto[n].get("Dmean")) * 0.85)
            over = np.clip((w @ Am) - lim, 0, None)
            if want_grad:
                g += np.float32(wt["oar"] * 2.0) * (Am @ over) / max(Am.shape[1], 1)
            cost += wt["oar"] * float((over ** 2).mean())
        hot = np.clip((w @ A) - rx * np.float32(1.07), 0, None)
        if want_grad:
            g += np.float32(wt["hot"] * 2.0) * (A @ hot) / max(A.shape[1], 1)
        cost += wt["hot"] * float((hot ** 2).mean())
        return g, cost

    def grad_and_cost(w, wt):
        return _terms(w, wt, True)

    def cost_only(w, wt):
        return _terms(w, wt, False)[1]

    def optimise(weights):
        """One fluence optimisation at a fixed set of trade-off weights.

        Backtracking line search. An earlier loop halved a single `step` on
        every rejection and never restored it, so about twenty consecutive
        rejections ended the run for good -- on one patient it exited on the
        FLAT STARTING FLUENCE and returned a plan with dose standard deviation
        0.199 Gy where a working plan gives 8.5. Every organ then violated its
        limit, which read as an impossible constraint set rather than as an
        optimiser that never took a step.

        `-g` is a descent direction, so a small enough step MUST reduce the cost
        unless the point is already a minimum. Shrinking within the iteration
        and letting the step grow again afterwards makes that guarantee usable;
        breaking out on a small step throws it away."""
        w = np.full(K, rx / max(float(A[:, prim_cols].sum(axis=0).mean()), 1e-9),
                    dtype=np.float32)
        step = float(pr["step"])
        _, cost = grad_and_cost(w, weights)
        # A non-finite objective disables the search silently, because NaN loses
        # every comparison and so every candidate step is rejected. Refusing is
        # better than returning the starting fluence dressed as a plan.
        if not np.isfinite(cost):
            raise SystemExit("objective is not finite at the starting fluence — "
                             "a structure with no voxels, or a protocol entry "
                             "with no dose limit")
        scale = max(float(w.mean()), 1e-9)
        for _ in range(int(round(float(pr["iters"])))):
            g, _ = grad_and_cost(w, weights)
            gn = float(np.linalg.norm(g))
            if not np.isfinite(gn) or gn < 1e-12:
                break
            d = (-(g / np.float32(gn)) * np.float32(scale)).astype(np.float32)
            s = step
            for _ in range(40):               # backtrack until it descends
                trial = np.clip(w + np.float32(s) * d, 0.0, None)
                tcost = cost_only(trial, weights)
                if tcost < cost:
                    break
                s *= 0.5
            else:
                break                         # genuinely at a minimum
            w, cost = trial, tcost
            step = min(s * 2.0, 2.0)
            scale = max(float(w.mean()), 1e-9)
        return w

    def evaluate(w):
        """The plan's own DVH against the PROTOCOL -- the clinical constraint
        set the planner was given. Never against the clinical dose, which is
        withheld and which this never reads."""
        vol = np.zeros(V.shape, np.float64)
        vol[yi, xi, zi] = np.asarray(w, np.float32) @ A_full
        viol = {}
        for n, m in tgt_vol.items():
            fl = proto[n].get("D99_min")
            if m.any() and fl:
                viol[n] = float(fl - np.percentile(vol[m], 1))
        for n, m in oar_vol.items():
            if not m.any():
                continue
            d = vol[m]
            if "Dmax" in proto[n]:
                viol[n] = float(d.max() - proto[n]["Dmax"])
            elif "Dmean" in proto[n]:
                viol[n] = float(d.mean() - proto[n]["Dmean"])
        viol["hot_spot"] = float(vol[V].max() - float(rx) * 1.07)
        return vol, viol

    # Per-patient weight tuning: geometry differs between patients more than any
    # one weight set can absorb. Tuned against the protocol, never against the
    # clinical dose.
    wt = {"under": float(pr["under_weight"]), "oar": float(pr["oar_weight"]),
          "hot": float(pr["hot_weight"]), "cold": float(pr["cold_weight"])}
    best = None
    for _ in range(max(1, int(round(float(pr["tuning_rounds"]))))):
        w = optimise(wt)
        vol, viol = evaluate(w)
        worst = max(viol.values()) if viol else 0.0
        if best is None or worst < best[0]:
            best = (worst, w, vol, dict(wt))
        if worst <= 0:
            break
        t_worst = max((v for n, v in viol.items() if n in tgt_vol), default=0.0)
        o_worst = max((v for n, v in viol.items() if n not in tgt_vol), default=0.0)
        if t_worst >= o_worst:
            wt["cold"] *= 1.6
            wt["under"] *= 1.3
        else:
            wt["oar"] *= 1.6
            wt["hot"] *= 1.3

    worst, w, vol, used = best
    out = os.path.join(ws, "results")
    os.makedirs(out, exist_ok=True)
    np.save(os.path.join(out, "dose.npy"), vol)
    np.save(os.path.join(out, "fluence.npy"), w)
    with open(os.path.join(out, "plan.json"), "w") as f:
        json.dump({"angles": list(ANGLES), "beamlets": int(K), "volumetric": True,
                   "shape": list(V.shape), "n_voxels": int(nvox),
                   "n_opt_voxels": int(opt.size), "z_beamlets": N_Z,
                   "weights": used, "worst_violation_gy": worst}, f)
    print("3D plan: %d beamlets over %d angles, %d voxels (%d optimised), "
          "worst violation %.2f Gy" % (K, len(ANGLES), nvox, opt.size, worst))


if __name__ == "__main__":
    main()
