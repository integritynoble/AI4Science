"""Ligand-based virtual screening: rank by similarity to the known actives.

Maximum Tanimoto similarity to the query set, per target — the oldest and still
one of the most competitive ligand-based baselines. It reads the query set,
which it is given, and never the labels, which it is not.
"""
import argparse, os
import numpy as np


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--workspace", default=".")
    ws = ap.parse_args().workspace
    d = lambda n: np.load(os.path.join(ws, "data", n + ".npy"))
    FP, tid, known = d("fingerprints").astype(bool), d("target_id"), d("known_active")

    scores = np.full(len(FP), -np.inf)
    for t in np.unique(tid):
        m = tid == t
        q = FP[m & (known == 1)]
        if len(q) == 0:
            scores[m] = 0.0
            continue
        F = FP[m]
        inter = F.astype(np.uint16) @ q.T.astype(np.uint16)
        union = F.sum(1)[:, None] + q.sum(1)[None, :] - inter
        tan = inter / np.clip(union, 1, None)
        scores[m] = tan.max(axis=1)          # nearest known active
    os.makedirs(os.path.join(ws, "results"), exist_ok=True)
    np.save(os.path.join(ws, "results", "scores.npy"), scores)
    print("scored", len(scores))


if __name__ == "__main__":
    main()
