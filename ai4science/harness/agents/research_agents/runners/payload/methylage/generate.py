"""Real methylation and age: fit on some hospitals, predict on others.

The split is **site-disjoint**. GSE40279 collected from four institutions, and
the alternative — a random re-split of one pooled cohort — is the mistake the
`cancer` agent had to have corrected after the fact: it measures how well a
model fits a population it has already seen, and every clock ever published
looks good by it.

The held-out ages are the answer key and are never staged. A solver that could
read them would produce a perfect clock and tell you nothing.
"""
import argparse, json, os, sys
import numpy as np

#: How much of the cohort is held out, by SITE.
#:
#: The held-out sites used to be the constant ("Utah", "USC"), and the seed
#: argument was accepted and never used — so every seed produced byte-identical
#: data. A paired comparison across seeds then had zero spread by construction,
#: `paired_p` returned exactly 0, and a night reported p = 0 for a result
#: measured once. That is arithmetic, not evidence, and it nearly got an
#: improvement adopted on nothing.
#:
#: The seed now chooses which institutions are held out, so seeds are genuinely
#: different validations of the same question — the same thing `cancer` does.
HELD_OUT_FRACTION = 0.45


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default="."); ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    sys.path.insert(0, os.environ.get("AI4SCIENCE_PKG", ""))
    from ai4science.harness.agents.research_agents.runners import corpus
    root = corpus.METHYLATION_AGE.require()

    B = np.load(os.path.join(root, "betas.npy"))
    age = np.load(os.path.join(root, "age.npy"))
    male = np.load(os.path.join(root, "male.npy"))
    site = np.load(os.path.join(root, "site.npy"))

    # Whole institutions, chosen by the seed. Sites are taken in a seeded order
    # until enough of the cohort is held out, so no patient and no contributing
    # site appears on both sides and different seeds ask genuinely different
    # questions.
    rng = np.random.default_rng(a.seed)
    order = rng.permutation(np.unique(site))
    held = np.zeros(len(site), dtype=bool)
    for s in order:
        if held.mean() >= HELD_OUT_FRACTION:
            break
        held |= (site == s)
    held_sites = sorted({str(s) for s in site[held]})
    if held.sum() < 50 or (~held).sum() < 50:
        raise SystemExit("site split leaves too few samples: %d dev, %d held"
                         % ((~held).sum(), held.sum()))

    d = os.path.join(a.workspace, "data")
    os.makedirs(d, exist_ok=True)
    np.save(os.path.join(d, "dev_betas.npy"), B[~held])
    np.save(os.path.join(d, "dev_age.npy"), age[~held])
    np.save(os.path.join(d, "dev_male.npy"), male[~held])
    np.save(os.path.join(d, "ext_betas.npy"), B[held])
    np.save(os.path.join(d, "ext_male.npy"), male[held])
    # THE ANSWER KEY. Written here so scoring can read it, and listed in the
    # benchmark's `answer_key` so it is never staged into the sandbox.
    np.save(os.path.join(d, "ext_age.npy"), age[held])

    print(json.dumps({
        "dev": int((~held).sum()), "ext": int(held.sum()),
        "probes": int(B.shape[1]),
        "dev_sites": sorted({str(s) for s in site[~held]}),
        "held_out_sites": held_sites,
        "dev_age_range": [int(age[~held].min()), int(age[~held].max())],
        "ext_age_range": [int(age[held].min()), int(age[held].max())],
        "real": True}))


if __name__ == "__main__":
    main()
