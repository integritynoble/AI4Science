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

from .common import DomainBenchmark, Parameter, Verdict


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


def _km_at(time: np.ndarray, event: np.ndarray, horizon: float) -> float:
    """Kaplan-Meier survival probability at `horizon`."""
    if len(time) == 0:
        return float("nan")
    order = np.argsort(time)
    t, e = time[order], event[order]
    s, n = 1.0, len(t)
    for i, (ti, ei) in enumerate(zip(t, e)):
        if ti > horizon:
            break
        at_risk = n - i
        if ei == 1 and at_risk > 0:
            s *= (1.0 - 1.0 / at_risk)
    return float(s)


def _psnr(a: np.ndarray, b: np.ndarray) -> float:
    mse = float(np.mean((a - b) ** 2))
    peak = float(max(b.max() - b.min(), 1e-9))
    return float(10.0 * np.log10(peak ** 2 / max(mse, 1e-12)))


# ------------------------------------------------------------- low-dose CT

def _score_ldct(seed_ws: Path, run_ws: Path) -> Dict[str, float]:
    """Fidelity against the real full-dose scan, and detectability of the
    inserted signal — reported together or not at all."""
    truth = np.load(seed_ws / "data" / "full_dose.npy")
    lesion = np.load(seed_ws / "data" / "lesion_mask.npy")
    low = np.load(run_ws / "data" / "low_dose.npy")
    rec = np.load(run_ws / "results" / "reconstruction.npy")

    # Background: an annulus of soft tissue around the lesion, excluding it.
    ys, xs = np.nonzero(lesion)
    cy, cx = int(ys.mean()), int(xs.mean())
    yy, xx = np.ogrid[:rec.shape[0], :rec.shape[1]]
    d2 = (yy - cy) ** 2 + (xx - cx) ** 2
    r = int(np.sqrt(lesion.sum() / np.pi)) + 1
    ring = (d2 > (2 * r) ** 2) & (d2 <= (5 * r) ** 2)
    # The background ROI is SOFT TISSUE within that annulus, not the annulus
    # itself. A lesion near the lung leaves the ring straddling a ~1200 HU step
    # from tissue to air, and its standard deviation then measures anatomy: one
    # patient reported 396 HU of "noise" with 35% of the ring air. CNR is
    # contrast over that number, so it fell below the Rose criterion however
    # well the lesion had been restored — the denominator was broken, not the
    # denoiser. A physicist draws this ROI in tissue; so does this now.
    #
    # The membership is decided on the FULL-DOSE reference, which is the answer
    # key and outside the sandbox. Deciding it on the reconstruction would let a
    # method choose its own background.
    tissue = (truth > -200) & (truth < 300)
    ring = ring & tissue
    if ring.sum() < 50:                    # nothing to measure against
        ring = (d2 > (2 * r) ** 2) & (d2 <= (5 * r) ** 2)
    noise_ref = float(np.load(seed_ws / "data" / "full_dose.npy")[ring].std())

    # Contrast is measured against the KNOWN inserted amplitude, using the
    # lesion's core rather than its peak.
    #
    # Not the peak, and not against the reference image: the full-dose scan
    # carries ~100 HU of noise, so the peak inside a 150 HU lesion is inflated
    # by a noise spike of several hundred HU. Scoring a restoration against
    # that peak punishes it for removing exactly the noise it was asked to
    # remove — a correct denoiser scored 0.37 by that measure. The core mean is
    # robust to noise and still collapses when a small object is blurred, which
    # is the failure this metric exists to catch.
    amp, r_les = np.load(seed_ws / "data" / "lesion_amplitude.npy")
    core = d2 <= max(1.0, (r_les * 0.6) ** 2)
    contrast = float(rec[core].mean() - rec[ring].mean())
    truth_contrast = float(amp)
    noise = float(rec[ring].std())
    return {"psnr": _psnr(rec, truth),
            "rmse_hu": float(np.sqrt(np.mean((rec - truth) ** 2))),
            "psnr_before": _psnr(low, truth),
            "noise_hu": noise,
            "noise_before_hu": float(low[ring].std()),
            "lesion_cnr": abs(contrast) / max(noise, 1e-9),
            "lesion_contrast_retained": abs(contrast) / max(abs(truth_contrast), 1e-9)}


def _judge_ldct(m: Dict[str, float]) -> Verdict:
    reasons, ok = [], True
    if m["psnr"] <= m["psnr_before"]:
        ok = False
        reasons.append("PSNR %.4g dB, against %.4g for the untouched low-dose "
                       "scan — the restoration made it worse"
                       % (m["psnr"], m["psnr_before"]))
    if m["lesion_cnr"] < 3.0:
        ok = False
        reasons.append(
            "lesion CNR %.3g, below the Rose criterion of 3 for reliable "
            "detection. A fidelity gain with the lesion smoothed away is a "
            "FAILURE, not a mixed result — the scan was ordered to find that "
            "lesion." % m["lesion_cnr"])
    # Half the inserted contrast. Demanding all of it fails every denoiser,
    # since any smoothing reduces a small object's amplitude somewhat; the
    # clinical question is whether the lesion stays detectable, which the CNR
    # check above answers.
    if m["lesion_contrast_retained"] < 0.5:
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
    goal="restore a real low-dose CT scan without losing the low-contrast lesion",
    package="ldct",
    deliverables=("results/reconstruction.npy",),
    answer_key=("data/full_dose.npy", "data/lesion_mask.npy",
                "data/lesion_amplitude.npy"),
    score=_score_ldct, judge=_judge_ldct, corpus="ldct",
    objective="lesion_cnr", objective_higher_is_better=True,
    # PSNR is the guardrail, not the target. Optimising PSNR is precisely how
    # the lesion gets smoothed away, and this benchmark exists to catch that.
    guardrails=("psnr", "lesion_contrast_retained"),
    parameters=(
        Parameter("sigma_s", 1.0, 6.0, 3.0, means="spatial extent of the filter"),
        Parameter("sigma_r_scale", 0.3, 2.0, 0.3,
                  means="range width as a multiple of the measured noise"),
        Parameter("iters", 1, 6, 3, integer=True, means="filter passes"),
        # ADOPTED 2026-08-05, owner-signed. The agent's night loop proposed
        # radius 4 with sigma_r_scale 0.3 and it survived held-out validation:
        # +3.91 lesion CNR over four distinct patients, p = 0.0088, with no
        # guardrail breach — PSNR and retained contrast both held. Proposed by
        # the agent, measured on seeds it was not selected on, signed by the
        # owner. The agent did not adopt it.
        Parameter("radius", 2, 5, 4, integer=True, means="neighbourhood radius"),
    ),
    criteria=("PSNR above the untouched low-dose scan, against the paired full-dose scan",
              "lesion CNR ≥ 3 — the Rose criterion, reported beside fidelity, always",
              "at least half the inserted contrast survives restoration",
              "an edge-preserving prior clears these; a PSNR-maximising blur "
              "does not, which is the whole point of scoring both"),
)


# -------------------------------------------------------- medical physics

def _score_medphys(seed_ws: Path, run_ws: Path) -> Dict[str, float]:
    """Real DVH statistics, per structure, over the whole planned volume.

    The clinical dose is loaded here — outside the sandbox — purely to report
    how the candidate compares with what the patient actually received. It is
    context for a physicist, never a target the planner could optimise toward."""
    import json as _json
    proto = _json.loads((seed_ws / "data" / "protocol.json").read_text())
    dose = np.load(run_ws / "results" / "dose.npy")
    clinical_full = np.load(seed_ws / "data" / "clinical_dose.npy")
    if dose.ndim == 3:
        # Volumetric: every structure is scored on all of its voxels. The 2D
        # path below survives only so an older artifact still reads — a planner
        # that returns a slice is reporting a property of one plane.
        take = lambda a: a
        clinical = clinical_full
    else:
        k = int(np.load(run_ws / "results" / "slice_index.npy")[0])
        take = lambda a: a[:, :, k]
        clinical = clinical_full[:, :, k]

    out: Dict[str, float] = {}
    for name, rule in proto.items():
        f = seed_ws / "data" / ("%s.npy" % name)
        if not f.exists():
            continue
        m = take(np.load(f))
        if not m.any():
            continue
        d = dose[m]
        if "D99_min" in rule:
            out["%s_D99" % name] = float(np.percentile(d, 1))
            out["%s_D99_min" % name] = float(rule["D99_min"])
        if "Dmax" in rule:
            out["%s_Dmax" % name] = float(d.max())
            out["%s_Dmax_limit" % name] = float(rule["Dmax"])
        if "Dmean" in rule:
            out["%s_Dmean" % name] = float(d.mean())
            out["%s_Dmean_limit" % name] = float(rule["Dmean"])
    out["clinical_PTV70_D99"] = float(np.percentile(
        clinical[take(np.load(seed_ws / "data" / "PTV70.npy"))], 1))
    out["hot_spot"] = float(dose.max())
    out["hot_spot_limit"] = float(proto["PTV70"]["prescription"] * 1.15)
    return out


def _judge_medphys(m: Dict[str, float]) -> Verdict:
    """Every constraint, one at a time, with the max as the headline.

    A mean would hide the tail, and in this field the tail is the clinical
    event. An aggregate score across structures would let a good parotid pay
    for a cord overdose, which is not a trade anyone is allowed to make."""
    checks = []
    for key in sorted(m):
        if key.endswith("_D99"):
            n = key[:-4]
            lim = m.get("%s_D99_min" % n)
            if lim is not None:
                checks.append(("%s D99" % n, m[key] >= lim,
                               "%.4g vs >= %.4g Gy" % (m[key], lim)))
        elif key.endswith("_Dmax") and not key.startswith("clinical"):
            n = key[:-5]
            lim = m.get("%s_Dmax_limit" % n)
            if lim is not None:
                checks.append(("%s Dmax" % n, m[key] <= lim,
                               "%.4g vs <= %.4g Gy" % (m[key], lim)))
        elif key.endswith("_Dmean"):
            n = key[:-6]
            lim = m.get("%s_Dmean_limit" % n)
            if lim is not None:
                checks.append(("%s Dmean" % n, m[key] <= lim,
                               "%.4g vs <= %.4g Gy" % (m[key], lim)))
    checks.append(("hot spot", m["hot_spot"] <= m["hot_spot_limit"],
                   "%.4g vs <= %.4g Gy" % (m["hot_spot"], m["hot_spot_limit"])))
    reasons = ["%s %s — %s" % (n, "met" if ok else "VIOLATED", d)
               for n, ok, d in checks]
    reasons.append("the delivered clinical plan reached PTV70 D99 = %.4g Gy on "
                   "this slice, for comparison only" % m.get("clinical_PTV70_D99", float("nan")))
    reasons.append("this is a plan CANDIDATE; a qualified medical physicist "
                   "signs anything that reaches a patient")
    return Verdict(all(ok for _, ok, _ in checks), tuple(reasons), m)


MEDPHYS = DomainBenchmark(
    agent="medical-physics",
    goal="produce a plan candidate meeting every protocol constraint",
    package="medphys",
    deliverables=("results/dose.npy", "results/plan_candidate.json"),
    # The clinical dose is what the patient actually received. A planner that
    # could read it would copy it, so it stays outside the sandbox.
    answer_key=("data/clinical_dose.npy",),
    score=_score_medphys, judge=_judge_medphys, corpus="open-kbp",
    objective="PTV70_D99", objective_higher_is_better=True,
    # Coverage is the target; the organ and the hot spot are what must not be
    # bought with it. An optimiser that raises D99 by irradiating the cord has
    # not planned, it has traded.
    guardrails=("SpinalCord_Dmax", "hot_spot"),
    guardrail_lower_is_better=("SpinalCord_Dmax", "hot_spot"),
    parameters=(
        # Default 20, not the 8.0 first guessed: at 8.0 the plan lands on
        # PTV70 D99 = 66.4991 against a 66.5 floor, short by 0.0009 Gy. Chosen
        # by sweeping this parameter against the protocol on one patient and
        # then checked across all eight, where it meets every constraint on
        # five. It is a starting point, not a solution — the three it misses
        # are why objective weights are tuned per patient in practice, and why
        # the night loop searches them.
        Parameter("under_weight", 1.0, 60.0, 20.0,
                  means="how much worse underdosing the tumour is than overdosing it"),
        Parameter("oar_weight", 1.0, 20.0, 6.0, means="organ-at-risk penalty"),
        Parameter("hot_weight", 0.5, 12.0, 3.0, means="hot-spot penalty"),
        Parameter("step", 0.1, 1.5, 0.6, means="projected-gradient step"),
        Parameter("iters", 200, 1500, 900, integer=True, means="iterations"),
        Parameter("cold_weight", 1.0, 200.0, 25.0,
                  means="penalty on target voxels BELOW the D99 floor. The "
                        "criterion is a dose-volume one, and a mean of squared "
                        "residuals barely sees the coldest percent — which is "
                        "the percent the verdict turns on"),
        # Default 2, not 8. Per-patient tuning makes ONE plan better and made the
        # night impossible: each candidate evaluation runs a full optimisation
        # per round, the loop already sweeps ~19 candidates x 6 seeds, and
        # medical-physics timed out at 30 minutes without completing a single
        # round. An agent that cannot finish a night produces nothing at all,
        # which is worse than a slightly weaker single plan. The ceiling stays
        # at 12 so the search can buy more rounds where they are worth it —
        # that is what the parameter is for.
        Parameter("tuning_rounds", 1, 12, 2, integer=True,
                  means="how many times the planner may read its own DVH "
                        "against the protocol and re-balance. 1 is the old "
                        "behaviour: one global weight set for every patient"),
    ),
    criteria=("each PTV reaches D99 ≥ 95% of its prescription",
              "brainstem ≤ 54 Gy, cord ≤ 45 Gy, parotid mean ≤ 26 Gy, mandible ≤ 70 Gy",
              "no hot spot above 115% of the primary prescription",
              "output is a candidate; a physicist signs"),
)


# ------------------------------------------------------------- pill camera

def _score_capsule(seed_ws: Path, run_ws: Path) -> Dict[str, float]:
    y = np.load(seed_ws / "data" / "labels.npy")
    vid = np.load(run_ws / "data" / "video_id.npy")
    is_test = np.load(run_ws / "data" / "is_test.npy")
    s = np.load(run_ws / "results" / "scores.npy")
    base = np.load(run_ws / "results" / "baseline_scores.npy")

    # Verified, not asserted: no video may appear on both sides. Consecutive
    # capsule frames are near-duplicates, so a leak here inflates everything.
    crossed = len(set(vid[is_test]) & set(vid[~is_test]))
    return {"auc": _auc(s[is_test], y[is_test]),
            "baseline_auc": _auc(base[is_test], y[is_test]),
            "auc_train_side": _auc(s[~is_test], y[~is_test]),
            "patients_crossing_the_split": float(crossed),
            "test_patients": float(len(set(vid[is_test]))),
            "train_patients": float(len(set(vid[~is_test]))),
            "positives_in_test": float(y[is_test].sum())}


def _judge_capsule(m: Dict[str, float]) -> Verdict:
    reasons, ok = [], True
    if m["patients_crossing_the_split"] > 0:
        ok = False
        reasons.append("%d patient(s) on both sides of the split — consecutive "
                       "frames are near-duplicates and this inflates everything"
                       % int(m["patients_crossing_the_split"]))
    else:
        reasons.append("patient-disjoint split verified in code, not asserted")
    # Patients, not frames. A test side with one or two patients measures
    # those patients, and this dataset makes that easy to walk into: the
    # blood class alone spans two videos.
    if m["test_patients"] < 3:
        ok = False
        reasons.append("only %d patients on the test side — that is not a "
                       "held-out evaluation, whatever the frame count says"
                       % int(m["test_patients"]))
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
    score=_score_capsule, judge=_judge_capsule, corpus="kvasir-capsule",
    objective="auc", objective_higher_is_better=True,
    guardrails=("baseline_auc",),
    parameters=(
        # ADOPTED 2026-08-05, owner-signed, from 95.0.
        #
        # Measurement: +0.029 AUC across six held-out seeds, paired, corrected
        # p 0.044 — found by the night loop, which then refused it for having
        # no mechanism.
        #
        # Mechanism, supplied afterwards and tested rather than asserted: a
        # lesion covers a small share of a capsule frame and the prior map is
        # elevated only over it, so a quantile summary works better the more it
        # isolates the lesion's own pixels instead of diluting them with normal
        # mucosa. On a 32x32 thumbnail, q=99.5 is the ~5th brightest pixel.
        #
        # The account predicts its own limit — isolation must stop helping once
        # the summary is a single noisy pixel — and the prediction holds:
        # effect size d runs 0.833 (q=99) -> 0.863 (99.5) -> 0.219 (99.8) ->
        # 0.058 (99.9), and the pure maximum is no better than noise. That
        # collapse is why this is a mechanism and not a story fitted to a win.
        #
        # Note the search found the optimum AT its upper bound, which normally
        # means the bound is wrong. Here the sweep above shows the bound is
        # right by coincidence; the space is left as it is because widening it
        # would admit values the data says are worse.
        Parameter("percentile", 50.0, 99.5, 99.5,
                  means="quantile of the per-pixel prior map that summarises a frame"),
    ),
    criteria=("the split is patient-disjoint, checked programmatically",
              "at least three patients on the test side",
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
    known = np.load(run_ws / "data" / "known_active.npy")
    s = np.load(run_ws / "results" / "scores.npy")

    # Enrichment is measured only on molecules NOT handed to the solver.
    # Scoring the query set would be scoring the answer back to itself.
    unseen = known == 0
    held = np.unique(tid)[-2:]                    # two whole targets held out
    m_held = np.isin(tid, held) & unseen
    m_all = unseen

    # DUD-E matches decoys to actives on bulk properties. It is known not to
    # match them perfectly, so the residual bias is measured and reported
    # rather than assumed away: if actives and decoys separate on molecular
    # weight alone, enrichment is partly a weight detector.
    bulk_gap = float(abs(D[y == 1][:, 0].mean() - D[y == 0][:, 0].mean())
                     / max(D[:, 0].std(), 1e-9))
    # The property baseline: what molecular weight alone achieves on this
    # library. DUD-E's decoys are property-matched but not perfectly, and the
    # residual bias is large enough that ranking by weight enriches — a
    # documented result, and the reason a screening claim has to be measured
    # against this rather than against random.
    ef_prop = _ef(D[m_all][:, 0], y[m_all])
    frac = float(y[m_all].mean())
    return {"active_fraction": frac,
            "ef_property_baseline": ef_prop,
            "ef_ceiling": (1.0 / frac) if frac > 0 else float("inf"),
            "ef_at_1pct": _ef(s[m_all], y[m_all]),
            "ef_at_1pct_heldout_targets": _ef(s[m_held], y[m_held]),
            "auc_unseen": _auc(s[m_all], y[m_all]),
            "auc_heldout_targets": _auc(s[m_held], y[m_held]),
            "decoy_bulk_bias_sd": bulk_gap,
            "heldout_targets": float(len(held)),
            "actives_scored": float(y[m_all].sum())}


def _judge_screening(m: Dict[str, float]) -> Verdict:
    reasons, ok = [], True
    # Calibrated to DUD-E's actual matching, which is imperfect and documented
    # as such. The number is always reported so a reader can weigh it — an
    # enrichment on a badly matched set is partly a property detector, and
    # hiding the figure would be the way to never have to say so.
    reasons.append("decoy property match: %.2g SD apart on molecular weight"
                   % m["decoy_bulk_bias_sd"])
    if m["decoy_bulk_bias_sd"] > 0.75:
        ok = False
        reasons.append("that is too far — this enrichment is measuring bulk "
                       "properties rather than binding")
    # A library dense in actives makes EF@1% saturate, and then every method
    # scores the ceiling — including ranking by molecular weight, which is how
    # this was caught. A saturated metric is not a lenient one, it is a broken
    # one, so the benchmark refuses rather than reporting the ceiling as a win.
    if m["active_fraction"] > 0.05:
        ok = False
        reasons.append("the library is %.1f%% active — EF@1%% saturates at %.3g "
                       "and stops discriminating between methods"
                       % (100 * m["active_fraction"], m["ef_ceiling"]))
    # The check above catches saturation caused by a dense *library*. It does
    # not catch saturation caused by a good *method*, and that is the case this
    # benchmark actually hit: at a healthy 1.5% active the top percentile came
    # out entirely active, EF@1% sat at 66.789 against a ceiling of 66.789, and
    # seven methods whose AUC differed by 0.014 all scored it identically to
    # four significant figures.
    #
    # A metric with no headroom is not a lenient grader, it is a broken one, and
    # reporting the ceiling as a triumph is the thing this judge exists to
    # refuse. So the refusal is on the *observed* value against the ceiling,
    # whatever put it there.
    #
    # This is a statement about the BENCHMARK, not about the method. A screen
    # that fills the first percentile with actives is doing well; the point is
    # that EF@1% can no longer say how well, or that anything else is better.
    headroom = 1.0 - (m["ef_at_1pct"] / max(m["ef_ceiling"], 1e-9))
    if headroom < 0.02:
        ok = False
        reasons.append("EF@1%% %.4g against a ceiling of %.4g — %.2f%% headroom. "
                       "The top percentile is essentially all actives, so this "
                       "number cannot rank one method above another and must "
                       "not be read as a score. It is a statement about the "
                       "benchmark, not the method. auc_unseen (%.4g) still "
                       "discriminates and is what the search optimises"
                       % (m["ef_at_1pct"], m["ef_ceiling"], 100 * headroom,
                          m.get("auc_unseen", float("nan"))))
    if m["ef_at_1pct"] < 2.0:
        ok = False
        reasons.append("EF@1%% %.3g — no useful enrichment" % m["ef_at_1pct"])
    # Beating random is not the bar. Beating what bulk properties alone deliver
    # on this exact library is, because anything less is a property detector
    # wearing a screening result's clothes.
    lift = m["ef_at_1pct"] / max(m["ef_property_baseline"], 1e-9)
    if lift < 1.5:
        ok = False
        reasons.append("EF@1%% %.3g against a molecular-weight baseline of %.3g "
                       "(%.2gx) — this is not screening, it is that baseline"
                       % (m["ef_at_1pct"], m["ef_property_baseline"], lift))
    else:
        reasons.append("EF@1%% %.3g vs %.3g for molecular weight alone (%.2gx "
                       "over the property baseline)"
                       % (m["ef_at_1pct"], m["ef_property_baseline"], lift))
    if m["actives_scored"] < 20:
        ok = False
        reasons.append("too few scored actives to say anything")
    reasons.append("EF@1%% %.3g overall, %.3g on targets held out entirely"
                   % (m["ef_at_1pct"], m["ef_at_1pct_heldout_targets"]))
    reasons.append("a score ranks; it does not measure. Nothing here has been "
                   "made or assayed, and no compound is a candidate")
    return Verdict(ok, tuple(reasons), m)


SCREENING = DomainBenchmark(
    agent="drug-design",
    goal="rank a library against held-out targets and report honest enrichment",
    package="screening",
    deliverables=("results/scores.npy",),
    answer_key=("data/labels.npy",),
    score=_score_screening, judge=_judge_screening, corpus="dude",
    # EF@1% is the field's metric — a screening campaign tests the top of the
    # list and nothing else — and it is the objective again now that it has room
    # to move. It briefly was not: the query set used to be drawn at random from
    # each target's actives, DUD-E actives are largely analogue series, and so
    # the ten molecules handed over were usually close relatives of the ones
    # being scored. EF@1% pinned at 100% of its ceiling and seven methods scored
    # it identically. AUC was the objective while that was true.
    #
    # The fix was to the SPLIT, not to the metric: the query set is drawn from
    # whole clusters and the rest of those clusters is withheld, so what is left
    # to find is a series the solver was never shown. The task got harder — AUC
    # fell from 0.94 to 0.82-0.88 — and EF@1% came back to 51-77% of ceiling,
    # which is a metric that ranks methods again.
    objective="ef_at_1pct", objective_higher_is_better=True,
    # AUC over all unseen molecules guards the other direction: EF@1% is a
    # top-of-list number, and the cheapest way to raise it is to sharpen the
    # first percentile while making the rest of the ranking worse — no use to
    # anyone who screens deeper than 1%. The held-out targets guard the failure
    # that ends screening papers: gaining overall by suiting the well-represented
    # targets and losing the ones the method was meant to generalise to.
    guardrails=("auc_unseen", "ef_at_1pct_heldout_targets"),
    parameters=(
        Parameter("top_k", 1, 15, 1, integer=True,
                  means="group fusion: average the top-k similarities to known "
                        "actives rather than taking the single nearest. 1 is "
                        "1-NN, which is what this solver has always done"),
        Parameter("tversky_alpha", 0.2, 2.0, 1.0,
                  means="weight on features the candidate has and the query "
                        "lacks; lower tolerates analogues larger than the query"),
        Parameter("tversky_beta", 0.2, 2.0, 1.0,
                  means="weight on features the query has and the candidate "
                        "lacks. alpha = beta = 1 is Tanimoto exactly"),
        Parameter("idf_weight", 0.0, 2.0, 0.0,
                  means="exponent on inverse-document-frequency bit weights; "
                        "0 weighs every bit alike, as unweighted Tanimoto does"),
    ),
    criteria=("EF@1% ≥ 2 on molecules not handed to the solver",
              "and ≥ 1.5x what molecular weight alone achieves on the same library",
              "and with at least 2% headroom below its own ceiling — a pinned "
              "EF@1% cannot rank methods and is refused whatever pinned it",
              "the decoy property match is measured and reported",
              "no activity claimed without an assay"),
)


# ------------------------------------------------------------------ cancer

def _score_onco(seed_ws: Path, run_ws: Path) -> Dict[str, float]:
    d = lambda n: np.load(seed_ws / "data" / (n + ".npy"))
    rd = np.load(run_ws / "results" / "risk_dev.npy")
    re_ = np.load(run_ws / "results" / "risk_ext.npy")
    rx = np.load(run_ws / "results" / "risk_xh.npy")
    c_int = _c_index(rd, d("dev_time"), d("dev_event"))
    c_ext = _c_index(re_, d("ext_time"), d("ext_event"))
    # Calibration by Kaplan-Meier at a fixed horizon, per risk tertile.
    #
    # NOT the median observed time, which was the first version of this and is
    # wrong: in a real cohort most cases are censored — alive at last contact —
    # so "observed time" measures how long someone has been in the study, not
    # how long they survived. A group followed for longer looks sicker. KM uses
    # the censored cases for as long as they were observed and drops them after,
    # which is the whole reason it exists.
    t, e = d("ext_time"), d("ext_event")
    q = np.quantile(re_, [1 / 3, 2 / 3])
    masks = [re_ <= q[0], (re_ > q[0]) & (re_ <= q[1]), re_ > q[1]]
    horizon = float(np.quantile(t, 0.5))
    surv = [_km_at(t[m], e[m], horizon) for m in masks]
    monotone = float(surv[0] >= surv[1] >= surv[2])
    return {"c_index_internal": c_int, "c_index_external": c_ext,
            # A different DISEASE, not a different hospital. Reported beside the
            # external number and never confused with it: the model transports
            # across institutions, and squamous cell is a cohort where these
            # covariates carry little signal in either direction.
            "c_index_cross_histology": _c_index(rx, d("xh_time"), d("xh_event")),
            "external_drop": c_int - c_ext,
            "calibration_monotone": monotone,
            "km_horizon_days": horizon,
            "survival_low_risk": surv[0],
            "survival_mid_risk": surv[1],
            "survival_high_risk": surv[2]}


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
    # Reported, never graded. A different disease is a different question, and
    # grading on it once turned "squamous cell is hard to prognose" into "the
    # model does not transport" — which the numbers did not support.
    reasons.append("on the other histology entirely: %.4g. That cohort scores "
                   "low whichever cohort the model was fitted on, and stage "
                   "alone scores 0.658 in adenocarcinoma against 0.565 there, "
                   "so it is the cohort that is hard and not the transport "
                   "that failed" % m["c_index_cross_histology"])
    reasons.append("for a clinician. Not a diagnosis, not advice, no "
                   "patient-level claim")
    return Verdict(ok, tuple(reasons), m)


ONCO = DomainBenchmark(
    agent="cancer",
    goal="fit a risk score and validate it on an external cohort",
    package="onco",
    deliverables=("results/risk_dev.npy", "results/risk_ext.npy"),
    answer_key=(),      # outcomes are the data; what is tested is transport
    score=_score_onco, judge=_judge_onco, corpus="tcga-survival",
    objective="c_index_external", objective_higher_is_better=True,
    # Internal discrimination is the guardrail: a "transporting" model that
    # got there by throwing away its fit is not the thing anyone wants.
    guardrails=("c_index_internal",),
    parameters=(
        Parameter("ridge", 0.0, 400.0, 10.0,
                  means="shrinkage toward zero; more should transport better, "
                        "and on this cohort pair it does not"),
        Parameter("lr", 0.1, 1.0, 0.5, means="gradient step"),
        Parameter("iters", 200, 1200, 800, integer=True, means="fit iterations"),
    ),
    criteria=("external C-index ≥ 0.58 on a cohort the model never saw",
              "calibration reported with discrimination",
              "no patient-level claim"),
)



# ------------------------------------------------------------ reverse aging

def _score_methylage(seed_ws: Path, run_ws: Path) -> Dict[str, float]:
    """Age error, and how much of it survives removing the methylome's bulk
    structure. Reported together or the first number cannot be read."""
    truth = np.load(seed_ws / "data" / "ext_age.npy").astype(float)
    dev_age = np.load(run_ws / "data" / "dev_age.npy").astype(float)
    pred = np.load(run_ws / "results" / "age_pred.npy").astype(float)
    pred_dev = np.load(run_ws / "results" / "age_pred_dev.npy").astype(float)
    pred_np = np.load(run_ws / "results" / "age_pred_no_pcs.npy").astype(float)

    mae = float(np.median(np.abs(pred - truth)))
    mae_dev = float(np.median(np.abs(pred_dev - dev_age)))
    mae_np = float(np.median(np.abs(pred_np - truth)))
    # The bar that makes it a clock rather than a number: predicting the
    # training cohort's mean age for everybody. Any method that cannot beat
    # this has learnt nothing about the individual.
    mae_const = float(np.median(np.abs(dev_age.mean() - truth)))

    r = float(np.corrcoef(pred, truth)[0, 1]) if len(truth) > 2 else float("nan")
    return {"mae_years": mae,
            "mae_years_internal": mae_dev,
            "mae_years_pcs_removed": mae_np,
            "mae_years_constant_baseline": mae_const,
            # How much of the accuracy rode on the leading components of the
            # methylome. NOT called cell composition: those components are
            # dominated by it in whole blood, but this measures the components,
            # and naming it for what it is presumed to contain would be a claim
            # this benchmark cannot check.
            "bulk_structure_share": float(
                (mae_np - mae) / max(mae_const - mae, 1e-9)),
            "age_correlation": r,
            "n_external": float(len(truth)),
            "external_age_span": float(truth.max() - truth.min())}


def _judge_methylage(m: Dict[str, float]) -> Verdict:
    reasons, ok = [], True
    if m["n_external"] < 50:
        return Verdict(False, ("only %d held-out samples — too few to read"
                               % m["n_external"],), m)
    # A clock has to beat predicting the mean. This is the whole bar for
    # "is it a clock", and it is low on purpose: what this benchmark is for is
    # the two checks after it.
    if m["mae_years"] >= 0.75 * m["mae_years_constant_baseline"]:
        ok = False
        reasons.append("median error %.2f years against %.2f for predicting the "
                       "training cohort's mean age — that is not a clock, it is "
                       "an intercept"
                       % (m["mae_years"], m["mae_years_constant_baseline"]))
    # The field's characteristic failure. Whole-blood methylation's leading
    # components are dominated by cell-type proportions, which themselves shift
    # with age; a clock riding on them is a blood-count detector with a birthday
    # attached, and it will not transfer to a tissue whose composition differs.
    if m["bulk_structure_share"] > 0.75:
        ok = False
        reasons.append("%.0f%% of this clock's accuracy disappears when the "
                       "leading components of the methylome are projected out "
                       "(%.2f years -> %.2f). Those components are dominated by "
                       "cell composition in whole blood, so most of what this is "
                       "measuring is what the blood is made of, not how old the "
                       "person is"
                       % (100 * m["bulk_structure_share"], m["mae_years"],
                          m["mae_years_pcs_removed"]))
    else:
        reasons.append("with the methylome's leading components projected out, "
                       "error goes %.2f -> %.2f years (%.0f%% of the gain lost), "
                       "so the clock is not merely reading cell composition"
                       % (m["mae_years"], m["mae_years_pcs_removed"],
                          100 * m["bulk_structure_share"]))
    reasons.append("median absolute error %.2f years on %d samples from "
                   "institutions that contributed nothing to the fit; internal "
                   "%.2f" % (m["mae_years"], m["n_external"],
                             m["mae_years_internal"]))
    # Said on every run, pass or fail. It is the rule this agent exists to hold.
    reasons.append("a clock is not a lifespan. This predicts CHRONOLOGICAL age, "
                   "which is known anyway; nothing here measures how fast anyone "
                   "is ageing, and no outcome has been looked at. GSE40279 "
                   "carries no survival or function endpoint, so `outcome_link` "
                   "stays unmeasured rather than being approximated")
    return Verdict(ok, tuple(reasons), m)


METHYLAGE = DomainBenchmark(
    agent="reverse-aging",
    goal="fit an epigenetic clock and validate it on institutions it never saw",
    package="methylage",
    deliverables=("results/age_pred.npy", "results/age_pred_no_pcs.npy"),
    answer_key=("data/ext_age.npy",),
    score=_score_methylage, judge=_judge_methylage, corpus="methylation-age",
    objective="mae_years", objective_higher_is_better=False,
    # Not the error alone. A clock can be improved by leaning harder on bulk
    # structure, which is the failure this benchmark exists to see, so the share
    # is a guardrail and lower is better for it too.
    guardrails=("bulk_structure_share", "mae_years_internal"),
    guardrail_lower_is_better=("bulk_structure_share", "mae_years_internal"),
    parameters=(
        # ADOPTED 2026-08-05, owner-signed. Proposed by the agent's night loop
        # and validated on six genuinely different institutional splits:
        # -2.08 years median error, p = 0.014, no guardrail breach. The first
        # night proposed the same value with p = 0, which was zero-spread
        # arithmetic from a seed that did nothing; that result was refused and
        # this one earned.
        #
        # The winner sat at the FLOOR, so the floor was opened 1.0 -> 0.0001 and
        # the space measured, 6 seeds per point. The optimum IS outside the old
        # range, and it is worth almost nothing:
        #
        #   ridge   0.0001   0.01    0.1     1.0     10      100
        #   MAE      9.649   9.650   9.654   9.730   10.272  12.998
        #   bulk     0.456   0.455   0.452   0.436   0.414   0.554
        #
        # MAE is flat below ~0.01: dropping from the adopted 1.0 to 0.0001 buys
        # 0.081 years — about a month — and moves bulk_structure_share the WRONG
        # way, 0.436 -> 0.456. That is the trade this guardrail exists to catch:
        # a weaker penalty lets the clock lean harder on cell composition, which
        # is the failure mode, so the search would be buying a month of apparent
        # accuracy with the thing we say we care about.
        #
        # So the range is widened and the adopted value STAYS 1.0. The floor was
        # hiding a flat region, not a better clock.
        #
        # Above 1.0 the error rises monotonically and 100 already fails 4 of 6
        # seeds, so the 5000 ceiling is mostly dead search space. Left in place:
        # 4 points on 6 seeds is thinner evidence than the floor case, and
        # narrowing a declared range on thin evidence is how a space gets shaped
        # to flatter a result.
        # log=True because this range is 7.7 decades and nothing else in any
        # benchmark is above ~1. A linear step here is ~2500 wide: the first
        # night after the floor was opened proposed exactly one reachable
        # candidate below the incumbent (clamped to 0.0001, delta +0.0138) and
        # never saw anything in between. The space is unchanged; only the walk.
        Parameter("ridge", 0.0001, 5000.0, 1.0, log=True,
                  means="shrinkage; with 20k probes and a few hundred samples "
                        "this is what stops the clock memorising the fit"),
        Parameter("n_pcs_removed", 1, 20, 5, integer=True,
                  means="how many leading components are projected out for the "
                        "second fit — the depth at which bulk structure is "
                        "considered removed"),
    ),
    criteria=("median error below 75% of predicting the training mean age",
              "no more than 75% of the accuracy lost when the methylome's "
              "leading components are projected out",
              "validated on institutions that contributed nothing to the fit",
              "chronological age only — no claim about rate of ageing, and no "
              "outcome examined"),
)

# The registry lives at the end of the file so that adding a benchmark below an
# existing one cannot silently leave it unregistered — which is exactly what
# happened when METHYLAGE was appended after this line sat in the middle.
BENCHMARKS = {b.agent: b for b in
              (LDCT, MEDPHYS, CAPSULE, SCREENING, ONCO, METHYLAGE)}


def benchmark_for(agent: str) -> DomainBenchmark:
    if agent not in BENCHMARKS:
        raise KeyError("no domain runner for %r — have: %s"
                       % (agent, ", ".join(sorted(BENCHMARKS))))
    return BENCHMARKS[agent]
