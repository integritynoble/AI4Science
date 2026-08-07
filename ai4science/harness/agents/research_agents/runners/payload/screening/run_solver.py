"""Ligand-based virtual screening: rank by similarity to the known actives.

Similarity to the query set, per target — the oldest and still one of the most
competitive ligand-based baselines. It reads the query set, which it is given,
and never the labels, which it is not.

The method has four knobs, and **at their defaults this is exactly the
max-Tanimoto solver it has always been**: `top_k=1` takes the single nearest
active, `tversky_alpha = tversky_beta = 1` is Tanimoto by definition, and
`idf_weight=0` makes every bit weigh one. That matters because the incumbent in
any search is this solver at its defaults — if the defaults drifted, every
reported delta would be measured against a baseline nobody had ever run.

What each knob is, in the field's terms:

**`top_k`** — group fusion. Ranking by the single nearest known active is 1-NN;
averaging the top *k* similarities is the standard alternative, and on targets
whose actives fall into several chemical series it is usually the better one,
because a molecule close to *several* known actives is a stronger bet than one
close to a single outlier.

**`tversky_alpha` / `tversky_beta`** — Tversky's index generalises Tanimoto by
weighting the two asymmetries separately: features the candidate has and the
query lacks (`alpha`), and features the query has and the candidate lacks
(`beta`). Tanimoto forces them equal. Lowering `alpha` tolerates candidates
larger than the query — analogues carrying extra substituents — and raising it
demands the candidate be contained in what the query already shows.

**`idf_weight`** — bits shared by most of the library say little about binding;
rare bits say more. Weighting each bit by its inverse document frequency,
raised to this exponent, is the usual correction. At 0 every bit weighs the
same, which is what unweighted Tanimoto assumes.

**`bayes_weight`** — blend a Laplacian-modified naive Bayes score, fitted on the
query set against the library as background, with the similarity score; both
converted to within-target ranks first. At 0 this term is absent and the solver
is unchanged. Similarity asks whether a molecule resembles a known active, which
by construction cannot reach a new scaffold; the Bayes term scores individual
BITS by their enrichment in the actives, which can.

None of these can reach the labels. They change how molecules are compared to
the query set, which is the only thing the solver is given. The Bayes term's
positives are the staged query set and its background is the unlabelled library
— both of which the solver already holds.
"""
import argparse, json, os
import numpy as np


def load_params(ws, **defaults):
    f = os.path.join(ws, "params.json")
    if os.path.exists(f):
        defaults.update(json.load(open(f)))
    return defaults


def bayes_scores(F: np.ndarray, q_mask: np.ndarray) -> np.ndarray:
    """Laplacian-modified naive Bayes: query set against the library background.

    Where max-similarity asks "does this look like one known active", this asks
    "which BITS are enriched in the actives relative to this library". That
    difference is the point: a feature-level score can survive a scaffold
    change, and whole-molecule resemblance by construction cannot.

    Uses no labels — the positives are the staged query set, the background is
    the library the solver is handed. The +1 terms are the Laplacian smoothing
    that makes this usable from ten actives, which is the whole regime here.
    """
    A = F[q_mask].sum(axis=0).astype(np.float64)     # actives carrying each bit
    n_a, n_lib = int(q_mask.sum()), len(F)
    expected = F.sum(axis=0).astype(np.float64) * (n_a / max(n_lib, 1))
    return F.astype(np.float64) @ np.log((A + 1.0) / (expected + 1.0))


def rank_unit(x: np.ndarray) -> np.ndarray:
    """Ranks scaled to [0, 1]. Ties broken arbitrarily but deterministically."""
    r = np.empty(len(x), np.float64)
    r[np.argsort(x)] = np.arange(len(x), dtype=np.float64)
    return r / max(len(x) - 1, 1)


def bit_weights(FP: np.ndarray, idf_weight: float) -> np.ndarray:
    """Inverse document frequency per bit, raised to `idf_weight`.

    At `idf_weight == 0` this is all ones and the similarity below reduces to
    the ordinary unweighted one — returned exactly, not approximately, so the
    default path is the historical path."""
    if idf_weight <= 0:
        return np.ones(FP.shape[1], dtype=np.float64)
    df = FP.sum(axis=0).astype(np.float64)              # documents per bit
    idf = np.log((len(FP) + 1.0) / (df + 1.0)) + 1.0
    return np.maximum(idf, 1e-9) ** float(idf_weight)


def similarity(F: np.ndarray, q: np.ndarray, w: np.ndarray,
               alpha: float, beta: float) -> np.ndarray:
    """Weighted Tversky similarity of every row of F to every row of q.

    With `w` all ones and `alpha == beta == 1` the denominator is
    `|F| + |q| - common` — the Tanimoto union, exactly."""
    Fw = F.astype(np.float64) * w
    qf = q.astype(np.float64)
    common = Fw @ qf.T                                   # weighted intersection
    only_f = Fw.sum(1)[:, None] - common                 # candidate has, query lacks
    only_q = (qf * w).sum(1)[None, :] - common           # query has, candidate lacks
    denom = common + alpha * only_f + beta * only_q
    return common / np.clip(denom, 1e-12, None)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--workspace", default=".")
    ws = ap.parse_args().workspace
    pr = load_params(ws, top_k=1, tversky_alpha=1.0, tversky_beta=1.0,
                     idf_weight=0.0, bayes_weight=0.0)
    top_k = max(1, int(round(float(pr["top_k"]))))
    alpha, beta = float(pr["tversky_alpha"]), float(pr["tversky_beta"])
    bw = float(pr["bayes_weight"])

    d = lambda n: np.load(os.path.join(ws, "data", n + ".npy"))
    FP, tid, known = d("fingerprints").astype(bool), d("target_id"), d("known_active")

    # Document frequency is computed over the whole library, which the solver is
    # given. It is a property of the fingerprints, not of the labels.
    w = bit_weights(FP, float(pr["idf_weight"]))

    scores = np.full(len(FP), -np.inf)
    for t in np.unique(tid):
        m = tid == t
        q = FP[m & (known == 1)]
        if len(q) == 0:
            scores[m] = 0.0
            continue
        sim = similarity(FP[m], q, w, alpha, beta)
        k = min(top_k, sim.shape[1])
        if k == 1:
            s = sim.max(axis=1)                          # nearest known active
        else:
            # Mean of the k most similar actives. Partition then average the
            # tail; sorting the whole row would cost more and say the same.
            s = np.partition(sim, -k, axis=1)[:, -k:].mean(axis=1)
        if bw > 0:
            # Blend in the Bayes score, both sides converted to WITHIN-TARGET
            # ranks first. Two reasons the ranks are not optional:
            #
            #   * the two scores have incompatible units — a Tversky index in
            #     [0,1] against a sum of log-odds — so a raw blend is whichever
            #     one happens to be numerically larger;
            #   * enrichment is measured on all targets pooled, and raw scores
            #     are not comparable ACROSS targets either. A target whose
            #     actives form one tight series scores higher throughout than a
            #     target with a diverse set, so a pooled top percentile fills up
            #     with the former and the latter is never examined however good
            #     its own ranking is. Ranking within the target removes that,
            #     and it is what a screener reading six target lists does.
            s = (1.0 - bw) * rank_unit(s) + bw * rank_unit(
                bayes_scores(FP[m], known[m] == 1))
        scores[m] = s
    os.makedirs(os.path.join(ws, "results"), exist_ok=True)
    np.save(os.path.join(ws, "results", "scores.npy"), scores)
    print("scored %d  top_k=%d alpha=%.3g beta=%.3g idf=%.3g bayes=%.3g"
          % (len(scores), top_k, alpha, beta, float(pr["idf_weight"]), bw))


if __name__ == "__main__":
    main()
