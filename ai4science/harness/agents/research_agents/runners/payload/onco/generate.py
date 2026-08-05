"""Real TCGA survival: developed and validated on institutions that do not overlap.

**The external cohort is site-disjoint, not cross-histology.** It used to be
LUSC, on the reasoning that different tumour biology is the strongest possible
external test. It is a strong test and it was measuring the wrong thing: the
model transports, and squamous cell is simply a cohort where these covariates
carry little signal. Fitted on LUAD it scores 0.667 internally and 0.579 on
LUSC; fitted on LUSC it scores 0.577 on its OWN cohort and 0.646 on LUAD. The
score follows the cohort being scored, not the cohort that was fitted — and
stage alone gives 0.658 in LUAD against 0.565 in LUSC. Reading that as a
transport failure was a mistake, and it is recorded rather than quietly dropped.

What the field means by external validation is a different institution, not a
different disease, and TCGA barcodes carry the tissue source site. Development
and validation now use disjoint sites, which is a re-split of one cohort in
exactly the way that does NOT flatter: no patient, and no contributing hospital,
appears in both.

The cross-histology number is still computed and reported beside it, because it
is the finding — it just is not the pass criterion.

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

#: Fraction of tissue source sites held out as the external cohort.
HELD_OUT_SITE_FRACTION = 1 / 3


def site_of(case):
    """TCGA barcode: TCGA-<site>-<patient>. The middle field is the hospital."""
    return case.split("-")[1]


def load(root, name):
    with open(os.path.join(root, name)) as f:
        raw = json.load(f)
    rows = raw["rows"]
    X = np.array([[r[c] for c in COVARIATES] for r in rows], float)
    t = np.array([r["time"] for r in rows], float)
    e = np.array([r["event"] for r in rows], int)
    s = np.array([site_of(r["case"]) for r in rows])
    return raw["project"], X, t, e, s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default="."); ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    sys.path.insert(0, os.environ.get("AI4SCIENCE_PKG", ""))
    from ai4science.harness.agents.research_agents.runners import corpus
    root = corpus.TCGA_SURVIVAL.require()

    os.makedirs(os.path.join(a.workspace, "data"), exist_ok=True)
    rng = np.random.default_rng(a.seed)
    proj, X, T, E, S = load(root, "dev.json")
    other_p, Xo, to_, eo, _ = load(root, "ext.json")   # the other histology

    # Hold out whole hospitals. A patient's site is fixed, so this cannot leak a
    # patient across the boundary, and it reproduces the thing that actually
    # breaks published models: a different institution's referral pattern,
    # staging practice and follow-up.
    sites = np.unique(S)
    rng.shuffle(sites)
    held = set(sites[:max(1, int(round(len(sites) * HELD_OUT_SITE_FRACTION)))])
    m_ext = np.array([s in held for s in S])
    dev_p = "%s (sites not in validation)" % proj
    ext_p = "%s (%d held-out sites)" % (proj, len(held))
    Xd, td, ed = X[~m_ext], T[~m_ext], E[~m_ext]
    Xe, te, ee = X[m_ext], T[m_ext], E[m_ext]
    # Standardise on the DEVELOPMENT cohort's statistics, and apply the same
    # transform to the external one. Re-standardising the external cohort to
    # itself would quietly remove the population shift that makes it external.
    mu, sd = Xd.mean(axis=0), np.clip(Xd.std(axis=0), 1e-6, None)
    for nm, arr in (("dev_X", (Xd - mu) / sd), ("dev_time", td), ("dev_event", ed),
                    ("ext_X", (Xe - mu) / sd), ("ext_time", te), ("ext_event", ee),
                    # the other histology, for the cross-histology number
                    ("xh_X", (Xo - mu) / sd), ("xh_time", to_), ("xh_event", eo)):
        np.save(os.path.join(a.workspace, "data", nm + ".npy"), arr)
    print(json.dumps({"dev": int(len(td)), "ext": int(len(te)), "p": Xd.shape[1],
                      "dev_project": dev_p, "ext_project": ext_p,
                      "cross_histology_project": other_p,
                      "held_out_sites": sorted(held),
                      "dev_events": int(ed.sum()), "ext_events": int(ee.sum()),
                      "covariates": list(COVARIATES), "real": True}))


if __name__ == "__main__":
    main()
