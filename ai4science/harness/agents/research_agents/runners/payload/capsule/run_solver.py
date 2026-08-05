"""Score each frame by an analytic haemoglobin prior.

Haemoglobin absorbs green far more than red, so the log ratio log(R) - log(G)
rises where blood is. The ratio also cancels illumination gain, which matters
because a capsule's lighting varies between devices and along the gut — an
absolute intensity carries that variation and a ratio does not.

The naive rival is plain green intensity: it sees the same absorption and the
same illumination changes, and cannot tell them apart. That comparison is the
point of the exercise, so both are emitted.

Reads frames and video ids. Labels are not in this workspace.
"""
import argparse, json, os
import numpy as np


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--workspace", default=".")
    ws = ap.parse_args().workspace
    X = np.load(os.path.join(ws, "data", "frames.npy"))
    T = np.load(os.path.join(ws, "data", "thumbs.npy")).astype(np.float32) / 255.0
    eps = 1e-6

    # P_blood is a PER-PIXEL quantity and a lesion covers a small part of the
    # frame, so the frame has to be summarised by how strong its strongest
    # region is, not by its average. Averaging first scored AUC 0.496 on real
    # frames — chance — while plain green intensity got 0.614: the mean washed
    # out exactly the signal the prior exists to find.
    pix = (np.log(np.clip(T[..., 0], eps, None))
           - np.log(np.clip(T[..., 1], eps, None)))
    # 95 was chosen by hand and never questioned. It is a knob now, so the
    # search can ask whether a lesion is better summarised by a higher or lower
    # quantile of the prior map.
    f = os.path.join(ws, "params.json")
    q = json.load(open(f))["percentile"] if os.path.exists(f) else 95.0
    p_blood = np.percentile(pix.reshape(len(pix), -1), q, axis=1)
    baseline = -X[:, 1]
    os.makedirs(os.path.join(ws, "results"), exist_ok=True)
    np.save(os.path.join(ws, "results", "scores.npy"), p_blood)
    np.save(os.path.join(ws, "results", "baseline_scores.npy"), baseline)
    print("scored", len(p_blood))


if __name__ == "__main__":
    main()
