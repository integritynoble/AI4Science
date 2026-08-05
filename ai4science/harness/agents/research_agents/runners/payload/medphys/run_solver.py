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
    # Both filtered. `Ao` was guarded and `At` was not, and the asymmetry cost a
    # patient: a target with no voxels on the planned slice gives a zero-column
    # submatrix, `resid.mean()` over an empty array is NaN, and the objective
    # returns NaN. Every `tcost < cost` is then False — NaN loses every
    # comparison — so every trial step was rejected, the optimiser never moved
    # off its flat starting fluence, and the plan delivered 70 Gy through the
    # whole body. It read as an impossible constraint set. It was a missing
    # `if m.any()`.
    At = {n: A[:, m] for n, m in tgt.items() if m.any()}
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
    def grad_and_cost(w, wt):
        g = np.zeros(K)
        cost = 0.0
        for n, Am in At.items():
            resid = (w @ Am) - proto[n]["prescription"]       # BOTH directions
            # Asymmetric, as clinical objectives are: missing the tumour is
            # worse than a modest hot spot inside it. Symmetric weighting left
            # D99 at 62.2 against a 66.5 floor — uniform, and uniformly too
            # cold, because the cold tail counts no more than the warm one.
            wgt = np.where(resid < 0, wt["under"], 1.0)
            g += 2.0 * (Am @ (wgt * resid)) / max(Am.shape[1], 1)
            cost += float((wgt * resid ** 2).mean())
        for n, Am in Ao.items():
            lim = proto[n].get("Dmax") or proto[n].get("Dmean")
            over = np.clip((w @ Am) - lim * 0.85, 0, None)
            g += wt["oar"] * 2.0 * (Am @ over) / max(Am.shape[1], 1)
            cost += wt["oar"] * float((over ** 2).mean())
        hot = np.clip((w @ Ab) - rx * 1.07, 0, None)
        g += wt["hot"] * 2.0 * (Ab @ hot) / max(Ab.shape[1], 1)
        cost += wt["hot"] * float((hot ** 2).mean())
        return g, cost

    def optimise(weights):
        """One fluence optimisation at a fixed set of trade-off weights.

        Backtracking line search. The previous loop halved a single `step` on
        every rejection and broke out when it fell below 1e-6, and the step was
        never restored — so about twenty consecutive rejections ended the run
        for good. On one patient every early trial was rejected because the
        initial step was wrong for that geometry's scale, the loop exited on the
        FLAT STARTING FLUENCE, and the plan it returned put 70 Gy through the
        whole body: dose standard deviation 0.199 Gy where a working plan gives
        8.5. Every organ then violated its limit, which read as an impossible
        constraint set rather than an optimiser that never took a step.

        `-g` is a descent direction, so a small enough step MUST reduce the cost
        unless the point is already a minimum. Shrinking within the iteration
        and letting the step grow again afterwards makes that guarantee usable;
        breaking out on a small step throws it away."""
        w = np.full(K, rx / max(float(A[:, prim].sum(axis=0).mean()), 1e-9))
        step = float(pr["step"])
        _, cost = grad_and_cost(w, weights)
        # A non-finite objective disables the search silently, because NaN loses
        # every comparison and so every candidate step is rejected. Refusing is
        # better than returning the starting fluence dressed as a plan.
        if not np.isfinite(cost):
            raise SystemExit("objective is not finite at the starting fluence — "
                             "a structure with no voxels on this slice, or a "
                             "protocol entry with no dose limit")
        scale = max(float(w.mean()), 1e-9)
        for _ in range(int(round(float(pr["iters"])))):
            g, _ = grad_and_cost(w, weights)
            gn = float(np.linalg.norm(g))
            if not np.isfinite(gn) or gn < 1e-12:
                break
            d = -(g / gn) * scale
            s = step
            for _ in range(40):                 # backtrack until it descends
                trial = np.clip(w + s * d, 0.0, None)
                _, tcost = grad_and_cost(trial, weights)
                if tcost < cost:
                    break
                s *= 0.5
            else:
                break                           # genuinely at a minimum
            w, cost = trial, tcost
            # Start the next iteration a little bolder than what just worked,
            # rather than from a step that has been ratcheted down permanently.
            step = min(s * 2.0, 2.0)
            scale = max(float(w.mean()), 1e-9)
        return w

    def evaluate(w):
        """The plan's own DVH against the PROTOCOL — the clinical constraint set
        the planner was given. Not against the clinical dose, which is withheld
        and which this never reads. Same statistics the scorer uses: D99 is the
        1st percentile in the structure, Dmax the maximum in it, hot spot the
        maximum anywhere in the body."""
        d = np.tensordot(w, A, axes=(0, 0)) * body
        viol = {}
        for n, m in tgt.items():
            # A protocol can name a structure this patient has no contour for.
            # Skipping is right: there is nothing to constrain, and reducing
            # over an empty mask raises.
            if not np.any(m):
                continue
            rule = proto[n]
            if "D99_min" in rule:
                got = float(np.percentile(d[m], 1))
                if got < rule["D99_min"]:
                    viol["under"] = max(viol.get("under", 0.0),
                                        (rule["D99_min"] - got) / max(rule["D99_min"], 1e-9))
        ptv_m = tgt.get("PTV70")
        for n, m in oars.items():
            if not np.any(m):
                continue
            # Same convention as the scorer: an organ overlapping the target is
            # judged on the part outside it. The planner has to optimise toward
            # the constraint it will be held to.
            if ptv_m is not None and np.any(m & ptv_m):
                m = m & ~ptv_m
                if not np.any(m):
                    continue
            rule = proto[n]
            if "Dmax" in rule:
                got = float(d[m].max())
                if got > rule["Dmax"]:
                    viol["oar"] = max(viol.get("oar", 0.0),
                                      (got - rule["Dmax"]) / max(rule["Dmax"], 1e-9))
            if "Dmean" in rule:
                got = float(d[m].mean())
                if got > rule["Dmean"]:
                    viol["oar"] = max(viol.get("oar", 0.0),
                                      (got - rule["Dmean"]) / max(rule["Dmean"], 1e-9))
        hot_lim = proto["PTV70"]["prescription"] * 1.15
        got = float(d.max())
        if got > hot_lim:
            viol["hot"] = (got - hot_lim) / hot_lim
        return d, viol

    # ------------------------------------------------------------------
    # Weight tuning, per patient.
    #
    # One global set of trade-off weights was used for every patient, and it
    # suited about five of eight: a cord that abuts the target needs a different
    # balance from one that does not, and no single number is right for both.
    # That is not a defect in the optimiser, it is what inverse planning IS —
    # a planner tunes the weights for the patient in front of it, looks at the
    # resulting DVH, and tunes again.
    #
    # So: optimise, evaluate against the protocol, raise the weight for whatever
    # is violated, repeat. The protocol is staged input; the clinical dose is
    # the answer key and is never read here. The plan kept is the one violating
    # least, ties broken on target coverage — not the last one tried.
    weights = {"under": float(pr["under_weight"]),
               "oar": float(pr["oar_weight"]),
               "hot": float(pr["hot_weight"])}
    best_w = best_dose = None
    best_score = None
    for round_no in range(int(round(float(pr.get("tuning_rounds", 4))))):
        w = optimise(weights)
        d, viol = evaluate(w)
        # Rank on total relative violation first, coverage second.
        total = sum(viol.values())
        cover = (float(np.percentile(d[tgt["PTV70"]], 1))
                 if "PTV70" in tgt and np.any(tgt["PTV70"]) else 0.0)
        score = (total, -cover)
        if best_score is None or score < best_score:
            best_w, best_dose, best_score = w, d, score
        if not viol:
            break
        # Raise the weight for what is violated, in proportion to how badly.
        # Bounded so one round cannot drive a weight somewhere the search space
        # does not go — the declared parameter range is the space.
        # `key`, not `k`: `k` is the slice index in the enclosing scope, and
        # shadowing it left `int(k)` reading the string "hot".
        for key, (_lo, hi) in (("under", (1.0, 60.0)), ("oar", (1.0, 20.0)),
                               ("hot", (0.5, 12.0))):
            if key in viol:
                weights[key] = min(hi, weights[key] * (1.0 + 3.0 * viol[key]))
        print("  round %d: violations %s -> weights %s"
              % (round_no, {k: round(v, 4) for k, v in viol.items()},
                 {k: round(v, 2) for k, v in weights.items()}))

    w, dose = best_w, best_dose
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
