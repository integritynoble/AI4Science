"""Fit a Cox proportional-hazards model on the development cohort.

Cox rather than a regression on log survival time, because most cases in a
real cohort are censored — alive at last follow-up — and a model that keeps
only the deaths throws away most of its data and all of its recent patients.
Partial likelihood uses a censored case for as long as it was observed, which
is the whole reason Cox exists.

Emits risk scores for both cohorts. No thresholds, no risk groups, no
eligibility, no advice — a score, and the judge decides what it is worth.
"""
import argparse, json, os
import numpy as np


def cox_fit(X, time, event, *, iters=800, lr=0.5, ridge=10.0):
    """Newton-free gradient ascent on the Breslow partial log-likelihood.

    The step is scaled by the gradient itself, divided by n — NOT normalised to
    unit length. An earlier version did `b += lr * g / ||g||`, which makes the
    step size independent of the gradient's magnitude and therefore swamps the
    ridge term: the penalty only changes the *direction*, so shrinkage did
    almost nothing until it was enormous. Coefficient norm held at 0.63 from
    ridge 0.001 to 25 and then collapsed at 200, instead of shrinking smoothly.
    Any conclusion about regularisation drawn from that optimiser was a
    conclusion about the optimiser.
    """
    order = np.argsort(-time)                 # descending: risk sets accumulate
    X, time, event = X[order], time[order], event[order]
    beta = np.zeros(X.shape[1])
    n = max(len(time), 1)
    for _ in range(iters):
        eta = np.clip(X @ beta, -30, 30)
        w = np.exp(eta)
        cw = np.cumsum(w)
        cwx = np.cumsum(w[:, None] * X, axis=0)
        idx = event == 1
        if not idx.any():
            break
        grad = (X[idx] - cwx[idx] / np.clip(cw[idx, None], 1e-12, None)).sum(axis=0)
        grad = (grad - 2.0 * ridge * beta) / n
        if not np.isfinite(grad).all():
            break
        beta = beta + lr * grad
        # A ridge large relative to n drives the update unstable rather than to
        # zero; at ridge 1000 the coefficients reached 1e13. Stop rather than
        # return a diverged fit that a C-index will happily score.
        if not np.isfinite(beta).all() or np.linalg.norm(beta) > 1e3:
            return np.zeros(X.shape[1])
    return beta


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--workspace", default=".")
    ws = ap.parse_args().workspace
    d = lambda n: np.load(os.path.join(ws, "data", n + ".npy"))
    Xd, td, ed = d("dev_X"), d("dev_time"), d("dev_event")
    f = os.path.join(ws, "params.json")
    pr = json.load(open(f)) if os.path.exists(f) else {}
    beta = cox_fit(Xd, td, ed, ridge=float(pr.get("ridge", 10.0)),
                   iters=int(round(float(pr.get("iters", 800)))),
                   lr=float(pr.get("lr", 0.5)))
    os.makedirs(os.path.join(ws, "results"), exist_ok=True)
    np.save(os.path.join(ws, "results", "risk_dev.npy"), Xd @ beta)
    np.save(os.path.join(ws, "results", "risk_ext.npy"), d("ext_X") @ beta)
    np.save(os.path.join(ws, "results", "coefficients.npy"), beta)
    print("cox fitted on %d cases, %d events" % (len(td), int(ed.sum())))


if __name__ == "__main__":
    main()
