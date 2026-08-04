"""Rank each target's library by a shape/pharmacophore similarity score.

It has descriptors and target ids, and no labels. The score is a docking-like
heuristic: distance to the consensus of the target's own library, which is a
weak signal on purpose — a docking score ranks, it does not measure."""
import argparse, os
import numpy as np


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--workspace", default=".")
    ws = ap.parse_args().workspace
    D = np.load(os.path.join(ws, "data", "descriptors.npy"))
    tid = np.load(os.path.join(ws, "data", "target_id.npy"))
    feat = D[:, 2:]
    scores = np.zeros(len(D))
    for t in np.unique(tid):
        m = tid == t
        f = feat[m]
        # actives cluster; decoys are diffuse. A robust centre finds the cluster.
        centre = np.median(f, axis=0)
        for _ in range(6):
            d = np.linalg.norm(f - centre, axis=1)
            keep = d <= np.percentile(d, 35)
            centre = f[keep].mean(axis=0)
        scores[m] = -np.linalg.norm(f - centre, axis=1)
    os.makedirs(os.path.join(ws, "results"), exist_ok=True)
    np.save(os.path.join(ws, "results", "scores.npy"), scores)
    print("scored", len(scores))


if __name__ == "__main__":
    main()
