"""Fit a risk score on the development cohort; emit risks for both cohorts.

No thresholds, no eligibility, no advice — a risk score and nothing else."""
import argparse, os
import numpy as np


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--workspace", default=".")
    ws = ap.parse_args().workspace
    d = lambda n: np.load(os.path.join(ws, "data", n + ".npy"))
    Xd, td, ed = d("dev_X"), d("dev_time"), d("dev_event")
    # A cheap proportional-hazards surrogate: regress the log event time on the
    # covariates among the uncensored, and negate to get risk.
    m = ed == 1
    A = np.hstack([Xd[m], np.ones((m.sum(), 1))])
    coef, *_ = np.linalg.lstsq(A, np.log(np.clip(td[m], 1e-6, None)), rcond=None)
    risk = lambda X: -(np.hstack([X, np.ones((len(X), 1))]) @ coef)
    os.makedirs(os.path.join(ws, "results"), exist_ok=True)
    np.save(os.path.join(ws, "results", "risk_dev.npy"), risk(Xd))
    np.save(os.path.join(ws, "results", "risk_ext.npy"), risk(d("ext_X")))
    print("risk scores written")


if __name__ == "__main__":
    main()
