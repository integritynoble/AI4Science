"""A per-window representation of the TEXT, and nothing else.

The candidate hands in two feature matrices — one row per stimulus window — and
the linear readout is fitted outside this sandbox, through the identical path as
the stimulus-only floor and the random control of the same width. So this file
computes no correlation, imports nothing from the runner, and reads no brain
response at all. `data/train_responses.npz` IS staged and IS deliberately not
opened: the training subjects' responses would be legitimate to read, and
declining them anyway is what makes "this solver never touched a response file"
a property of the source rather than an argument about which archive was fair
game.

What the representation is, and why the cheap version is wrong. The eight
staged descriptors — word rate, token length, log frequency, duration, position
— are the floor, and a candidate that re-encodes them, linearly or at random, is
guaranteed to tie one of the two bars by construction: a linear map of eight
columns is still eight-dimensional however wide it is written, and a random one
is the control itself. What a language representation has that the eight do not
is lexical IDENTITY and CONTEXT, so that is what is built here:

  * a stable signed hash of each window's words. Which words a window holds is
    not recoverable from how many there were or how long they are;
  * a second hashed block over character n-grams, so `remember` and
    `remembered` land near each other instead of in two unrelated columns —
    morphology, which whole-word hashing throws away;
  * a context term: an exponentially decayed sum of the PRECEDING windows'
    lexical vectors. Language cortex responses to a window depend on the
    sentence it sits in, not only on the words inside it, and this is the
    cheapest honest statement of that;
  * the eight descriptors concatenated in, because generate.py stages them for
    the solver on purpose and a candidate that omitted them could lose to the
    floor for a reason that has nothing to do with its representation.

The hashed part is then compressed by a truncated SVD whose basis is fitted on
the TRAINING windows only, the way the methylation clock takes its PCs from the
training betas: the held-out windows are projected through a basis they had no
part in choosing. The width is kept modest deliberately — the random control is
drawn at whatever width this file hands in, so inflating it inflates the bar,
and an honest candidate does not buy dimensionality it cannot use.

Nothing here draws a random number. brainlang's control is a random projection
by definition; a candidate is the other side of that comparison, and a
representation drawn from a generator predicts held-out responses at exactly the
level of the thing it is supposed to beat while the run still exits 0.

This is the REFERENCE solver: the half of `payload/brainlang` that makes the
benchmark runnable end to end. It is also the drop-in point — a real language
model's per-window activations replace `_lexical` and `_context` and the rest of
the file is unchanged — and with a real corpus mapped onto INTERFACE, that
substitution is the only step left.
"""
import argparse, json, os, zlib
import numpy as np


#: Widths of the two hashed blocks, kept separate rather than shared.
#:
#: A whole-word column and a character-n-gram column that collide are two
#: unrelated facts summed into one number for no gain; the n-grams are precisely
#: the part that has to place related forms NEAR one another, which a shared
#: space undoes at random.
D_WORD = 512
D_CHAR = 512
#: Character n-gram orders, over the token with word boundaries marked, so a
#: prefix and a suffix are distinguishable from the same letters mid-word.
NGRAMS = (3, 4)
#: Weight on the previous window's context, applied recursively. At 0.5 a window
#: still carries a few percent of what was said four windows earlier, which is
#: about the span a sentence lasts at these window rates.
CONTEXT_DECAY = 0.5
#: Components kept from the hashed block, before the eight descriptors are added.
#:
#: Small on purpose. The control is matched to the width this file emits, so
#: every extra column raises the bar it is measured against, and the readout is
#: fitted on the held-out windows alone — a few dozen of them. Width bought
#: beyond what those rows can estimate is width that costs both sides.
N_COMPONENTS = 32


def _signed_bucket(text, width):
    """A stable signed hash of `text` into `width` buckets.

    zlib.crc32 rather than the builtin hash(), which is salted by PYTHONHASHSEED:
    the same word would land in a different column on the next run, and a
    representation nobody can reproduce cannot be re-checked by whoever reads the
    number it earned. The sign comes from the top bit and the column from the
    low bits, so the two are not the same fact twice.
    """
    h = zlib.crc32(text.encode("utf-8"))
    return h % width, (1.0 if (h >> 31) & 1 else -1.0)


def _unit_rows(X):
    """L2-normalise each row, leaving all-zero rows alone.

    How many words a window holds is already the first staged descriptor. These
    columns are here to say WHICH words, so their magnitude should not re-encode
    the count and hand the readout the same regressor twice.
    """
    norm = np.sqrt((X * X).sum(axis=1))
    norm[norm == 0] = 1.0
    return X / norm[:, None]


def _lexical(stimulus):
    """One row per window: word identity and morphology, hashed.

    `token` is a string or a list of them, per INTERFACE, and both are handled
    the way stimulus_descriptors handles them. Case is folded first: upper case
    at a sentence start is a transcription convention, and treating it as a
    different word would split a common token across two columns for no reason.
    """
    n = len(stimulus)
    words = np.zeros((n, D_WORD), dtype=np.float64)
    chars = np.zeros((n, D_CHAR), dtype=np.float64)
    for i, w in enumerate(stimulus):
        tok = w.get("token", "")
        toks = [tok] if isinstance(tok, str) else list(tok)
        for t in toks:
            t = str(t).lower()
            j, s = _signed_bucket("w|" + t, D_WORD)
            words[i, j] += s
            marked = "^" + t + "$"
            for k in NGRAMS:
                for a in range(len(marked) - k + 1):
                    j, s = _signed_bucket("c|" + marked[a:a + k], D_CHAR)
                    chars[i, j] += s
    return np.hstack([_unit_rows(words), _unit_rows(chars)])


def _context(lex, decay):
    """Exponentially decayed sum of everything said BEFORE each window.

    Strictly preceding: window i's own vector is already beside this one, and
    including it here would only rescale a column the readout can rescale
    itself. Run over the whole stimulus in window order, so a held-out window
    carries the sentence that led into it — that is stimulus, not response, and
    it is the same material generate.py counts frequencies over.
    """
    ctx = np.zeros_like(lex)
    for i in range(1, len(lex)):
        ctx[i] = decay * (ctx[i - 1] + lex[i - 1])
    return ctx


def _project(train, heldout, k):
    """Truncated SVD basis from the training rows; both matrices through it.

    Fitted on the training windows ONLY, as the methylation clock takes its PCs
    from the training betas: a basis chosen with the held-out rows in it is a
    basis those rows were allowed to influence before being scored in it.

    Via the Gram matrix, because there are a few hundred rows against two
    thousand hashed columns and the right singular vectors come out of the small
    eigenproblem exactly — if A Aᵀ = Q W Qᵀ then vᵢ = Aᵀqᵢ / √wᵢ.

    The component count is clipped to the rows and the rank actually available,
    so a workspace with few training windows still yields an equal-width pair
    rather than an error or an invented column. If nothing survives, both sides
    come back zero-wide and the eight descriptors are the whole representation:
    a candidate that tied the floor, which is the correct verdict for it.
    """
    k = min(int(k), train.shape[0] - 1, train.shape[1])
    if k < 1:
        return train[:, :0], heldout[:, :0]
    gram = train @ train.T
    w, Q = np.linalg.eigh(gram)                     # ascending, symmetric
    order = np.argsort(w, kind="stable")[::-1][:k]
    keep = [i for i in order if w[i] > 1e-9 * max(float(w.max()), 1e-30)]
    if not keep:
        return train[:, :0], heldout[:, :0]
    V = (train.T @ Q[:, keep]) / np.sqrt(w[keep])   # hashed columns x k
    # The sign of each eigenvector is arbitrary and LAPACK's choice can differ
    # between BLAS builds. Pinning it to the largest-magnitude entry means the
    # emitted bytes are a function of the text and not of what numpy links
    # against — which is the determinism claim, made where it can break.
    flip = np.sign(V[np.argmax(np.abs(V), axis=0), np.arange(V.shape[1])])
    flip[flip == 0] = 1.0
    V = V * flip
    return train @ V, heldout @ V


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--workspace", default=".")
    ws = ap.parse_args().workspace
    d = lambda name: os.path.join(ws, "data", name)

    # No try/except anywhere below. A missing input is a FileNotFoundError and
    # the run fails loudly; the alternative is a workspace that looks complete
    # and a feature matrix that came from somewhere other than the stimulus.
    stimulus = json.load(open(d("stimulus.json")))
    split = json.load(open(d("split.json")))
    train_idx = [int(i) for i in split["train_windows"]]
    heldout_idx = [int(i) for i in split["heldout_windows"]]
    # The split is handed over, never re-cut here: it is a split by SUBJECT, and
    # these features are per-window and subject-independent, which is exactly
    # what lets them be scored against people this process never saw.
    desc_train = np.load(d("train_features.npy")).astype(np.float64)
    desc_heldout = np.load(d("heldout_features.npy")).astype(np.float64)

    lex = _lexical(stimulus)
    X = np.hstack([lex, _context(lex, CONTEXT_DECAY)])
    mu = X[train_idx].mean(axis=0)
    P_train, P_heldout = _project(X[train_idx] - mu, X[heldout_idx] - mu,
                                  N_COMPONENTS)

    out = os.path.join(ws, "results"); os.makedirs(out, exist_ok=True)
    # One basis, so the two matrices are the same width by construction rather
    # than by a check further downstream.
    np.save(os.path.join(out, "features_train.npy"),
            np.hstack([desc_train, P_train]))
    np.save(os.path.join(out, "features_heldout.npy"),
            np.hstack([desc_heldout, P_heldout]))
    print("features: %d train windows, %d held-out, %d wide "
          "(%d staged descriptors + %d hashed components)"
          % (len(train_idx), len(heldout_idx),
             desc_train.shape[1] + P_train.shape[1],
             desc_train.shape[1], P_train.shape[1]))


if __name__ == "__main__":
    main()
