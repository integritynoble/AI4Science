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

def open_kbp(_argv=()) -> str:
    raise NotImplementedError(
        "open-kbp: the OpenKBP data is distributed through the challenge "
        "repository's own downloader; wire it here before claiming real RT data")


def kvasir_capsule(_argv=()) -> str:
    raise NotImplementedError(
        "kvasir-capsule requires reading and accepting its data-use terms. An "
        "agent may not accept them; fetch it as a person, then point "
        "AI4SCIENCE_DATA at it.")


def ldct(_argv=()) -> str:
    raise NotImplementedError(
        "ldct: real thoracic CT with a simulated dose reduction; wire the TCIA "
        "public-collection download here before claiming real CT data")
