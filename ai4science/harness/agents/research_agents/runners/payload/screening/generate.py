"""A virtual screen: actives, property-matched decoys, held-out targets.

Decoys are matched on the bulk properties (weight, logP) on purpose. Unmatched
decoys make enrichment a measure of molecular weight, which is the commonest way
a screening result means nothing."""
import argparse, json, os
import numpy as np

TARGETS, PER_TARGET, ACTIVE_FRAC = 6, 220, 0.05


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default="."); ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args(); rng = np.random.default_rng(a.seed)
    os.makedirs(os.path.join(a.workspace, "data"), exist_ok=True)

    D, y, tid, scaf = [], [], [], []
    for t in range(TARGETS):
        pharm = rng.normal(0, 1, 4)              # the target's pharmacophore
        n_act = int(PER_TARGET * ACTIVE_FRAC)
        for i in range(PER_TARGET):
            active = i < n_act
            bulk = rng.normal([350, 3.0], [40, 0.9])          # weight, logP
            if active:
                feat = pharm + rng.normal(0, 0.55, 4)
            else:
                feat = rng.normal(0, 1.15, 4)
            D.append(np.concatenate([bulk, feat]))
            y.append(int(active)); tid.append(t)
            scaf.append(int(rng.integers(0, 12)))             # scaffold family
    D = np.array(D)
    np.save(os.path.join(a.workspace, "data", "descriptors.npy"), D)
    np.save(os.path.join(a.workspace, "data", "target_id.npy"), np.array(tid))
    np.save(os.path.join(a.workspace, "data", "scaffold.npy"), np.array(scaf))
    np.save(os.path.join(a.workspace, "data", "labels.npy"), np.array(y))   # withheld
    # The pharmacophores are the answer too: knowing them ranks perfectly.
    np.save(os.path.join(a.workspace, "data", "pharmacophores.npy"),
            np.zeros((TARGETS, 4)))
    print(json.dumps({"targets": TARGETS, "n": len(y), "active_frac": ACTIVE_FRAC,
                      "seed": a.seed}))


if __name__ == "__main__":
    main()
