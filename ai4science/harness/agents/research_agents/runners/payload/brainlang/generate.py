"""A subject-disjoint encoding-model problem, cut from a real brain corpus.

Nothing here can run yet. `brainlang.load_corpus()` is the first statement that
touches data and there is no brain-recording corpus on this machine, so this
generator refuses at line one of `main` and says which files it wanted. That is
the intended behaviour, not a stub: a generator that manufactured responses when
the corpus was absent would hand the whole benchmark a random-number generator
to score, and every number after it would look exactly like a result.

Two things are cut here, and the split is the interesting one:

  * the split is by SUBJECT. Unit responses are strongly idiosyncratic, so a
    model fitted on any of subject s2's data predicts the rest of s2 far better
    than it predicts anyone new. `cancer` had precisely this corrected after the
    fact. `validate_subject_disjoint` is called below rather than trusted.

  * the held-out WINDOWS are the ones the corpus presented more than once. The
    noise ceiling is measured from those repeats, and this benchmark reports no
    correlation without a ceiling — so which windows can be scored is a fact
    about the corpus, not a choice made here.

The held-out subjects' responses and their repeats are the answer key and are
never staged. A solver that could read them would produce a perfect encoding
model and tell you nothing.
"""
import argparse, json, os, sys
import numpy as np


#: Fraction of the ceiling-bearing subjects held out, chosen by the seed.
#:
#: The seed chooses WHICH subjects, so different seeds are genuinely different
#: validations of the same question — the mistake `reverse-aging` made was
#: accepting a seed and ignoring it, which gave every seed byte-identical data
#: and a paired test with zero spread by construction.
HELD_OUT_FRACTION = 0.34
#: Below this the mean over held-out subjects is one or two people's anatomy.
MIN_TEST_SUBJECTS = 3


def stimulus_descriptors(stimulus, index):
    """Stimulus-only properties of each window: no model of meaning involved.

    Word rate, token length, log token frequency, position and duration — the
    things every account of language cortex agrees are there and that no
    language model is needed to compute. These are what the floor is fitted
    from, and they are staged for the solver as well: a candidate is welcome to
    use them, and if that is ALL it uses it will tie the floor, which is the
    correct verdict for it.

    Token frequency is counted over the whole stimulus, held-out windows
    included. That is not leakage: the stimulus is not the answer key, the
    responses are, and a frequency table built only from the training windows
    would be a worse descriptor for no gain in rigour.
    """
    counts = {}
    for w in stimulus:
        tok = w.get("token", "")
        for t in ([tok] if isinstance(tok, str) else list(tok)):
            counts[t] = counts.get(t, 0) + 1
    total = float(sum(counts.values())) or 1.0

    rows = []
    for i in index:
        w = stimulus[i]
        tok = w.get("token", "")
        toks = [tok] if isinstance(tok, str) else list(tok)
        lens = [len(t) for t in toks] or [0]
        logf = [np.log((counts.get(t, 0) + 1) / total) for t in toks] or [0.0]
        dur = float(w.get("offset_s", 0.0)) - float(w.get("onset_s", 0.0))
        rows.append([len(toks),                       # word rate in the window
                     float(np.mean(lens)),
                     float(np.max(lens)),
                     float(np.mean(logf)),
                     float(np.min(logf)),             # the rarest word in it
                     max(dur, 0.0),
                     len(toks) / max(dur, 1e-6),      # words per second
                     i / max(len(stimulus) - 1, 1)])  # position in the session
    return np.asarray(rows, dtype=np.float64)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default="."); ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    sys.path.insert(0, os.environ.get("AI4SCIENCE_PKG", ""))
    from ai4science.harness.agents.research_agents.runners import brainlang

    # Refuses here, with the directory searched and the files missing from it.
    bc = brainlang.load_corpus()

    # Only subjects whose held-out material was presented twice can be scored:
    # without repeats there is no ceiling for them, and a correlation without a
    # ceiling is not a number this benchmark will report.
    ceilinged = sorted(s for s in bc.subjects if s in bc.repeats)
    if len(ceilinged) < MIN_TEST_SUBJECTS + 1:
        raise SystemExit(
            "%d subject(s) carry repeated presentations; a subject-disjoint "
            "split with a measured ceiling needs at least %d"
            % (len(ceilinged), MIN_TEST_SUBJECTS + 1))

    rng = np.random.default_rng(a.seed)
    order = list(rng.permutation(ceilinged))
    n_test = max(MIN_TEST_SUBJECTS, int(round(HELD_OUT_FRACTION * len(ceilinged))))
    n_test = min(n_test, len(ceilinged) - 1)
    test = sorted(str(s) for s in order[:n_test])
    train = sorted(str(s) for s in bc.subjects if str(s) not in set(test))
    # Checked where the split is MADE, and again where it is scored. The two can
    # drift, and the one that matters is whichever the reader does not look at.
    brainlang.validate_subject_disjoint(train, test)

    n_heldout = {int(bc.repeats[s].shape[1]) for s in test}
    if len(n_heldout) != 1:
        raise SystemExit("held-out subjects disagree on how many windows were "
                         "repeated: %s" % sorted(n_heldout))
    k = n_heldout.pop()
    n_windows = bc.n_windows
    if k < 20 or k >= n_windows:
        raise SystemExit("%d repeated windows out of %d is not a usable "
                         "held-out set" % (k, n_windows))
    # The repeated windows are the FINAL k of the shared sequence; see INTERFACE.
    heldout_idx = list(range(n_windows - k, n_windows))
    train_idx = list(range(0, n_windows - k))

    d = os.path.join(a.workspace, "data")
    os.makedirs(d, exist_ok=True)
    json.dump(list(bc.stimulus), open(os.path.join(d, "stimulus.json"), "w"))
    json.dump({"train_subjects": train, "test_subjects": test,
               "train_windows": train_idx, "heldout_windows": heldout_idx},
              open(os.path.join(d, "split.json"), "w"))
    np.save(os.path.join(d, "train_features.npy"),
            stimulus_descriptors(bc.stimulus, train_idx))
    np.save(os.path.join(d, "heldout_features.npy"),
            stimulus_descriptors(bc.stimulus, heldout_idx))
    np.savez_compressed(
        os.path.join(d, "train_responses.npz"),
        **{s: bc.responses[s][train_idx].astype(np.float32) for s in train})

    # THE ANSWER KEY. Written here so scoring can read it, and named in
    # HUMANBRAIN.answer_key so it is never staged into the sandbox.
    np.savez_compressed(
        os.path.join(d, "test_responses.npz"),
        **{s: bc.responses[s][heldout_idx].astype(np.float32) for s in test})
    np.savez_compressed(
        os.path.join(d, "test_repeats.npz"),
        **{s: bc.repeats[s].astype(np.float32) for s in test})

    print(json.dumps({
        "train_subjects": train, "test_subjects": test,
        "n_train_windows": len(train_idx), "n_heldout_windows": len(heldout_idx),
        "n_repeats": int(min(bc.repeats[s].shape[0] for s in test)),
        "modality": bc.metadata.get("modality", "unstated"),
        "alignment": bc.metadata.get("alignment", "unstated"),
        "real": True}))


if __name__ == "__main__":
    main()
