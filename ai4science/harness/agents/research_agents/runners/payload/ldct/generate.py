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
    """A uniform soft-tissue patch, away from bone and air."""
    from scipy.ndimage import uniform_filter
    soft = (img > -20) & (img < 90)
    local_var = uniform_filter(img.astype(float) ** 2, 15) - \
        uniform_filter(img.astype(float), 15) ** 2
    ok = soft & (local_var < 900)
    ok[:r * 6, :] = ok[-r * 6:, :] = False
    ok[:, :r * 6] = ok[:, -r * 6:] = False
    ys, xs = np.nonzero(ok)
    if len(ys) == 0:
        return img.shape[0] // 2, img.shape[1] // 2
    k = len(ys) // 2
    return int(ys[k]), int(xs[k])


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
