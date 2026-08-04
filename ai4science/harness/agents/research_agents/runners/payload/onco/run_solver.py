"""Fit a Cox proportional-hazards model on the development cohort.

Cox rather than a regression on log survival time, because most cases in a
real cohort are censored — alive at last follow-up — and a model that keeps
only the deaths throws away most of its data and all of its recent patients.
Partial likelihood uses a censored case for as long as it was observed, which
is the whole reason Cox exists.

Emits risk scores for both cohorts. No thresholds, no risk groups, no
eligibility, no advice — a score, and the judge decides what it is worth.
"""
import argparse, os
import numpy as np


def cox_fit(X, time, event, *, iters=400, lr=0.35, ridge=1e-3):
    """Newton-free gradient ascent on the Breslow partial log-likelihood."""
    order = np.argsort(-time)                 # descending: risk sets accumulate
    X, time, event = X[order], time[order], event[order]
    beta = np.zeros(X.shape[1])
    for _ in range(iters):
        eta = np.clip(X @ beta, -30, 30)
        w = np.exp(eta)
        cw = np.cumsum(w)                     # sum over the risk set
        cwx = np.cumsum(w[:, None] * X, axis=0)
        idx = event == 1
        if not idx.any():
            break
        grad = (X[idx] - cwx[idx] / np.clip(cw[idx, None], 1e-12, None)).sum(axis=0)
        grad -= 2 * ridge * beta
        g = np.linalg.norm(grad)
        if not np.isfinite(g) or g < 1e-8:
            break
        beta += lr * grad / max(g, 1e-9)
    return beta


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--workspace", default=".")
    ws = ap.parse_args().workspace
    d = lambda n: np.load(os.path.join(ws, "data", n + ".npy"))
    Xd, td, ed = d("dev_X"), d("dev_time"), d("dev_event")
    beta = cox_fit(Xd, td, ed)
    os.makedirs(os.path.join(ws, "results"), exist_ok=True)
    np.save(os.path.join(ws, "results", "risk_dev.npy"), Xd @ beta)
    np.save(os.path.join(ws, "results", "risk_ext.npy"), d("ext_X") @ beta)
    np.save(os.path.join(ws, "results", "coefficients.npy"), beta)
    print("cox fitted on %d cases, %d events" % (len(td), int(ed.sum())))


if __name__ == "__main__":
    main()
