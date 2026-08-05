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

#: Tanimoto below which two actives count as different chemical series.
#:
#: The query set used to be drawn at RANDOM from a target's actives, and DUD-E
#: actives are largely analogue series, so the ten handed over were usually close
#: relatives of the ones being scored: test actives sat at 0.519 mean max-Tanimoto
#: to the query against 0.154 for decoys. Nearest-neighbour retrieval then found
#: them without generalising at all, and EF@1% pinned at 100% of its ceiling —
#: a metric that had stopped ranking methods.
#:
#: So the query set is drawn from whole clusters, and the rest of those clusters
#: is dropped rather than scored. What is left to find is a series the solver was
#: not shown. At 0.4 the analogue gap falls to 0.093 and EF@1% lands near 43% of
#: ceiling; at 0.5 it is still 88% of ceiling, which is why this is not looser.
CLUSTER_CUTOFF = 0.4


def _tanimoto(A, B):
    A = A.astype(np.uint16); B = B.astype(np.uint16)
    inter = A @ B.T
    union = A.sum(1)[:, None] + B.sum(1)[None, :] - inter
    return inter / np.clip(union, 1, None)


def _leader_clusters(F, cutoff):
    """Leader clustering: each molecule joins the first leader within cutoff.

    Deliberately the simple algorithm. What matters here is that whole series end
    up together, not which of several clusterings is optimal — and a simple one
    is a clustering a reader can check by hand."""
    leaders, assign = [], np.full(len(F), -1)
    for i in range(len(F)):
        if leaders:
            s = _tanimoto(F[i:i + 1], F[leaders])[0]
            j = int(s.argmax())
            if s[j] >= cutoff:
                assign[i] = j
                continue
        assign[i] = len(leaders)
        leaders.append(i)
    return assign


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
        # Fingerprints first: the split is decided on them, so they cannot be
        # computed inside the emit loop any more.
        parsed = []
        for r in rows:
            m = Chem.MolFromSmiles(r["smiles"])
            if m is None:
                continue
            parsed.append((r, gen.GetFingerprintAsNumPy(m).astype(np.uint8)))

        act_pos = [k for k, (r, _) in enumerate(parsed) if r["y"] == 1]
        assign = _leader_clusters(np.array([parsed[k][1] for k in act_pos], bool),
                                  CLUSTER_CUTOFF)
        pool = []
        for c in rng.permutation(np.unique(assign)):
            pool += [act_pos[k] for k in np.flatnonzero(assign == c)]
            if len(pool) >= KNOWN_PER_TARGET:
                break
        query = set(pool[:KNOWN_PER_TARGET])
        # The rest of the query's own clusters are neither shown nor scored:
        # scoring them would be scoring the query set's analogues back to itself.
        withheld = set(pool) - query

        for k, (r, fp) in enumerate(parsed):
            if k in withheld:
                continue
            D.append(r["d"]); FP.append(fp); y.append(r["y"]); tid.append(i)
            known.append(1 if k in query else 0)

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
