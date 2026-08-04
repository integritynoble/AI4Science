"""A real head-and-neck case from OpenKBP: CT, contours, and a clinical plan.

The clinical dose is the answer key. It is what the patient was actually
treated with, it is the thing a planner is trying to match, and a planner that
could read it would be copying rather than planning — so it never enters the
sandbox, exactly like the reconstruction ground truth elsewhere.

The protocol is the real one for head and neck: prescription doses to three
target volumes, and the standard organ-at-risk limits (brainstem 54 Gy, cord
45 Gy, parotid mean 26 Gy, mandible 70 Gy). Those are clinical decisions made
by people accountable for them, and nothing in this system may relax one.
"""
import argparse, json, os, sys
import numpy as np

# Real head-and-neck constraints. Input, never tunable.
PROTOCOL = {
    "PTV70": {"prescription": 70.0, "D99_min": 66.5},
    "PTV63": {"prescription": 63.0, "D99_min": 59.9},
    "PTV56": {"prescription": 56.0, "D99_min": 53.2},
    "Brainstem": {"Dmax": 54.0},
    "SpinalCord": {"Dmax": 45.0},
    "LeftParotid": {"Dmean": 26.0},
    "RightParotid": {"Dmean": 26.0},
    "Mandible": {"Dmax": 70.0},
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default="."); ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    sys.path.insert(0, os.environ.get("AI4SCIENCE_PKG", ""))
    from ai4science.harness.agents.research_agents.runners import corpus
    root = corpus.OPENKBP.require()
    index = json.loads(open(os.path.join(root, "index.json")).read())

    # One patient, chosen by the seed: a different seed is a different case,
    # which is what makes a seed set here mean something.
    pids = sorted(index["patients"])
    pid = pids[a.seed % len(pids)]
    z = np.load(os.path.join(root, index["patients"][pid]["file"]))

    d = os.path.join(a.workspace, "data")
    os.makedirs(d, exist_ok=True)
    np.save(os.path.join(d, "ct.npy"), z["ct"])
    np.save(os.path.join(d, "possible.npy"), z["possible"])
    np.save(os.path.join(d, "spacing.npy"), z["spacing"])
    present = []
    for name in PROTOCOL:
        if name in z.files and z[name].any():
            np.save(os.path.join(d, "%s.npy" % name), z[name])
            present.append(name)
    np.save(os.path.join(d, "clinical_dose.npy"), z["dose"])      # withheld
    with open(os.path.join(d, "protocol.json"), "w") as f:
        json.dump({k: v for k, v in PROTOCOL.items() if k in present}, f)
    print(json.dumps({"patient": pid, "structures": present,
                      "shape": list(z["ct"].shape), "real": True}))


if __name__ == "__main__":
    main()
