"""One fetcher per corpus.

Each writes a small bundle plus a `PROVENANCE.json` saying where the data came
from, when, and under what terms — so a metric computed from it can be traced to
a source rather than to a directory someone once filled.
"""
from __future__ import annotations

import gzip
import io
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .. import corpus as _corpus

UA = {"User-Agent": "ai4science-research-agents/1.0"}


def _get(url: str, *, timeout: int = 120, binary: bool = False):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    if binary:
        return raw
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return raw.decode("utf-8", "replace")


def _open_stream(url: str, timeout: int = 600):
    """A live response to read through, rather than a buffer to hold.

    The beta matrix is 1.1 GB and what is kept from it is ~55 MB. `_get` would
    materialise the whole thing first, which is the difference between a fetch
    that runs on a small machine and one that does not."""
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=timeout)


def _to_float(s: str) -> float:
    """A beta value, or NaN. GEO writes blanks, NA and quoted numbers."""
    s = s.strip().strip('"')
    if not s or s.upper() in ("NA", "NAN", "NULL"):
        return float("nan")
    try:
        return float(s)
    except ValueError:
        return float("nan")


def _provenance(d: Path, c: "_corpus.Corpus", **extra) -> Path:
    p = d / "PROVENANCE.json"
    p.write_text(json.dumps(
        {"corpus": c.key, "title": c.title, "source": c.source,
         "licence": c.licence, "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                           time.gmtime()),
         **extra}, indent=1))
    return p


# ------------------------------------------------------- TCGA survival (cancer)

_GDC = "https://api.gdc.cancer.gov/cases"
_FIELDS = ",".join((
    "submitter_id", "demographic.vital_status", "demographic.days_to_death",
    "demographic.age_at_index", "demographic.gender",
    "diagnoses.ajcc_pathologic_stage", "diagnoses.days_to_last_follow_up",
    "diagnoses.prior_malignancy",
    # T and N stage: the strongest clinical predictors in NSCLC and more
    # granular than the overall stage, which collapses them.
    "diagnoses.ajcc_pathologic_t", "diagnoses.ajcc_pathologic_n",
))


def _gdc_cohort(project: str, size: int = 1200) -> List[Dict[str, Any]]:
    filt = {"op": "in", "content": {"field": "project.project_id",
                                    "value": [project]}}
    q = urllib.parse.urlencode({"filters": json.dumps(filt), "fields": _FIELDS,
                                "size": str(size), "format": "JSON"})
    raw = json.loads(_get("%s?%s" % (_GDC, q)))
    return raw["data"]["hits"]


def _tcga_rows(hits: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One row per case: covariates, follow-up time, and whether it is an event.

    Cases with neither a death time nor a follow-up time carry no survival
    information at all and are dropped — an unknown time is not a long one."""
    out = []
    for h in hits:
        demo = h.get("demographic") or {}
        dx = (h.get("diagnoses") or [{}])[0]
        vital = (demo.get("vital_status") or "").lower()
        dead = vital == "dead"
        t = demo.get("days_to_death") if dead else dx.get("days_to_last_follow_up")
        age = demo.get("age_at_index")
        if t is None or age is None or float(t) <= 0:
            continue
        stage = (dx.get("ajcc_pathologic_stage") or "").replace("Stage ", "").strip()
        roman = {"I": 1, "IA": 1, "IB": 1, "II": 2, "IIA": 2, "IIB": 2,
                 "III": 3, "IIIA": 3, "IIIB": 3, "IV": 4}

        def ordinal(v, prefix):
            """T2b -> 2, N1 -> 1. Missing stays 0 and is flagged, because an
            unknown stage is not an early one."""
            v = (v or "").strip().upper()
            if not v.startswith(prefix):
                return 0.0
            for ch in v[len(prefix):]:
                if ch.isdigit():
                    return float(ch)
            return 0.0

        tstage = ordinal(dx.get("ajcc_pathologic_t"), "T")
        nstage = ordinal(dx.get("ajcc_pathologic_n"), "N")
        out.append({"case": h.get("submitter_id"),
                    "age": float(age),
                    "male": 1.0 if (demo.get("gender") or "") == "male" else 0.0,
                    "stage": float(roman.get(stage, 0)),
                    "t_stage": tstage, "n_stage": nstage,
                    "staged": 1.0 if (tstage and nstage) else 0.0,
                    "prior_malignancy": 1.0 if (dx.get("prior_malignancy") or ""
                                                ).lower() == "yes" else 0.0,
                    "time": float(t), "event": 1 if dead else 0})
    return out


def tcga_survival(_argv=()) -> str:
    c = _corpus.TCGA_SURVIVAL
    d = c.dir()
    d.mkdir(parents=True, exist_ok=True)
    dev = _tcga_rows(_gdc_cohort("TCGA-LUAD"))
    ext = _tcga_rows(_gdc_cohort("TCGA-LUSC"))
    if len(dev) < 100 or len(ext) < 100:
        raise RuntimeError("GDC returned too few usable cases (%d dev, %d ext)"
                           % (len(dev), len(ext)))
    (d / "dev.json").write_text(json.dumps({"project": "TCGA-LUAD", "rows": dev}))
    (d / "ext.json").write_text(json.dumps({"project": "TCGA-LUSC", "rows": ext}))
    _provenance(d, c, dev_n=len(dev), ext_n=len(ext),
                dev_project="TCGA-LUAD", ext_project="TCGA-LUSC",
                note="lung adenocarcinoma as development, squamous cell as "
                     "external — different tumour biology and a different "
                     "population, which is what makes it an external test")
    return ("%s: %d development cases (TCGA-LUAD), %d external (TCGA-LUSC) → %s"
            % (c.key, len(dev), len(ext), d))


# ------------------------------------------------------------ DUD-E (drug design)

#: A handful of targets across families. Held-out targets come from this list,
#: so they must be genuinely different proteins rather than close paralogues.
DUDE_TARGETS = ("ampc", "cxcr4", "hivpr", "kif11", "aces", "cdk2")
_DUDE = "https://dude.docking.org/targets/%s/%s"


def _dude_smiles(target: str, kind: str, *, tries: int = 4) -> List[str]:
    """DUD-E's server returns 503 under load often enough that a single attempt
    is not a fetch. Retries with a backoff, then gives up on this target rather
    than the whole corpus — a partial target list is usable, a half-written one
    is not."""
    url = _DUDE % (target, "actives_final.ism" if kind == "active"
                   else "decoys_final.ism")
    last = None
    for i in range(tries):
        try:
            text = _get(url, timeout=240)
            break
        except (urllib.error.URLError, urllib.error.HTTPError) as e:
            last = e
            time.sleep(3 * (i + 1))
    else:
        raise RuntimeError("could not fetch %s after %d tries (%s)"
                           % (url, tries, last))
    out = []
    for line in text.splitlines():
        parts = line.split()
        if parts:
            out.append(parts[0])
    return out


def dude(argv=()) -> str:
    """Real actives and DUD-E's property-matched decoys, with RDKit descriptors.

    The decoys matter as much as the actives: DUD-E matches them to the actives
    on bulk properties precisely so that enrichment cannot be won by a molecular
    weight detector. That property matching is what the judge checks."""
    from rdkit import Chem, RDLogger
    from rdkit.Chem import Descriptors, rdMolDescriptors
    RDLogger.DisableLog("rdApp.*")

    c = _corpus.DUDE
    d = c.dir()
    d.mkdir(parents=True, exist_ok=True)
    # DUD-E ships ~50 decoys per active, and that ratio IS the benchmark: a
    # library that is 40% active makes EF@1% saturate at 1/0.4 = 2.5, which
    # every method reaches and none exceeds. Ranking by molecular weight scored
    # exactly what fingerprint similarity scored until this was fixed. So cap
    # the ACTIVES and keep the ratio, rather than the reverse.
    max_actives = int(argv[0]) if argv else 50
    cap = max_actives * 50

    def describe(smiles: str) -> Optional[List[float]]:
        m = Chem.MolFromSmiles(smiles)
        if m is None:
            return None
        return [Descriptors.MolWt(m), Descriptors.MolLogP(m),
                Descriptors.TPSA(m), float(Descriptors.NumRotatableBonds(m)),
                float(rdMolDescriptors.CalcNumHBD(m)),
                float(rdMolDescriptors.CalcNumHBA(m)),
                float(rdMolDescriptors.CalcNumRings(m)),
                float(Descriptors.FractionCSP3(m))]

    targets, skipped = {}, []
    for t in DUDE_TARGETS:
        try:
            rows = []
            for kind in ("active", "decoy"):
                smis = _dude_smiles(t, kind)
                smis = smis[:max_actives] if kind == "active" else smis[:cap]
                for sm in smis:
                    v = describe(sm)
                    if v is not None:
                        # SMILES kept: fingerprints are computed at benchmark
                        # time, so the descriptor set can change without
                        # re-downloading 4,000 molecules.
                        rows.append({"d": v, "y": 1 if kind == "active" else 0,
                                     "smiles": sm})
        except RuntimeError as e:
            skipped.append("%s (%s)" % (t, e))
            continue
        if len(rows) < 50 or sum(r["y"] for r in rows) < 10:
            skipped.append("%s (only %d molecules)" % (t, len(rows)))
            continue
        targets[t] = rows
    if len(targets) < 4:
        raise RuntimeError("only %d targets fetched, need >= 4 so that two can "
                           "be held out entirely. Skipped: %s"
                           % (len(targets), "; ".join(skipped)))
    (d / "targets.json").write_text(json.dumps(targets))
    _provenance(d, c, targets=list(targets),
                counts={t: {"actives": sum(r["y"] for r in rows),
                            "decoys": sum(1 - r["y"] for r in rows)}
                        for t, rows in targets.items()},
                active_fraction={t: round(sum(r["y"] for r in rows) / len(rows), 4)
                                 for t, rows in targets.items()},
                descriptors=["MolWt", "MolLogP", "TPSA", "RotB", "HBD", "HBA",
                             "Rings", "FractionCSP3"],
                note="decoys are DUD-E's property-matched set; the judge checks "
                     "that matching rather than assuming it")
    n = sum(len(v) for v in targets.values())
    return "%s: %d molecules across %d targets → %s" % (c.key, n, len(targets), d)


# ---------------------------------------------------------- not yet implemented

_KBP_RAW = ("https://raw.githubusercontent.com/ababier/open-kbp/master/"
            "provided-data/%s/pt_%d/%s")
#: 128^3, the OpenKBP grid.
KBP_SHAPE = (128, 128, 128)
KBP_STRUCTURES = ("PTV70", "PTV63", "PTV56", "Brainstem", "SpinalCord",
                  "LeftParotid", "RightParotid", "Mandible")


def _kbp_sparse(text, shape=KBP_SHAPE, dtype=float):
    """OpenKBP ships each volume as (flat_index, value) pairs. A structure mask
    has the value column empty — the index alone is the membership."""
    import numpy as np
    vol = np.zeros(int(np.prod(shape)), dtype)
    for line in text.splitlines()[1:]:
        if not line.strip():
            continue
        idx, _, val = line.partition(",")
        try:
            k = int(idx)
        except ValueError:
            continue
        vol[k] = float(val) if val.strip() else 1.0
    return vol.reshape(shape)


def open_kbp(argv=()) -> str:
    """Real head-and-neck plans: CT, clinical dose, targets and organs at risk.

    The clinical dose is the answer key and never enters the sandbox, exactly as
    the reconstruction ground truth does not elsewhere. A planner able to read
    the delivered plan would be copying it, not planning."""
    import numpy as np
    c = _corpus.OPENKBP
    d = c.dir()
    d.mkdir(parents=True, exist_ok=True)
    n = int(argv[0]) if argv else 12

    kept, index = [], {}
    for pid in range(1, n * 4):
        if len(kept) >= n:
            break
        try:
            vox = _get(_KBP_RAW % ("train-pats", pid, "voxel_dimensions.csv"), timeout=90)
            ct = _kbp_sparse(_get(_KBP_RAW % ("train-pats", pid, "ct.csv"), timeout=240))
            dose = _kbp_sparse(_get(_KBP_RAW % ("train-pats", pid, "dose.csv"), timeout=240))
            mask = _kbp_sparse(_get(_KBP_RAW % ("train-pats", pid,
                                                "possible_dose_mask.csv"), timeout=240))
        except (urllib.error.URLError, urllib.error.HTTPError):
            continue
        structs = {}
        for name in KBP_STRUCTURES:
            try:
                structs[name] = _kbp_sparse(
                    _get(_KBP_RAW % ("train-pats", pid, name + ".csv"), timeout=120),
                    dtype=np.uint8).astype(bool)
            except (urllib.error.URLError, urllib.error.HTTPError):
                structs[name] = np.zeros(KBP_SHAPE, bool)
        if not structs["PTV70"].any() or float(dose.max()) <= 0:
            continue
        spacing = [float(x) for x in vox.split()]
        np.savez_compressed(d / ("pt_%d.npz" % pid), ct=ct.astype(np.float32),
                            dose=dose.astype(np.float32),
                            possible=mask.astype(bool),
                            spacing=np.array(spacing),
                            **{k: v for k, v in structs.items()})
        kept.append(pid)
        index[str(pid)] = {"file": "pt_%d.npz" % pid,
                           "structures": [k for k, v in structs.items() if v.any()],
                           "dose_max": float(dose.max())}
    if len(kept) < 4:
        raise RuntimeError("only %d OpenKBP patients fetched" % len(kept))
    (d / "index.json").write_text(json.dumps({"patients": index,
                                              "shape": list(KBP_SHAPE)}))
    _provenance(d, c, patients=kept, n=len(kept), shape=list(KBP_SHAPE),
                structures=list(KBP_STRUCTURES),
                note="the clinical dose is the answer key and is withheld from "
                     "the sandbox")
    return "%s: %d real head-and-neck plans -> %s" % (c.key, len(kept), d)


_OSF = "https://files.osf.io/v1/resources/dv2ag/providers/googledrive/%s"

#: Red, vascular findings — the ones a haemoglobin prior is physically able to
#: see. Kept as one positive class because they share the mechanism; each on its
#: own comes from too few patients to split.
KV_POSITIVE = ("angiectasia", "blood_fresh", "erythema", "blood_hematin")
KV_NEGATIVE = "normal_clean_mucosa"
THUMB = 32


def kvasir_capsule(argv=()) -> str:
    """Real capsule endoscopy frames, with the video id that makes a split honest.

    The patient count is the thing to look at here, not the frame count.
    `Blood - fresh` is 446 frames from **two** videos; splitting it by patient
    gives one patient a side, which is not an evaluation. So the positive class
    is the red vascular findings together — angiectasia, fresh blood, erythema,
    hematin — which is clinically coherent (haemoglobin absorption is the signal
    in all of them) and spans enough videos to hold some out. The per-class
    video counts are written into the metadata so the limitation travels with
    the data instead of being rediscovered.
    """
    import csv as _csv
    import io as _io
    import tarfile
    import numpy as np
    from PIL import Image

    c = _corpus.KVASIR_CAPSULE
    d = c.dir()
    d.mkdir(parents=True, exist_ok=True)
    per_video_neg = int(argv[0]) if argv else 80

    meta_raw = _get(_OSF % "metadata.csv", timeout=600)
    rows = list(_csv.DictReader(_io.StringIO(meta_raw), delimiter=";"))
    by_file = {r["filename"]: r for r in rows}
    per_class_videos = {}
    for r in rows:
        per_class_videos.setdefault(r["finding_class"], set()).add(r["video_id"])

    X, thumbs, y, vid, cls = [], [], [], [], []

    def take(archive: str, label: int, per_video=None):
        """Sample per VIDEO, not per archive.

        A global cap takes whatever the tar yields first, which is the first few
        videos: capping normal mucosa at 2500 frames gave 2500 negatives from 3
        patients, so a patient-disjoint split would have been three patients
        wide on the negative side. The whole point of splitting by patient is
        lost if the patients are three."""
        raw = _get(_OSF % ("labelled_images/%s.tar.gz" % archive),
                   timeout=1800, binary=True)
        tf = tarfile.open(fileobj=_io.BytesIO(raw), mode="r:gz")
        n = 0
        seen = {}
        for m in tf:
            if not m.isfile() or not m.name.lower().endswith((".jpg", ".jpeg")):
                continue
            base = m.name.rsplit("/", 1)[-1]
            row = by_file.get(base)
            if row is None:
                continue
            v = row["video_id"]
            if per_video is not None and seen.get(v, 0) >= per_video:
                continue
            try:
                im = Image.open(_io.BytesIO(tf.extractfile(m).read())).convert("RGB")
            except Exception:
                continue
            a = np.asarray(im, np.float32) / 255.0
            # The capsule image sits in a black circular surround; sampling the
            # centre keeps the optics out of the colour statistics.
            h, w, _ = a.shape
            cy, cx, r = h // 2, w // 2, min(h, w) // 4
            core = a[cy - r:cy + r, cx - r:cx + r]
            X.append(core.reshape(-1, 3).mean(axis=0))
            thumbs.append(np.asarray(im.resize((THUMB, THUMB)), np.uint8))
            y.append(label); vid.append(v); cls.append(row["finding_class"])
            seen[v] = seen.get(v, 0) + 1
            n += 1
        return n

    counts = {}
    for a in KV_POSITIVE:
        counts[a] = take(a, 1)
    counts[KV_NEGATIVE] = take(KV_NEGATIVE, 0, per_video=per_video_neg)

    X = np.array(X, np.float32)
    if X.shape[0] < 200 or sum(y) < 50:
        raise RuntimeError("too few frames: %d total, %d positive" % (len(y), sum(y)))
    np.savez_compressed(d / "frames.npz", rgb=X, thumb=np.array(thumbs, np.uint8),
                        label=np.array(y, np.int8),
                        video=np.array(vid), finding=np.array(cls))
    pos_v = sorted({v for v, l in zip(vid, y) if l == 1})
    neg_v = sorted({v for v, l in zip(vid, y) if l == 0})
    (d / "metadata.json").write_text(json.dumps(
        {"frames": int(len(y)), "positive": int(sum(y)),
         "positive_videos": pos_v, "negative_videos": neg_v,
         "counts": counts,
         "videos_per_class": {k: len(v) for k, v in sorted(per_class_videos.items())},
         "positive_classes": list(KV_POSITIVE), "negative_class": KV_NEGATIVE}))
    _provenance(d, c, frames=int(len(y)), positive=int(sum(y)),
                positive_videos=len(pos_v), negative_videos=len(neg_v),
                videos_per_class={k: len(v) for k, v in sorted(per_class_videos.items())},
                note="positives are the red vascular findings pooled, because "
                     "each alone spans too few videos for a patient-disjoint "
                     "split — Blood-fresh is 2 videos")
    return ("%s: %d frames (%d positive) from %d positive and %d negative "
            "videos -> %s" % (c.key, len(y), sum(y), len(pos_v), len(neg_v), d))


# Restored 2026-08-06. Both this constant and the helper below were deleted by
# accident in 731a6e3, when the Kvasir fetcher was written over them. Nothing
# caught it: every machine that runs the tests already had ldct on disk, so the
# only code path that touches these names is the one nobody re-ran. It surfaced
# the first time the corpus was fetched onto a second machine.
_TCIA = "https://services.cancerimagingarchive.net/nbia-api/services/v1/%s"


def _tcia(endpoint: str, **params) -> Any:
    q = urllib.parse.urlencode(params)
    return json.loads(_get("%s?%s" % (_TCIA % endpoint, q), timeout=180))


def ldct(argv=()) -> str:
    """Real paired full-dose and low-dose CT from TCIA.

    No dose simulation: this collection ships the *same patient* reconstructed
    at full dose and at reduced dose, which is the thing a simulated reduction
    is only ever an approximation of. The full-dose reconstruction is the answer
    key and never enters the sandbox.

    Lesion masks are not part of the collection, so detectability is measured on
    an inserted low-contrast signal — standard practice for task-based image
    quality, and labelled as inserted rather than passed off as pathology."""
    import numpy as np
    import pydicom

    c = _corpus.LDCT
    d = c.dir()
    d.mkdir(parents=True, exist_ok=True)
    want = int(argv[0]) if argv else 4          # patients
    per_pat = 3                                 # slices each

    patients = _tcia("getPatient", Collection="LDCT-and-Projection-data")
    pairs, meta = [], []
    for p in patients:
        if len(pairs) >= want:
            break
        pid = p.get("PatientId") or p.get("PatientID")
        try:
            series = _tcia("getSeries", Collection="LDCT-and-Projection-data",
                           PatientID=pid)
        except Exception:
            continue
        by = {}
        for s_ in series:
            desc = (s_.get("SeriesDescription") or "").lower()
            # Reconstructed images only. The projection series are raw sinograms
            # and are two orders of magnitude larger.
            if "images" not in desc:
                continue
            if "full" in desc:
                by["full"] = s_
            elif "low" in desc:
                by["low"] = s_
        if "full" not in by or "low" not in by:
            continue
        try:
            # Read every slice's z position, then pair the two series BY
            # POSITION. Sorting zip entry names does not order a DICOM series
            # anatomically, and pairing on that order silently compares one
            # patient's lung to a different part of the same lung: the first
            # version of this had full[0] matching low[2] better than low[0].
            byz = {}
            for kind, s_ in by.items():
                raw = _get(_TCIA % "getImage" + "?" + urllib.parse.urlencode(
                    {"SeriesInstanceUID": s_["SeriesInstanceUID"]}),
                    timeout=900, binary=True)
                import zipfile
                zf = zipfile.ZipFile(io.BytesIO(raw))
                zmap = {}
                for nm in zf.namelist():
                    try:
                        ds = pydicom.dcmread(io.BytesIO(zf.read(nm)))
                        z = float(ds.ImagePositionPatient[2])
                    except Exception:
                        continue
                    arr = ds.pixel_array.astype(np.float32)
                    slope = float(getattr(ds, "RescaleSlope", 1) or 1)
                    inter = float(getattr(ds, "RescaleIntercept", 0) or 0)
                    zmap[round(z, 2)] = arr * slope + inter      # Hounsfield units
                byz[kind] = zmap
            shared = sorted(set(byz["full"]) & set(byz["low"]))
            if len(shared) < per_pat:
                meta.append({"patient": pid,
                             "skipped": "only %d shared slice positions" % len(shared)})
                continue
            mid = len(shared) // 2
            take = shared[mid - per_pat // 2: mid - per_pat // 2 + per_pat]
            vols = {k: np.stack([byz[k][z] for z in take]) for k in ("full", "low")}
        except Exception as e:
            meta.append({"patient": pid, "skipped": str(e)[:120]})
            continue
        if vols["full"].shape != vols["low"].shape:
            continue
        pairs.append((pid, vols["full"], vols["low"]))
        rmse = float(np.sqrt(((vols["full"] - vols["low"]) ** 2).mean()))
        meta.append({"patient": pid, "slices": int(vols["full"].shape[0]),
                     "shape": list(vols["full"].shape[1:]),
                     "z_positions": [float(z) for z in take],
                     "pair_rmse_hu": rmse})

    if len(pairs) < 2:
        raise RuntimeError("only %d paired patients fetched from TCIA" % len(pairs))
    np.savez_compressed(d / "volumes.npz",
                        **{("full_%s" % pid): f for pid, f, _ in pairs},
                        **{("low_%s" % pid): l for pid, _, l in pairs})
    (d / "metadata.json").write_text(json.dumps(
        {"patients": [p for p, _, _ in pairs], "units": "HU", "detail": meta}))
    _provenance(d, c, patients=[p for p, _, _ in pairs],
                note="paired full-dose and low-dose reconstructions of the same "
                     "patient; no dose simulation. Lesions are inserted for "
                     "task-based assessment and are labelled as inserted.")
    return ("%s: %d patients, real paired full/low dose → %s"
            % (c.key, len(pairs), d))


# --------------------------------------------------- CAVE (computational imaging)

_CAVE = "https://cave.cs.columbia.edu/old/databases/multispectral/zip/%s.zip"

#: Scenes chosen for spectral variety rather than looks: pigments, fabric,
#: food and a colour chart span very different spectral signatures, and a
#: reconstruction that only works on smooth spectra should fail somewhere here.
CAVE_SCENES = ("balloons_ms", "chart_and_stuffed_toy_ms", "cloth_ms",
               "beads_ms", "superballs_ms", "flowers_ms",
               "feathers_ms", "photo_and_face_ms", "thread_spools_ms")


def cave_hyperspectral(argv=()) -> str:
    """Real hyperspectral scenes for the CASSI benchmark.

    The benchmark it replaces synthesised its own cube from Gaussian blobs —
    trivially sparse, unusually kind to a total-variation prior, and its own
    docstring called it "a synthetic stand-in for real KAIST-like data". Real
    scenes carry real spectral correlation and real spatial structure, which is
    what a reconstruction prior is actually up against.

    **The measurement is still simulated.** These are real scenes pushed through
    the forward model, not captures from a physical CASSI instrument. That is a
    meaningful step and it is not the same thing, and the benchmark says so
    rather than letting "real data" cover both.
    """
    import io as _io
    import zipfile
    import numpy as np
    from PIL import Image

    c = _corpus.CAVE
    d = c.dir()
    d.mkdir(parents=True, exist_ok=True)
    size = int(argv[0]) if argv else 64
    bands = int(argv[1]) if len(argv) > 1 else 8

    keep, meta = {}, {}
    for name in CAVE_SCENES:
        try:
            raw = _get(_CAVE % name, timeout=900, binary=True)
            # Parse inside the guard, not after it. A wrong scene name returns
            # an HTML error page that a range probe answers 206 to, so it looks
            # available and is not a zip — and with the parse outside the guard
            # one bad name threw away four completed multi-megabyte downloads.
            zf = zipfile.ZipFile(_io.BytesIO(raw))
        except Exception as e:
            meta[name] = {"skipped": "%s: %s" % (type(e).__name__, str(e)[:80])}
            continue
        pngs = sorted(x for x in zf.namelist()
                      if x.lower().endswith(".png") and "_ms_" in x)
        if len(pngs) < 31:
            meta[name] = {"skipped": "only %d bands" % len(pngs)}
            continue
        # Spread the kept bands across 400-700nm rather than taking a block:
        # a contiguous slice would be far more spectrally correlated than the
        # full range and would make the reconstruction easier than it is.
        idx = np.linspace(0, len(pngs) - 1, bands).round().astype(int)
        cube = []
        for i in idx:
            im = Image.open(_io.BytesIO(zf.read(pngs[i])))
            a = np.asarray(im, np.float32)
            if a.ndim == 3:
                a = a.mean(axis=2)
            h, w = a.shape
            s0 = min(h, w)
            a = a[(h - s0) // 2:(h - s0) // 2 + s0, (w - s0) // 2:(w - s0) // 2 + s0]
            step = max(1, s0 // size)
            a = a[::step, ::step][:size, :size]
            cube.append(a)
        # Normalise the CUBE, not each band. Per-band normalisation was the
        # first version and it destroys the thing this data is for: dividing
        # every band by its own maximum flattens the relative amplitudes
        # between bands, which IS the spectral signature a reconstruction is
        # trying to recover. One global scale preserves the spectrum and puts
        # the cube in [0, 1].
        arr = np.stack(cube, axis=-1).astype(np.float32)
        peak = float(arr.max())
        if peak > 0:
            arr = arr / peak
        if arr.shape != (size, size, bands):
            meta[name] = {"skipped": "shape %s" % (arr.shape,)}
            continue
        keep[name] = arr
        meta[name] = {"shape": list(arr.shape), "mean": float(arr.mean())}

    if len(keep) < 4:
        raise RuntimeError("only %d CAVE scenes usable" % len(keep))
    np.savez_compressed(d / "scenes.npz", **keep)
    (d / "metadata.json").write_text(json.dumps(
        {"scenes": sorted(keep), "shape": [size, size, bands],
         "bands_nm": "400-700 spread across %d of 31" % bands, "detail": meta}))
    _provenance(d, c, scenes=sorted(keep), shape=[size, size, bands],
                note="real scenes; the CASSI measurement is still simulated by "
                     "applying the forward model, which is not the same as a "
                     "capture from a physical instrument")
    return "%s: %d real scenes at %dx%dx%d -> %s" % (c.key, len(keep), size, size, bands, d)


# ---------------------------------------------------- methylation and age

#: How many CpG probes to keep, and how they are chosen.
#:
#: **Chosen without looking at age.** A subset picked by correlation with age
#: would be selection on the target: the held-out sites would already have voted
#: on which probes exist, and the clock's error would be optimistic for a reason
#: no amount of held-out validation could detect. A seeded random subset cannot
#: do that. Age signal in the methylome is diffuse enough that 20k random probes
#: support a clock comfortably, and the *method* is still free to select among
#: them — inside its training fold, which is where selection belongs.
METHYL_N_PROBES = 20000
METHYL_PROBE_SEED = 20260805

_GSE = "GSE40279"
_GEO_META = ("https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi"
             "?acc=%s&targ=gsm&form=text&view=brief" % _GSE)
_GEO_BETA = ("https://ftp.ncbi.nlm.nih.gov/geo/series/GSE40nnn/%s/suppl/"
             "%s_average_beta.txt.gz" % (_GSE, _GSE))


def _methyl_metadata():
    """Ages, sex and source site per sample, from the 1.1 MB GEO metadata.

    The full SOFT family file is 2.8 GB and carries the same fields; this is the
    same information for a four-hundredth of the download."""
    import re
    raw = _get(_GEO_META)          # _get already decodes
    samples, cur = [], None
    for line in raw.split("\n"):
        line = line.strip()
        if line.startswith("^SAMPLE"):
            if cur:
                samples.append(cur)
            cur = {"gsm": line.split("=")[-1].strip()}
        elif cur is not None and "Sample_characteristics" in line:
            v = line.split("=", 1)[-1].strip()
            if ":" not in v:
                continue
            k, val = v.split(":", 1)
            cur[k.strip().lower()] = val.strip()
        elif cur is not None and line.startswith("!Sample_title"):
            cur["title"] = line.split("=", 1)[-1].strip()
    if cur:
        samples.append(cur)
    out = []
    for s in samples:
        age = s.get("age (y)") or s.get("age")
        if not age or not re.match(r"^\d+$", age):
            continue
        out.append({"gsm": s["gsm"], "title": s.get("title", ""),
                    "age": int(age),
                    "male": 1 if (s.get("gender", "").upper().startswith("M")) else 0,
                    # The source institution. A clock validated on a re-split of
                    # one cohort is the mistake `cancer` had to correct; this is
                    # what makes a site-disjoint split possible here.
                    "site": s.get("source", "unknown")})
    return out


def methylation_age(argv=None) -> str:
    """GEO GSE40279: whole-blood methylation with chronological age.

    Streams the 1.1 GB beta matrix and keeps a fixed probe subset, so the
    download is large and what lands on disk is not. Nothing is written until
    the whole parse succeeds."""
    import gzip, io, json, re
    import numpy as np
    from .. import corpus as _c

    c = _c.METHYLATION_AGE
    d = c.dir(); d.mkdir(parents=True, exist_ok=True)

    meta = _methyl_metadata()
    if len(meta) < 300:
        raise RuntimeError("GEO returned %d usable samples for %s; expected ~656. "
                           "The metadata format may have changed." % (len(meta), _GSE))
    # The two files do not share an identifier directly. Beta columns are
    # "X1001"; sample titles are "age 67y 1001". The trailing number is the
    # subject id in both, and it is the only thing that joins them — matching on
    # the title verbatim finds nothing, which is what the guard below caught.
    def _subject_key(s):
        m_ = re.findall(r"(\d+)", str(s))
        return m_[-1] if m_ else None

    by_key = {}
    for m_ in meta:
        k = _subject_key(m_["title"])
        if k:
            by_key[k] = m_

    print("  %d samples with an age, %d source sites"
          % (len(meta), len({m["site"] for m in meta})))
    print("  streaming %s (~1.1 GB) and keeping %d probes ..." % (_GSE, METHYL_N_PROBES))

    resp = _open_stream(_GEO_BETA)
    gz = gzip.GzipFile(fileobj=resp)
    header = gz.readline().decode("utf8", "ignore").rstrip("\n").split("\t")
    # Column layout is: probe id, then <sample> and <sample>.Detection Pval pairs.
    cols, keep_idx = [], []
    for i, h in enumerate(header[1:], start=1):
        h = h.strip().strip('"')
        if h.lower().endswith("pval") or "detection" in h.lower():
            continue
        cols.append(h); keep_idx.append(i)
    matched = [h for h in cols if _subject_key(h) in by_key]
    if len(matched) < 300:
        raise RuntimeError("only %d of %d beta columns matched a sample title; "
                           "the column naming may have changed" % (len(matched), len(cols)))

    rng = np.random.default_rng(METHYL_PROBE_SEED)
    rows, ids = [], []
    n_seen = 0
    # Reservoir sampling: one pass, no need to know the probe count in advance
    # and no need to hold 450k x 656 in memory to choose from.
    reservoir_row, reservoir_id = [], []
    for line in gz:
        parts = line.decode("utf8", "ignore").rstrip("\n").split("\t")
        if len(parts) <= max(keep_idx):
            continue
        pid = parts[0].strip().strip('"')
        if not pid.startswith("cg"):
            continue
        n_seen += 1
        vals = np.array([_to_float(parts[i]) for i in keep_idx], dtype=np.float32)
        if len(reservoir_row) < METHYL_N_PROBES:
            reservoir_row.append(vals); reservoir_id.append(pid)
        else:
            j = int(rng.integers(0, n_seen))
            if j < METHYL_N_PROBES:
                reservoir_row[j] = vals; reservoir_id[j] = pid
        if n_seen % 50000 == 0:
            print("    %d probes scanned" % n_seen)
    gz.close(); resp.close()
    if n_seen < 100000:
        raise RuntimeError("only %d probes parsed; expected ~450k" % n_seen)

    B = np.vstack(reservoir_row).T            # samples x probes
    order = [by_key[_subject_key(h)] for h in cols if _subject_key(h) in by_key]
    sel = [k for k, h in enumerate(cols) if _subject_key(h) in by_key]
    B = B[sel]
    age = np.array([m["age"] for m in order], dtype=np.float64)
    male = np.array([m["male"] for m in order], dtype=np.int64)
    site = np.array([m["site"] for m in order])

    np.save(d / "betas.npy", B)
    np.save(d / "age.npy", age)
    np.save(d / "male.npy", male)
    np.save(d / "site.npy", site)
    (d / "cpg_ids.json").write_text(json.dumps(reservoir_id))
    (d / "metadata.json").write_text(json.dumps({
        "series": _GSE, "samples": int(len(age)), "probes": int(B.shape[1]),
        "probes_scanned": int(n_seen), "probe_seed": METHYL_PROBE_SEED,
        "age_range": [int(age.min()), int(age.max())],
        "sites": sorted({str(s) for s in site}),
        "tissue": "whole blood", "platform": "Illumina 450k",
        "note": ("probes chosen by seeded reservoir sampling, never by "
                 "correlation with age — selecting probes on the target would "
                 "make held-out error optimistic in a way held-out data cannot "
                 "detect"),
    }, indent=1))
    return ("%s: %d samples x %d probes from %d scanned, ages %d-%d, %d sites"
            % (c.key, len(age), B.shape[1], n_seen, age.min(), age.max(),
               len(set(site.tolist()))))
