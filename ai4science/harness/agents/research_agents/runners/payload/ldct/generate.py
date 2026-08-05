"""Real paired CT: the same patient at full dose and at reduced dose.

No dose simulation. This collection reconstructs the same acquisition twice,
which is the thing a simulated noise model is only ever an approximation of.
The full-dose reconstruction is the reference and is withheld from the sandbox.

Detectability needs a signal whose location is known, and the collection ships
no lesion masks — so a low-contrast disk is INSERTED into both images at the
same place, which is standard for task-based image quality and is labelled as
inserted rather than passed off as pathology. It is small and faint on purpose:
a large or high-contrast lesion survives any amount of blurring, and a benchmark
built on one cannot show the failure this agent exists to catch.
"""
import argparse, json, os, sys
import numpy as np

# Calibrated to this collection's actual noise, which is not a free choice:
# the series are reconstructed with B50f, a sharp lung kernel, and measure
# ~100 HU noise at full dose and 226-336 HU at low dose. A 45 HU lesion — the
# first value tried here — sits far below that and is invisible to every
# method, which makes a benchmark that cannot rank anything. 150 HU is still
# low contrast against 100 HU of full-dose noise, and small enough at 5 px
# that a PSNR-maximising blur erases it.
LESION_HU = 150.0
LESION_R = 5


def pick_site(img, r):
    """The most uniform soft-tissue site, judged where the SCORER will look.

    Two defects lived here, and the second hid the first.

    **The threshold was impossible.** Uniformity was `local_var < 900` — a
    standard deviation of 30 HU — computed on the raw image, which carries
    about 100 HU of noise at full dose by this file's own reckoning. Local
    variance is therefore ~10,000 everywhere and the condition was never true
    anywhere on any slice.

    **And the fallback was silent.** An empty candidate set returned the centre
    of the image. So every lesion went to pixel (256, 256) regardless of what
    was there: mediastinum on some patients, lung on others. Where it landed in
    lung the scorer's background ring filled with air, "noise" came out at 396
    HU instead of ~15, and lesion CNR fell below the Rose criterion however well
    the method had restored the lesion. Two of four patients failed for that
    reason and it read as a denoising failure.

    Uniformity is judged on a SMOOTHED copy so that noise does not swamp the
    anatomy the test is about, over the radius the scorer actually measures, and
    an empty candidate set now raises instead of quietly choosing the middle.
    """
    from scipy.ndimage import gaussian_filter, minimum_filter, uniform_filter
    f = img.astype(float)
    # Anatomy, with the noise taken out. Structure survives a 2-pixel blur;
    # photon noise does not.
    a = gaussian_filter(f, 2.0)

    reach = 5 * (r + 1)            # the scorer's outer ring radius
    win = 2 * reach + 1

    soft = (a > -20) & (a < 90)
    near_var = uniform_filter(a ** 2, 15) - uniform_filter(a, 15) ** 2
    ring_var = uniform_filter(a ** 2, win) - uniform_filter(a, win) ** 2
    no_air = minimum_filter(img, win) > -200

    def _edges(m):
        e = reach + r
        m[:e, :] = m[-e:, :] = False
        m[:, :e] = m[:, -e:] = False
        return m

    # In order of preference. A chest slice is mostly lung, so an entirely
    # air-free neighbourhood at this radius does not always exist — and the
    # scorer measures noise in soft tissue within the ring rather than in the
    # whole ring, so a little air nearby is survivable. It is still avoided
    # first.
    for cand in (soft & (near_var < 30.0 ** 2) & no_air & (ring_var < 40.0 ** 2),
                 soft & (near_var < 30.0 ** 2) & no_air,
                 soft & (near_var < 60.0 ** 2) & no_air,
                 soft & (near_var < 60.0 ** 2)):
        ok = _edges(cand.copy())
        if ok.any():
            break
    else:
        raise SystemExit("no uniform soft-tissue site on this slice — refusing "
                         "rather than inserting the lesion somewhere arbitrary")

    # The most uniform candidate. `ys[len // 2]` was the median in raster order,
    # which is a fact about the image's shape rather than about the site.
    scored = np.where(ok, ring_var, np.inf)
    cy, cx = np.unravel_index(int(np.argmin(scored)), scored.shape)
    return int(cy), int(cx)


def insert(img, cy, cx, r, hu):
    y, x = np.ogrid[:img.shape[0], :img.shape[1]]
    m = (y - cy) ** 2 + (x - cx) ** 2 <= r ** 2
    out = img.copy()
    out[m] += hu
    return out, m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default="."); ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    sys.path.insert(0, os.environ.get("AI4SCIENCE_PKG", ""))
    from ai4science.harness.agents.research_agents.runners import corpus
    root = corpus.LDCT.require()
    meta = json.loads(open(os.path.join(root, "metadata.json")).read())
    z = np.load(os.path.join(root, "volumes.npz"))

    pats = sorted(meta["patients"])
    pid = pats[a.seed % len(pats)]
    full = z["full_%s" % pid]
    low = z["low_%s" % pid]
    k = full.shape[0] // 2
    full, low = full[k].astype(np.float32), low[k].astype(np.float32)

    cy, cx = pick_site(full, LESION_R)
    full_l, mask = insert(full, cy, cx, LESION_R, LESION_HU)
    low_l, _ = insert(low, cy, cx, LESION_R, LESION_HU)

    d = os.path.join(a.workspace, "data")
    os.makedirs(d, exist_ok=True)
    np.save(os.path.join(d, "low_dose.npy"), low_l)          # the input
    np.save(os.path.join(d, "full_dose.npy"), full_l)        # the answer key
    np.save(os.path.join(d, "lesion_mask.npy"), mask)        # also withheld
    np.save(os.path.join(d, "lesion_amplitude.npy"),
            np.array([LESION_HU, LESION_R]))                 # also withheld
    print(json.dumps({"patient": pid, "slice": int(k),
                      "shape": list(full.shape), "lesion_hu": LESION_HU,
                      "lesion_radius_px": LESION_R, "lesion": "INSERTED",
                      "real": True}))


if __name__ == "__main__":
    main()
