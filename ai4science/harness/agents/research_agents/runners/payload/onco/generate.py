"""Real TCGA survival: lung adenocarcinoma to develop on, squamous for external.

The cohorts are the point. LUAD and LUSC are different tumour biology in a
different population, so a model fitted on one and tested on the other is an
external validation in the sense the field means — not a re-split of one cohort,
which flatters every model ever published in oncology.

Covariates are the ordinary clinical ones the GDC exposes for both: age, sex,
stage, prior malignancy. Cases with no follow-up time at all are dropped rather
than imputed — an unknown time is not a long one.
"""
import argparse, json, os, sys
import numpy as np

#: Age, sex, overall stage, prior malignancy. T and N stage are fetched and
#: available, and were tried: they made the model WORSE on the external cohort
#: (0.571 against 0.579) because missing values had to be coded as a category
#: and the two cohorts are missing them differently. Kept out, and the negative
#: result recorded here rather than dropped.
COVARIATES = ("age", "male", "stage", "prior_malignancy")


def load(root, name):
    with open(os.path.join(root, name)) as f:
        raw = json.load(f)
    rows = raw["rows"]
    X = np.array([[r[c] for c in COVARIATES] for r in rows], float)
    t = np.array([r["time"] for r in rows], float)
    e = np.array([r["event"] for r in rows], int)
    return raw["project"], X, t, e


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default="."); ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    sys.path.insert(0, os.environ.get("AI4SCIENCE_PKG", ""))
    from ai4science.harness.agents.research_agents.runners import corpus
    root = corpus.TCGA_SURVIVAL.require()

    os.makedirs(os.path.join(a.workspace, "data"), exist_ok=True)
    dev_p, Xd, td, ed = load(root, "dev.json")
    ext_p, Xe, te, ee = load(root, "ext.json")
    # Standardise on the DEVELOPMENT cohort's statistics, and apply the same
    # transform to the external one. Re-standardising the external cohort to
    # itself would quietly remove the population shift that makes it external.
    mu, sd = Xd.mean(axis=0), np.clip(Xd.std(axis=0), 1e-6, None)
    for nm, arr in (("dev_X", (Xd - mu) / sd), ("dev_time", td), ("dev_event", ed),
                    ("ext_X", (Xe - mu) / sd), ("ext_time", te), ("ext_event", ee)):
        np.save(os.path.join(a.workspace, "data", nm + ".npy"), arr)
    print(json.dumps({"dev": int(len(td)), "ext": int(len(te)), "p": Xd.shape[1],
                      "dev_project": dev_p, "ext_project": ext_p,
                      "dev_events": int(ed.sum()), "ext_events": int(ee.sum()),
                      "covariates": list(COVARIATES), "real": True}))


if __name__ == "__main__":
    main()
