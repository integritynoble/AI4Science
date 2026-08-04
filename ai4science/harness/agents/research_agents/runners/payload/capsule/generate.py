"""Capsule endoscopy frames with a haemoglobin-like signature.

Patients, not frames, are the unit — consecutive frames from one patient are
near-duplicates, so the split is by patient and the generator emits the patient
id alongside every frame."""
import argparse, json, os
import numpy as np

PATIENTS, PER_PATIENT = 24, 18


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default="."); ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed)
    os.makedirs(os.path.join(a.workspace, "data"), exist_ok=True)

    X, y, pid = [], [], []
    for p in range(PATIENTS):
        # per-patient illumination and tissue tone: the nuisance variation that
        # makes a frame-level split flatter every model that sees it
        tone = rng.normal(0.55, 0.05, 3)
        # Illumination varies a lot between capsules and between
        # positions in the gut. That is precisely why an absolute
        # intensity is a poor feature and a channel RATIO is not:
        # gain cancels in the ratio and does not cancel in `-g`.
        gain = rng.lognormal(0.0, 0.30)
        for f in range(PER_PATIENT):
            bleeding = int(rng.random() < 0.30)
            px = rng.normal(tone, 0.05, 3) * gain
            if bleeding:
                # haemoglobin absorbs green far more than red
                px = px * np.array([1.02, 0.80, 0.93]) + rng.normal(0, 0.012, 3)
            px = np.clip(px + rng.normal(0, 0.02, 3), 1e-3, None)
            X.append(px); y.append(bleeding); pid.append(p)
    np.save(os.path.join(a.workspace, "data", "frames.npy"), np.array(X))
    np.save(os.path.join(a.workspace, "data", "patient_id.npy"), np.array(pid))
    np.save(os.path.join(a.workspace, "data", "labels.npy"), np.array(y))  # withheld
    print(json.dumps({"patients": PATIENTS, "frames": len(X), "seed": a.seed}))


if __name__ == "__main__":
    main()
