"""The five domain runners, and what each field counts as a defensible result.

The judges are the interesting part, and they differ on purpose. Six agents
exist because "better" means six different things; a shared scorer would quietly
make them one, and each field's characteristic failure would stop being visible.

    low-dose-ct       fidelity up, lesion gone → FAIL. Not a mixed result.
    medical-physics   per-constraint, max not mean, and never "approved".
    pill-camera       patient-disjoint verified in code, per-class, and the
                      effect measured against its own seed spread.
    drug-design       held-out targets, and decoys checked for property bias —
                      unmatched decoys make enrichment a weight detector.
    cancer            external cohort, and calibration reported with
                      discrimination or the number cannot be read as a risk.

Scoring runs in this process against the withheld answer key, never in the
sandbox. See `common.py`.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple

import numpy as np

from .common import DomainBenchmark, Verdict


# ------------------------------------------------------------------ helpers

def _auc(scores: np.ndarray, labels: np.ndarray) -> float:
    """Mann-Whitney AUC. Ties get half credit, which matters here because a
    coarse score produces plenty of them."""
    pos, neg = scores[labels == 1], scores[labels == 0]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    diff = pos[:, None] - neg[None, :]
    return float(((diff > 0).sum() + 0.5 * (diff == 0).sum()) / (len(pos) * len(neg)))


def _c_index(risk: np.ndarray, time: np.ndarray, event: np.ndarray) -> float:
    """Harrell's C over comparable pairs."""
    num = den = 0.0
    for i in np.where(event == 1)[0]:
        later = time > time[i]
        den += later.sum()
        num += (risk[i] > risk[later]).sum() + 0.5 * (risk[i] == risk[later]).sum()
    return float(num / den) if den else float("nan")


def _psnr(a: np.ndarray, b: np.ndarray) -> float:
    mse = float(np.mean((a - b) ** 2))
    peak = float(max(b.max() - b.min(), 1e-9))
    return float(10.0 * np.log10(peak ** 2 / max(mse, 1e-12)))


# ------------------------------------------------------------- low-dose CT

def _score_ldct(seed_ws: Path, run_ws: Path) -> Dict[str, float]:
    truth = np.load(seed_ws / "data" / "ground_truth.npy")
    lesion = np.load(seed_ws / "data" / "lesion_mask.npy")
    rec = np.load(run_ws / "results" / "reconstruction.npy")
    body = (truth > 0.5) & ~lesion
    # Detectability: contrast of the lesion over the surrounding tissue,
    # divided by the noise it has to be seen against.
    ring = body & ~lesion
    # Peak, not mean: blurring a small object spreads its signal into the
    # surround, so the mean over the lesion mask stays put while the thing a
    # radiologist would actually see — the peak above background — collapses.
    contrast = float(rec[lesion].max() - rec[ring].mean())
    noise = float(rec[ring].std())
    truth_contrast = float(truth[lesion].max() - truth[ring].mean())
    return {"psnr": _psnr(rec, truth),
            "rmse": float(np.sqrt(np.mean((rec - truth) ** 2))),
            "lesion_cnr": abs(contrast) / max(noise, 1e-9),
            "lesion_contrast_retained": abs(contrast) / max(abs(truth_contrast), 1e-9)}


def _judge_ldct(m: Dict[str, float]) -> Verdict:
    reasons, ok = [], True
    if m["psnr"] < 12.0:
        ok = False
        reasons.append("PSNR %.3g dB — the reconstruction did not converge" % m["psnr"])
    if m["lesion_cnr"] < 1.0:
        ok = False
        reasons.append(
            "lesion CNR %.3g: the low-contrast signal is gone. A fidelity gain "
            "with the lesion smoothed away is a FAILURE, not a mixed result — "
            "the scan was ordered to find that lesion." % m["lesion_cnr"])
    if m["lesion_contrast_retained"] < 1.0:
        ok = False
        reasons.append(
            "only %.0f%% of the lesion's peak contrast survived — this is the "
            "smoothing failure: PSNR rose and the finding went with it"
            % (100 * m["lesion_contrast_retained"]))
    if ok:
        reasons.append("both metrics reported together, as this field requires")
    return Verdict(ok, tuple(reasons), m)


LDCT = DomainBenchmark(
    agent="low-dose-ct",
    goal="reconstruct a sparse-view low-dose CT scan without losing the lesion",
    package="ldct",
    deliverables=("results/reconstruction.npy",),
    answer_key=("data/ground_truth.npy", "data/lesion_mask.npy"),
    score=_score_ldct, judge=_judge_ldct,
    criteria=("PSNR ≥ 12 dB against the paired full-dose phantom",
              "lesion CNR ≥ 1.0 — detectability reported beside fidelity, always",
              "the lesion's peak contrast survives reconstruction",
              "an edge-preserving prior clears these; a PSNR-maximising blur "
              "does not, which is the whole point of scoring both"),
)


# -------------------------------------------------------- medical physics

def _score_medphys(seed_ws: Path, run_ws: Path) -> Dict[str, float]:
    import json
    target = np.load(seed_ws / "data" / "target.npy")
    oar = np.load(seed_ws / "data" / "oar.npy")
    proto = json.loads((seed_ws / "data" / "protocol.json").read_text())
    dose = np.load(run_ws / "results" / "dose.npy")
    return {"target_D95": float(np.percentile(dose[target], 5)),
            "target_D95_min": float(proto["target_D95_min"]),
            "oar_Dmax": float(dose[oar].max()),
            "oar_Dmax_limit": float(proto["oar_Dmax"]),
            "oar_Dmean": float(dose[oar].mean()),
            "oar_Dmean_limit": float(proto["oar_Dmean"]),
            "hot_spot": float(dose.max()),
            "hot_spot_limit": float(proto["hot_spot_max"])}


def _judge_medphys(m: Dict[str, float]) -> Verdict:
    """Per constraint, and the headline is the max — the tail is the clinical
    event, and a mean would hide exactly the failure this field cares about."""
    checks = (("target D95", m["target_D95"] >= m["target_D95_min"],
               "%.4g vs ≥ %.4g Gy" % (m["target_D95"], m["target_D95_min"])),
              ("OAR Dmax", m["oar_Dmax"] <= m["oar_Dmax_limit"],
               "%.4g vs ≤ %.4g Gy" % (m["oar_Dmax"], m["oar_Dmax_limit"])),
              ("OAR Dmean", m["oar_Dmean"] <= m["oar_Dmean_limit"],
               "%.4g vs ≤ %.4g Gy" % (m["oar_Dmean"], m["oar_Dmean_limit"])),
              ("hot spot", m["hot_spot"] <= m["hot_spot_limit"],
               "%.4g vs ≤ %.4g Gy" % (m["hot_spot"], m["hot_spot_limit"])))
    reasons = ["%s %s — %s" % (n, "met" if ok else "VIOLATED", d)
               for n, ok, d in checks]
    reasons.append("this is a plan CANDIDATE; a qualified medical physicist "
                   "signs anything that reaches a patient")
    return Verdict(all(ok for _, ok, _ in checks), tuple(reasons), m)


MEDPHYS = DomainBenchmark(
    agent="medical-physics",
    goal="produce a plan candidate meeting every protocol constraint",
    package="medphys",
    deliverables=("results/dose.npy", "results/plan_candidate.json"),
    answer_key=(),      # the protocol IS given; what is withheld is approval
    score=_score_medphys, judge=_judge_medphys,
    criteria=("target D95 ≥ the prescribed minimum",
              "OAR Dmax and Dmean within protocol",
              "no hot spot above the limit",
              "output is a candidate; a physicist signs"),
)


# ------------------------------------------------------------- pill camera

def _score_capsule(seed_ws: Path, run_ws: Path) -> Dict[str, float]:
    y = np.load(seed_ws / "data" / "labels.npy")
    pid = np.load(run_ws / "data" / "patient_id.npy")
    s = np.load(run_ws / "results" / "scores.npy")
    base = np.load(run_ws / "results" / "baseline_scores.npy")
    # Patient-disjoint, verified here rather than asserted anywhere: the test
    # patients are held out whole, and the check below proves no id crosses.
    test_p = np.unique(pid)[::2]
    m = np.isin(pid, test_p)
    crossed = len(set(pid[m]) & set(pid[~m]))
    return {"auc": _auc(s[m], y[m]), "baseline_auc": _auc(base[m], y[m]),
            "auc_train_side": _auc(s[~m], y[~m]),
            "patients_crossing_the_split": float(crossed),
            "test_patients": float(len(test_p)),
            "positives_in_test": float(y[m].sum())}


def _judge_capsule(m: Dict[str, float]) -> Verdict:
    reasons, ok = [], True
    if m["patients_crossing_the_split"] > 0:
        ok = False
        reasons.append("%d patient(s) on both sides of the split — consecutive "
                       "frames are near-duplicates and this inflates everything"
                       % int(m["patients_crossing_the_split"]))
    else:
        reasons.append("patient-disjoint split verified in code, not asserted")
    if m["positives_in_test"] < 3:
        ok = False
        reasons.append("only %d positives in the test split" % int(m["positives_in_test"]))
    if not (m["auc"] > m["baseline_auc"]):
        ok = False
        reasons.append("the physics prior (%.4g) did not beat the naive baseline "
                       "(%.4g)" % (m["auc"], m["baseline_auc"]))
    if m["auc"] < 0.6:
        ok = False
        reasons.append("AUC %.4g is not a usable signal" % m["auc"])
    reasons.append("one seed is one seed — a claim needs the whole fixed set, "
                   "and the effect measured against its spread")
    return Verdict(ok, tuple(reasons), m)


CAPSULE = DomainBenchmark(
    agent="pill-camera",
    goal="detect bleeding frames using an analytic haemoglobin prior",
    package="capsule",
    deliverables=("results/scores.npy", "results/baseline_scores.npy"),
    answer_key=("data/labels.npy",),
    score=_score_capsule, judge=_judge_capsule,
    criteria=("the split is patient-disjoint, checked programmatically",
              "the prior beats the naive baseline on held-out patients",
              "AUC ≥ 0.6 on the held-out patients"),
)


# ------------------------------------------------------------- drug design

def _ef(scores: np.ndarray, labels: np.ndarray, frac: float = 0.01) -> float:
    n = max(1, int(round(len(scores) * frac)))
    top = np.argsort(-scores)[:n]
    hit_rate = labels[top].mean()
    base = labels.mean()
    return float(hit_rate / base) if base > 0 else float("nan")


def _score_screening(seed_ws: Path, run_ws: Path) -> Dict[str, float]:
    y = np.load(seed_ws / "data" / "labels.npy")
    tid = np.load(run_ws / "data" / "target_id.npy")
    D = np.load(run_ws / "data" / "descriptors.npy")
    s = np.load(run_ws / "results" / "scores.npy")
    held = np.unique(tid)[-2:]                      # targets held out entirely
    m = np.isin(tid, held)
    # Decoy property bias: if actives and decoys differ in bulk properties, then
    # enrichment is measuring molecular weight and not binding.
    bulk_gap = float(abs(D[y == 1][:, 0].mean() - D[y == 0][:, 0].mean())
                     / max(D[:, 0].std(), 1e-9))
    return {"ef_at_1pct": _ef(s[m], y[m]), "auc_heldout": _auc(s[m], y[m]),
            "auc_seen_targets": _auc(s[~m], y[~m]),
            "decoy_bulk_bias_sd": bulk_gap,
            "heldout_targets": float(len(held)),
            "actives_heldout": float(y[m].sum())}


def _judge_screening(m: Dict[str, float]) -> Verdict:
    reasons, ok = [], True
    if m["decoy_bulk_bias_sd"] > 0.35:
        ok = False
        reasons.append("actives and decoys differ by %.2g SD in bulk property — "
                       "this enrichment is a molecular-weight detector"
                       % m["decoy_bulk_bias_sd"])
    else:
        reasons.append("decoys are property-matched (%.2g SD apart)"
                       % m["decoy_bulk_bias_sd"])
    if m["ef_at_1pct"] < 2.0:
        ok = False
        reasons.append("EF@1%% %.3g — no useful enrichment on held-out targets"
                       % m["ef_at_1pct"])
    if m["actives_heldout"] < 3:
        ok = False
        reasons.append("too few held-out actives to say anything")
    reasons.append("a score ranks; it does not measure. Nothing here has been "
                   "made or assayed, and no compound is a candidate")
    return Verdict(ok, tuple(reasons), m)


SCREENING = DomainBenchmark(
    agent="drug-design",
    goal="rank a library against held-out targets and report honest enrichment",
    package="screening",
    deliverables=("results/scores.npy",),
    answer_key=("data/labels.npy", "data/pharmacophores.npy"),
    score=_score_screening, judge=_judge_screening,
    criteria=("EF@1% ≥ 2 on targets held out entirely",
              "decoys property-matched to within 0.35 SD",
              "no activity claimed without an assay"),
)


# ------------------------------------------------------------------ cancer

def _score_onco(seed_ws: Path, run_ws: Path) -> Dict[str, float]:
    d = lambda n: np.load(seed_ws / "data" / (n + ".npy"))
    rd = np.load(run_ws / "results" / "risk_dev.npy")
    re_ = np.load(run_ws / "results" / "risk_ext.npy")
    c_int = _c_index(rd, d("dev_time"), d("dev_event"))
    c_ext = _c_index(re_, d("ext_time"), d("ext_event"))
    # Calibration: do the risk tertiles order the observed median survival?
    t, e = d("ext_time"), d("ext_event")
    q = np.quantile(re_, [1/3, 2/3])
    groups = [t[(re_ <= q[0])], t[(re_ > q[0]) & (re_ <= q[1])], t[re_ > q[1]]]
    meds = [float(np.median(g)) if len(g) else float("nan") for g in groups]
    monotone = float(meds[0] >= meds[1] >= meds[2])
    return {"c_index_internal": c_int, "c_index_external": c_ext,
            "external_drop": c_int - c_ext,
            "calibration_monotone": monotone,
            "median_survival_low_risk": meds[0],
            "median_survival_high_risk": meds[2]}


def _judge_onco(m: Dict[str, float]) -> Verdict:
    reasons, ok = [], True
    if np.isnan(m["c_index_external"]):
        return Verdict(False, ("no external cohort was evaluated — an internal "
                               "number is not a prognostic claim",), m)
    if m["c_index_external"] < 0.58:
        ok = False
        reasons.append("external C-index %.4g — the model did not transport"
                       % m["c_index_external"])
    if not m["calibration_monotone"]:
        ok = False
        reasons.append("risk groups do not order observed survival: "
                       "discrimination without calibration cannot be read as risk")
    reasons.append("internal %.4g → external %.4g (drop %.4g), reported together"
                   % (m["c_index_internal"], m["c_index_external"],
                      m["external_drop"]))
    reasons.append("for a clinician. Not a diagnosis, not advice, no "
                   "patient-level claim")
    return Verdict(ok, tuple(reasons), m)


ONCO = DomainBenchmark(
    agent="cancer",
    goal="fit a risk score and validate it on an external cohort",
    package="onco",
    deliverables=("results/risk_dev.npy", "results/risk_ext.npy"),
    answer_key=(),      # outcomes are the data; what is tested is transport
    score=_score_onco, judge=_judge_onco,
    criteria=("external C-index ≥ 0.58 on a cohort the model never saw",
              "calibration reported with discrimination",
              "no patient-level claim"),
)


BENCHMARKS = {b.agent: b for b in (LDCT, MEDPHYS, CAPSULE, SCREENING, ONCO)}


def benchmark_for(agent: str) -> DomainBenchmark:
    if agent not in BENCHMARKS:
        raise KeyError("no domain runner for %r — have: %s"
                       % (agent, ", ".join(sorted(BENCHMARKS))))
    return BENCHMARKS[agent]
