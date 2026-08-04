"""Real DUD-E, set up as ligand-based virtual screening actually works.

The first version of this asked the solver to rank a target's library with no
labels at all. Nothing in the field works that way: a virtual screen starts from
either a structure to dock into or a handful of known actives to search from.
Given neither, the honest answer for any method is chance — which makes a
benchmark that cannot distinguish anything.

So the realistic task: for each target a few actives are **known** and staged,
the rest of the library is ranked, and enrichment is measured on the part that
was not given. That is the standard ligand-based VS evaluation, and it is what a
medicinal chemist actually has on day one of a project.

Morgan fingerprints are computed here rather than shipped, so the descriptor set
can change without re-downloading four thousand molecules.
"""
import argparse, json, os, sys
import numpy as np

KNOWN_PER_TARGET = 10           # actives handed to the solver as the query set


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default="."); ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    sys.path.insert(0, os.environ.get("AI4SCIENCE_PKG", ""))
    from ai4science.harness.agents.research_agents.runners import corpus
    from rdkit import Chem, RDLogger
    from rdkit.Chem import rdFingerprintGenerator
    RDLogger.DisableLog("rdApp.*")

    root = corpus.DUDE.require()
    with open(os.path.join(root, "targets.json")) as f:
        targets = json.load(f)
    rng = np.random.default_rng(a.seed)
    gen = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=1024)

    names = sorted(targets)
    D, FP, y, tid, known = [], [], [], [], []
    for i, t in enumerate(names):
        rows = targets[t]
        act = [j for j, r in enumerate(rows) if r["y"] == 1]
        rng.shuffle(act)
        query = set(act[:KNOWN_PER_TARGET])
        for j, r in enumerate(rows):
            m = Chem.MolFromSmiles(r["smiles"])
            if m is None:
                continue
            fp = gen.GetFingerprintAsNumPy(m).astype(np.uint8)
            D.append(r["d"]); FP.append(fp); y.append(r["y"]); tid.append(i)
            known.append(1 if j in query else 0)

    D = np.array(D, float); FP = np.array(FP, np.uint8)
    y = np.array(y, int); tid = np.array(tid, int); known = np.array(known, int)

    d = os.path.join(a.workspace, "data")
    os.makedirs(d, exist_ok=True)
    np.save(os.path.join(d, "descriptors.npy"), D)
    np.save(os.path.join(d, "fingerprints.npy"), FP)
    np.save(os.path.join(d, "target_id.npy"), tid)
    np.save(os.path.join(d, "known_active.npy"), known)   # the query set: staged
    np.save(os.path.join(d, "labels.npy"), y)             # everything else: withheld
    print(json.dumps({"targets": names, "n": int(len(y)),
                      "actives": int(y.sum()), "known_actives": int(known.sum()),
                      "active_frac": float(y.mean()), "real": True}))


if __name__ == "__main__":
    main()
