"""Real capsule endoscopy frames, split by video — which is to say, by patient.

Two facts about this dataset drive the design and are worth stating before any
number is read from it.

**Consecutive frames are near-duplicates.** A capsule films at several frames a
second while drifting through the gut, so neighbouring frames are almost the
same picture. A frame-level split puts near-copies on both sides and every
model looks excellent. The split here is by `video_id`, and the scorer verifies
no video crosses it rather than trusting this docstring.

**The pathology classes come from very few patients.** `Blood - fresh` is 446
frames from two videos. So the positive class is the red vascular findings
pooled — angiectasia, fresh blood, erythema, hematin — which share the physical
signal a haemoglobin prior can see, and together span enough videos to hold some
out. It is still a small number of patients and the metadata says how many.
"""
import argparse, json, os, sys
import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default="."); ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    sys.path.insert(0, os.environ.get("AI4SCIENCE_PKG", ""))
    from ai4science.harness.agents.research_agents.runners import corpus
    root = corpus.KVASIR_CAPSULE.require()
    z = np.load(os.path.join(root, "frames.npz"), allow_pickle=False)
    meta = json.loads(open(os.path.join(root, "metadata.json")).read())

    rgb, y, vid = z["rgb"], z["label"].astype(int), z["video"]
    thumb = z["thumb"]          # 32x32 RGB: the prior is per-pixel, not per-frame
    # The held-out videos rotate with the seed, so a seed set covers different
    # patients rather than re-running one split with different noise.
    rng = np.random.default_rng(a.seed)
    pos_v = sorted(set(vid[y == 1])); neg_v = sorted(set(vid[y == 0]))
    rng.shuffle(pos_v); rng.shuffle(neg_v)
    test_v = set(pos_v[: max(1, len(pos_v) // 3)]) | set(neg_v[: max(1, len(neg_v) // 3)])
    is_test = np.array([v in test_v for v in vid])

    d = os.path.join(a.workspace, "data")
    os.makedirs(d, exist_ok=True)
    np.save(os.path.join(d, "frames.npy"), rgb)
    np.save(os.path.join(d, "thumbs.npy"), thumb)
    np.save(os.path.join(d, "video_id.npy"), vid)
    np.save(os.path.join(d, "is_test.npy"), is_test)
    np.save(os.path.join(d, "labels.npy"), y)                 # withheld
    print(json.dumps({"frames": int(len(y)), "positive": int(y.sum()),
                      "test_videos": int(len(test_v)),
                      "positive_videos": len(pos_v), "negative_videos": len(neg_v),
                      "videos_per_class": meta.get("videos_per_class"),
                      "real": True}))


if __name__ == "__main__":
    main()
