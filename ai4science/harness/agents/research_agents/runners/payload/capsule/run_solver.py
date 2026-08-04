"""Score each frame by an analytic haemoglobin prior.

P_blood rises as green falls relative to red — the physics, computed from the
pixel rather than learned from labels the solver does not have."""
import argparse, os
import numpy as np


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--workspace", default=".")
    ws = ap.parse_args().workspace
    X = np.load(os.path.join(ws, "data", "frames.npy"))
    r, g, b = X[:, 0], X[:, 1], X[:, 2]
    p_blood = np.log(np.clip(r, 1e-6, None)) - np.log(np.clip(g, 1e-6, None))
    baseline = -g                       # "it looks darker" — the naive rival
    os.makedirs(os.path.join(ws, "results"), exist_ok=True)
    np.save(os.path.join(ws, "results", "scores.npy"), p_blood)
    np.save(os.path.join(ws, "results", "baseline_scores.npy"), baseline)
    print("scored", len(p_blood))


if __name__ == "__main__":
    main()
