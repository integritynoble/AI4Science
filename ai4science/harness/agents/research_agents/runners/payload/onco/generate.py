"""Two cohorts: development, and an external one that does not look like it.

The external cohort is the point. Prognostic models in oncology fail on external
validation at a famous rate, and a benchmark with only an internal split cannot
show it."""
import argparse, json, os
import numpy as np

N_DEV, N_EXT, P = 400, 300, 6


def cohort(rng, n, shift, beta):
    X = rng.normal(shift, 1.0, (n, P))
    risk = X @ beta
    t = rng.exponential(np.exp(-risk) * 40.0)
    censor = rng.exponential(60.0, n)
    obs = np.minimum(t, censor)
    return X, obs, (t <= censor).astype(int)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default="."); ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args(); rng = np.random.default_rng(a.seed)
    os.makedirs(os.path.join(a.workspace, "data"), exist_ok=True)
    beta = np.array([0.9, -0.6, 0.4, 0.0, 0.0, 0.25])
    Xd, td, ed = cohort(rng, N_DEV, 0.0, beta)
    # different population: shifted covariates and a weaker effect
    Xe, te, ee = cohort(rng, N_EXT, 0.45, beta * 0.7)
    for nm, arr in (("dev_X", Xd), ("dev_time", td), ("dev_event", ed),
                    ("ext_X", Xe), ("ext_time", te), ("ext_event", ee)):
        np.save(os.path.join(a.workspace, "data", nm + ".npy"), arr)
    print(json.dumps({"dev": N_DEV, "ext": N_EXT, "p": P, "seed": a.seed}))


if __name__ == "__main__":
    main()
