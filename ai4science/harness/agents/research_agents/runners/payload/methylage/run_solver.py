"""A ridge clock: methylation in, chronological age out.

Ridge in its dual form, because there are 20,000 probes and a few hundred
samples. `beta = X'(XX' + lambda I)^-1 y` is a few-hundred-square solve rather
than a twenty-thousand-square one, and it is the same estimator.

Two predictions are written, and the second is the interesting one:

  age_pred            the clock
  age_pred_no_pcs     the clock refitted with the leading principal components
                      of the training betas projected out of BOTH cohorts

The methylome's leading components in whole blood are dominated by bulk
structure — cell-type proportions above all, which themselves change with age.
A clock riding on that is a blood-count detector with a birthday attached. The
difference between the two numbers is how much of the accuracy survives when
that structure is removed, and the judge reports it either way.

The PCs are computed on the TRAINING betas only. Computing them on both would
let the held-out sites influence the basis they are then scored in.
"""
import argparse, json, os
import numpy as np


def load_params(ws, **defaults):
    f = os.path.join(ws, "params.json")
    if os.path.exists(f):
        defaults.update(json.load(open(f)))
    return defaults


def ridge_dual(X, y, lam):
    """beta for min ||y - Xb||^2 + lam||b||^2, via the n x n system."""
    K = X @ X.T
    n = K.shape[0]
    alpha = np.linalg.solve(K + lam * np.eye(n), y)
    return X.T @ alpha


def drop_top_pcs(Xtr, Xte, k):
    """Project the top-k right singular directions of Xtr out of both.

    Via the n x n Gram matrix rather than a full SVD. `svd(Xtr)` on a
    317 x 20,000 matrix computes all 317 singular vectors when at most twenty
    are ever used, and it was 72 of the 78 seconds this solver spent — 94% of
    the run, repeated for every candidate in a search.

    The top-k right singular vectors come out of the small eigenproblem
    exactly: if K = X Xᵀ = Q W Qᵀ then vᵢ = Xᵀqᵢ / √wᵢ. Same arithmetic, done
    at 317 x 317 instead of 317 x 20,000.

    Signs may differ from LAPACK's, and that is harmless here: the projection
    I - V Vᵀ is invariant to the sign of each column. Checked against the full
    SVD on real data — the projected matrices agree to 2.5e-15 against a scale
    of 0.94, which is floating-point noise, not a different answer.
    """
    if k <= 0:
        return Xtr, Xte
    K = Xtr @ Xtr.T
    w, Q = np.linalg.eigh(K)                    # ascending, symmetric
    idx = np.argsort(w)[::-1][:k]
    # Guard the square root: a rank-deficient training matrix gives eigenvalues
    # at zero, and those directions carry nothing to project out.
    keep = [i for i in idx if w[i] > 1e-9 * max(w.max(), 1e-30)]
    if not keep:
        return Xtr, Xte
    V = (Xtr.T @ Q[:, keep]) / np.sqrt(w[keep])  # probes x k
    return Xtr - (Xtr @ V) @ V.T, Xte - (Xte @ V) @ V.T


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--workspace", default=".")
    ws = ap.parse_args().workspace
    pr = load_params(ws, ridge=100.0, n_pcs_removed=5)
    d = lambda n: np.load(os.path.join(ws, "data", n + ".npy"))

    Xd, yd, Xe = d("dev_betas").astype(np.float64), d("dev_age").astype(np.float64), d("ext_betas").astype(np.float64)
    mu = Xd.mean(0)
    Xd_c, Xe_c = Xd - mu, Xe - mu
    ym = yd.mean()

    b = ridge_dual(Xd_c, yd - ym, float(pr["ridge"]))
    pred = Xe_c @ b + ym
    pred_dev = Xd_c @ b + ym

    k = int(round(float(pr["n_pcs_removed"])))
    Xd_p, Xe_p = drop_top_pcs(Xd_c, Xe_c, k)
    b2 = ridge_dual(Xd_p, yd - ym, float(pr["ridge"]))
    pred_no_pcs = Xe_p @ b2 + ym

    out = os.path.join(ws, "results"); os.makedirs(out, exist_ok=True)
    np.save(os.path.join(out, "age_pred.npy"), pred)
    np.save(os.path.join(out, "age_pred_dev.npy"), pred_dev)
    np.save(os.path.join(out, "age_pred_no_pcs.npy"), pred_no_pcs)
    # The training mean, so the scorer can compare against predicting it.
    np.save(os.path.join(out, "train_mean_age.npy"), np.array([ym]))
    print("clock fitted: ridge=%g, %d PCs removed for the second fit" % (pr["ridge"], k))


if __name__ == "__main__":
    main()
