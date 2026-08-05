"""The five domain runners: they compute, and they refuse.

A test that only checks the happy path proves the benchmark runs, not that it is
worth running. So each domain here is tested twice — once with the intended
method, and once with a method that games the field's usual metric. If the
gaming version also passes, the benchmark cannot tell a good method from a bad
one and is not evidence of anything.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from ai4science.harness.agents.research_agents.runners import (
    BENCHMARKS, CAPSULE, LDCT, MEDPHYS, ONCO, SCREENING, benchmark_for,
    run_domain_task, seed_workspace,
)


class Sim:
    """The control plane, modelled: a run workspace, staged inputs, and a
    subprocess for the sandbox. Same shape as tests/imaging's HostSimClient."""

    def __init__(self, ws: Path, override: str = ""):
        self.ws = Path(ws)
        self.ws.mkdir(parents=True, exist_ok=True)
        self.override = override
        self.executed = []

    def open_run(self, goal, cp, limits, interaction_profile="I1", agent_id=None):
        return {"run_id": "t", "capability_profile": cp,
                "workspace_path": str(self.ws)}

    def stage_input(self, run_id, rel, content):
        d = self.ws / rel
        d.parent.mkdir(parents=True, exist_ok=True)
        d.write_bytes(content)
        return {"ok": True}

    def sandbox_execute(self, run_id, cmd, **kw):
        if self.override:
            (self.ws / "code" / "alt.py").write_text(self.override)
            cmd = ["python3", "code/alt.py", "--workspace", "."]
        self.executed.append(cmd)
        p = subprocess.run([sys.executable] + cmd[1:], cwd=str(self.ws),
                           capture_output=True, text=True)
        return {"exit_code": p.returncode, "is_error": p.returncode != 0,
                "stdout": p.stdout, "stderr": p.stderr}


def _needs_corpus(bench):
    """Skip, do not fail, when the real data is not on this machine. A dataset
    someone has to accept terms for is not a broken build."""
    if not bench.real:
        return
    from ai4science.harness.agents.research_agents.runners import corpus
    c = corpus.ALL[bench.corpus]
    if not c.present():
        pytest.skip("%s not fetched on this machine (%s)" % (c.key, c.fetch))


def _run(bench, tmp_path, override="", seed=42):
    _needs_corpus(bench)
    return run_domain_task(bench, client=Sim(tmp_path / "run", override),
                           workspace=tmp_path / "seed", seed=seed)


# ------------------------------------------------------------------ all five

@pytest.mark.parametrize("name", sorted(BENCHMARKS))
def test_each_agent_computes_and_is_judged(name, tmp_path):
    """Computed and judged — not necessarily passed.

    On real data a correct benchmark may return FAIL, and asserting a pass here
    would make the suite demand a result rather than a measurement. `cancer` is
    exactly that case; see the test below."""
    out = _run(benchmark_for(name), tmp_path)
    assert out["status"] in ("delivered", "rejected"), out.get("why")
    assert out["metrics"], "a verdict with no metrics is an opinion"
    assert out["verdict"] is not None
    assert out["provenance"], "a result must say where its data came from"


@pytest.mark.parametrize("name", ["low-dose-ct"])
def test_the_intended_method_passes(name, tmp_path):
    out = _run(benchmark_for(name), tmp_path)
    assert out["verdict"].passed, out["verdict"].report()


def test_drug_design_is_refused_because_its_metric_is_pinned(tmp_path):
    """`drug-design` left the list above, and the reason is the benchmark, not
    the method.

    EF@1% comes out at 66.789 against a ceiling of 66.789 — the top percentile
    is entirely actives, so the number has no headroom left. Seven methods whose
    AUC differed by 0.014 scored it identically to four significant figures,
    which is what a metric that has stopped measuring looks like.

    The judge already refused saturation caused by a dense *library* (>5%
    active). This library is a healthy 1.5%; what pins the metric here is that
    the *method* is good enough to fill the first percentile. Same broken
    number, a cause the original guard did not look for — so the refusal is now
    on observed headroom, whatever produced it.

    This is the `cancer` situation: a correct benchmark returning FAIL.
    Asserting a pass would make the suite demand a result rather than a
    measurement."""
    out = _run(SCREENING, tmp_path)
    v, m = out["verdict"], out["metrics"]
    assert not v.passed, v.report()
    assert any("headroom" in r for r in v.reasons), v.report()
    assert m["ef_at_1pct"] == pytest.approx(m["ef_ceiling"], rel=1e-6)
    # And what is NOT wrong with it, so the refusal is not misread as "the
    # screen is bad": it clears the property baseline comfortably, and the
    # metric that survives is the one the search now optimises.
    assert m["ef_at_1pct"] / m["ef_property_baseline"] > 1.5
    assert 0.5 < m["auc_unseen"] < 1.0


def test_a_clinical_only_model_does_not_transport_across_histologies(tmp_path):
    """The finding that arrived with the real data, kept as a test.

    A Cox model on age, sex, stage and prior malignancy, fitted on TCGA-LUAD and
    validated on TCGA-LUSC, discriminates internally and does not transport. The
    judge refuses it, which is the correct answer and not a bug to tune away —
    it is also what the literature says happens to prognostic models that are
    never externally validated."""
    out = _run(ONCO, tmp_path)
    m = out["metrics"]
    assert m["c_index_internal"] > 0.6, "it does discriminate on its own cohort"
    assert m["c_index_external"] < 0.6, "and it does not transport"
    assert m["external_drop"] > 0.05
    assert not out["verdict"].passed
    assert any("did not transport" in r for r in out["verdict"].reasons)
    # Calibration is measured by Kaplan-Meier, so censoring does not fake it.
    assert m["calibration_monotone"] == 1.0


@pytest.mark.parametrize("name", sorted(BENCHMARKS))
def test_the_answer_key_never_reaches_the_sandbox(name, tmp_path):
    bench = benchmark_for(name)
    out = _run(bench, tmp_path)
    run_ws = Path(out["run_workspace"])
    for key in bench.answer_key:
        assert not (run_ws / key).exists(), "%s leaked %s" % (name, key)
        assert (tmp_path / "seed" / key).exists(), "the key should exist outside"
    assert set(out["withheld"]) == set(bench.answer_key)


def test_a_run_is_reproducible_from_its_seed(tmp_path):
    a = _run(SCREENING, tmp_path / "a")
    b = _run(SCREENING, tmp_path / "b")
    assert a["metrics"]["ef_at_1pct"] == b["metrics"]["ef_at_1pct"]


# ------------------------------------- low-dose CT: the smoothing failure

GAUSS = """
import argparse, os
import numpy as np
from scipy.ndimage import gaussian_filter
ap = argparse.ArgumentParser(); ap.add_argument("--workspace", default=".")
ap.add_argument("--sigma", type=float, default=1.0)
ws = ap.parse_args().workspace
low = np.load(os.path.join(ws, "data", "low_dose.npy"))
rec = gaussian_filter(low, SIGMA)
os.makedirs(os.path.join(ws, "results"), exist_ok=True)
np.save(os.path.join(ws, "results", "reconstruction.npy"), rec)
"""


def test_the_psnr_maximising_restoration_FAILS(tmp_path):
    """The refusal this agent exists for, on real paired clinical CT.

    Light smoothing wins on PSNR — the number the field reports — and leaves the
    low-contrast lesion below the Rose criterion for reliable detection. A
    fidelity gain with the finding gone is a failure, not a mixed result."""
    good = _run(LDCT, tmp_path / "good")
    light = _run(LDCT, tmp_path / "light", override=GAUSS.replace("SIGMA", "1.0"))

    assert light["metrics"]["psnr"] > good["metrics"]["psnr"], \
        "the light blur is supposed to win on PSNR; otherwise this proves nothing"
    assert good["verdict"].passed, good["verdict"].report()
    assert not light["verdict"].passed
    assert light["metrics"]["lesion_cnr"] < 3.0
    assert any("Rose criterion" in r for r in light["verdict"].reasons)


def test_over_smoothing_FAILS_the_other_way(tmp_path):
    """And the opposite error is caught too: heavy smoothing keeps the lesion
    visible against a very quiet background while erasing most of its contrast."""
    heavy = _run(LDCT, tmp_path / "heavy", override=GAUSS.replace("SIGMA", "6.0"))
    assert not heavy["verdict"].passed
    assert heavy["metrics"]["lesion_contrast_retained"] < 0.5


def test_the_paired_scans_are_the_same_anatomy(tmp_path):
    """Sorting zip entries does not order a DICOM series: the first version of
    the fetcher paired full[0] with low[2]. Slices are matched by
    ImagePositionPatient now, and this asserts the pairing rather than trusting
    it — once smoothed, the two scans must be the same picture."""
    from scipy.ndimage import gaussian_filter
    _needs_corpus(LDCT)
    seed_workspace(LDCT, tmp_path / "s", seed=42)
    import numpy as np
    full = np.load(tmp_path / "s" / "data" / "full_dose.npy")
    low = np.load(tmp_path / "s" / "data" / "low_dose.npy")
    corr = np.corrcoef(gaussian_filter(full, 3).ravel(),
                       gaussian_filter(low, 3).ravel())[0, 1]
    assert corr > 0.99, "smoothed correlation %.4f — these are different slices" % corr
    # And the low-dose scan really is noisier, or it is not a dose pair.
    hi = lambda a: float((a - gaussian_filter(a, 2)).std())
    assert hi(low) > 1.5 * hi(full)


# ------------------------------- medical physics: modulation is not optional

NAIVE_PLAN = """
import argparse, json, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from run_solver import beamlets, ANGLES
ap = argparse.ArgumentParser(); ap.add_argument("--workspace", default=".")
ws = ap.parse_args().workspace
proto = json.load(open(os.path.join(ws, "data", "protocol.json")))
ptv = np.load(os.path.join(ws, "data", "PTV70.npy"))
k = int(np.argmax(ptv.sum(axis=(0, 1))))
prim = ptv[:, :, k]
body = np.load(os.path.join(ws, "data", "possible.npy"))[:, :, k]
cy, cx = np.argwhere(prim).mean(axis=0)
A = np.stack([b for a in ANGLES for b in beamlets(prim.shape, a, cy, cx)])
dose = np.tensordot(np.ones(len(A)), A, axes=(0, 0)) * body
d = dose[prim]
dose = dose * (proto["PTV70"]["prescription"] / max(float(np.percentile(d, 1)), 1e-9))
os.makedirs(os.path.join(ws, "results"), exist_ok=True)
np.save(os.path.join(ws, "results", "dose.npy"), dose)
np.save(os.path.join(ws, "results", "slice_index.npy"), np.array([k]))
json.dump({"status": "candidate", "requires": "sign-off by a qualified medical physicist"},
          open(os.path.join(ws, "results", "plan_candidate.json"), "w"))
"""


def test_modulation_is_what_makes_the_plan_acceptable(tmp_path):
    """Two earlier versions of this test are worth remembering.

    The first counted protocol violations and concluded modulation won — hiding
    that my planner had MORE violations than an unmodulated plan, because it
    halved the cord dose and paid with a 190 Gy hot spot. The second asserted
    that neither plan passes and only that the benchmark could tell them apart.

    Both were true when written. Fixing the objective made them false: the
    modulated plan now meets every constraint and the unmodulated one does not,
    which is the plain statement the other two were circling."""
    good = _run(MEDPHYS, tmp_path / "good")
    naive = _run(MEDPHYS, tmp_path / "naive", override=NAIVE_PLAN)
    assert good["verdict"].passed, good["verdict"].report()
    assert not naive["verdict"].passed
    # And it is the cord that separates them — the constraint that shapes a
    # head-and-neck plan, and the one an unmodulated field cannot respect.
    assert good["metrics"]["SpinalCord_Dmax"] < naive["metrics"]["SpinalCord_Dmax"]
    assert any("SpinalCord" in r and "VIOLATED" in r for r in naive["verdict"].reasons)


def test_the_planner_meets_a_real_head_and_neck_protocol(tmp_path):
    """This test asserted the opposite yesterday, and was right to fail today.

    It recorded "a coplanar 2D planner cannot spare a cord that abuts the
    target" as a finding about the field. It was a finding about three bugs in
    my objective: it penalised target underdose only, so nothing pushed dose
    down and normalising D99 to the prescription dragged the slice up — target
    mean 101.9 Gy against a 70 Gy prescription. Two-sided and asymmetric, as
    clinical objectives are, it plans."""
    out = _run(MEDPHYS, tmp_path)
    m = out["metrics"]
    assert out["verdict"].passed, out["verdict"].report()
    assert m["PTV70_D99"] >= m["PTV70_D99_min"]
    assert m["SpinalCord_Dmax"] <= m["SpinalCord_Dmax_limit"]
    assert m["hot_spot"] <= m["hot_spot_limit"]
    # Uniformity is the thing the one-sided objective destroyed: D99 alone
    # cannot see an overdose, so check the top of the distribution too.
    assert m["hot_spot"] <= m["PTV70_D99"] * 1.2, \
        "a plan meeting D99 while cooking everything else is what this caught"


def test_coverage_bought_with_the_cord_is_refused(tmp_path):
    """One OpenKBP patient reaches full target coverage by putting 70 Gy into a
    cord limited to 45. The judge must refuse that plan — and this is the case
    that exposed the inverted guardrail, which would have *approved* it."""
    out = _run(MEDPHYS, tmp_path, seed=4)
    m = out["metrics"]
    assert m["PTV70_D99"] >= m["PTV70_D99_min"], "coverage is fine on this one"
    assert m["SpinalCord_Dmax"] > m["SpinalCord_Dmax_limit"], "and the cord is not"
    assert not out["verdict"].passed
    assert any("SpinalCord" in r and "VIOLATED" in r for r in out["verdict"].reasons)


# ------------------------------------ pill camera: the split, and the prior

def test_the_split_is_patient_disjoint_and_checked(tmp_path):
    out = _run(CAPSULE, tmp_path)
    assert out["metrics"]["patients_crossing_the_split"] == 0
    assert any("patient-disjoint" in r for r in out["verdict"].reasons)


def test_the_prior_beats_intensity_at_the_ADOPTED_setting(tmp_path):
    """This test previously asserted the opposite, and said so in its own body:
    "if the prior ever does beat intensity here, this test should be the thing
    that notices, not a paragraph someone rewrites." It noticed.

    The history matters more than the current number. At the hand-picked 95th
    percentile the analytic prior LOST to plain green intensity (0.598 against
    0.614) and the synthetic benchmark that claimed otherwise had been built to
    agree with it. The night loop found 99.5, the mechanism was tested rather
    than asserted — a lesion is a small bright region, so the summary must
    isolate it without collapsing to one noisy pixel — and at the adopted
    setting the prior wins, narrowly.

    Narrowly is the word. This is one split; the adoption rests on +0.029 AUC
    across six held-out seeds at corrected p 0.044, not on the margin here."""
    out = _run(CAPSULE, tmp_path)
    m = out["metrics"]
    assert m["auc"] > m["baseline_auc"], \
        "if this flips back, the adoption was premature and this is how you learn"
    assert m["auc"] - m["baseline_auc"] < 0.05, \
        "and if the margin ever gets large, something has changed that is worth " \
        "understanding rather than celebrating"
    assert out["verdict"].passed


def test_the_adopted_percentile_is_the_one_the_mechanism_predicts(tmp_path):
    """The mechanism predicts its own limit: isolation helps until the summary
    is a single noisy pixel. Going past the adopted value must get worse."""
    from ai4science.harness.agents.research_agents.runners import CAPSULE as C
    good = _run(C, tmp_path / "adopted")                      # default = 99.5
    assert C.defaults()["percentile"] == 99.5
    # The declared space stops at the adopted value on purpose: the sweep that
    # justified it shows the effect collapsing beyond, so a wider bound would
    # only admit values known to be worse.
    assert max(p.high for p in C.parameters if p.name == "percentile") == 99.5


def test_a_per_pixel_prior_must_not_be_averaged_over_the_frame(tmp_path):
    """A lesion covers a small part of a capsule frame. Summarising P_blood by
    the frame mean scored 0.496 — chance — because the mean washes out the
    strongest region, which is the only place the prior says anything. The
    solver takes a high percentile instead, and that alone moved it to 0.60."""
    out = _run(CAPSULE, tmp_path)
    assert out["metrics"]["auc"] > 0.55, "the percentile aggregation is doing work"


def test_one_seed_is_never_presented_as_a_result(tmp_path):
    out = _run(CAPSULE, tmp_path)
    assert any("one seed is one seed" in r for r in out["verdict"].reasons)


# --------------------------------- drug design: decoys, and held-out targets

BIASED_DECOYS = '''
import argparse, os
import numpy as np
ap = argparse.ArgumentParser(); ap.add_argument("--workspace", default=".")
ws = ap.parse_args().workspace
D = np.load(os.path.join(ws, "data", "descriptors.npy"))
# Rank by molecular weight alone — the classic artefact.
os.makedirs(os.path.join(ws, "results"), exist_ok=True)
np.save(os.path.join(ws, "results", "scores.npy"), D[:, 0])
'''


def test_ranking_by_molecular_weight_is_not_screening(tmp_path):
    """DUD-E's decoys are property-matched but not perfectly, and molecular
    weight alone enriches — a documented bias. So the bar is not "beats random",
    it is "beats what bulk properties achieve on this same library". Without
    that, a weight detector passes as a virtual screen."""
    good = _run(SCREENING, tmp_path / "good")
    weight = _run(SCREENING, tmp_path / "w", override=BIASED_DECOYS)
    assert not weight["verdict"].passed
    assert any("it is that baseline" in r for r in weight["verdict"].reasons)
    assert weight["metrics"]["auc_unseen"] < good["metrics"]["auc_unseen"]
    # The reference method is NOT asserted to pass overall — it is refused for
    # a pinned EF@1% (see the test above), which is a different complaint about
    # a different thing. What this test is about is the property baseline, so
    # that is what is asserted about it: whatever else the judge says, it does
    # not say the reference method is merely a weight detector.
    assert not any("it is that baseline" in r for r in good["verdict"].reasons), \
        good["verdict"].report()


def test_the_library_is_not_dense_enough_to_saturate_the_metric(tmp_path):
    """EF@1% has a ceiling of 1/active_fraction. Capping decoys while keeping
    every active once left the library 40% active, the ceiling at 2.5, and
    molecular weight scoring exactly what fingerprint similarity scored."""
    out = _run(SCREENING, tmp_path)
    assert out["metrics"]["active_fraction"] < 0.05
    assert out["metrics"]["ef_ceiling"] > 20


def test_enrichment_is_reported_on_targets_held_out_entirely(tmp_path):
    out = _run(SCREENING, tmp_path)
    assert out["metrics"]["heldout_targets"] >= 2
    assert any("assayed" in r for r in out["verdict"].reasons), \
        "no activity may be claimed without an assay"


# ------------------------------------------ cancer: external, and calibrated

def test_the_model_is_validated_on_an_external_cohort(tmp_path):
    out = _run(ONCO, tmp_path)
    m = out["metrics"]
    assert m["c_index_external"] > 0.5
    assert m["external_drop"] > 0, \
        "the external cohort should be harder; otherwise it is not external"
    assert any("external" in r for r in out["verdict"].reasons)


def test_discrimination_alone_is_not_enough(tmp_path):
    out = _run(ONCO, tmp_path)
    assert out["metrics"]["calibration_monotone"] == 1.0
    assert any("clinician" in r for r in out["verdict"].reasons), \
        "the audience is named in the verdict, every time"


def test_an_internal_only_result_is_not_a_prognostic_claim():
    """No cohort, no claim — the judge refuses rather than reporting the
    internal number as if it were the answer."""
    v = ONCO.judge({"c_index_internal": 0.82, "c_index_external": float("nan"),
                    "external_drop": float("nan"), "calibration_monotone": 0.0,
                    "median_survival_low_risk": 1.0,
                    "median_survival_high_risk": 1.0})
    assert not v.passed
    assert any("not a prognostic claim" in r for r in v.reasons)


# ---------------------------------------------- guardrails must point the right way

def test_a_lower_is_better_guardrail_is_not_inverted():
    """The most dangerous defect found in this work, kept as a test.

    `guardrail_breaches` defaulted every metric to higher-is-better and nothing
    ever passed a direction. For spinal cord dose that is exactly backwards: a
    cord dose RISING read as fine, and a cord dose falling read as a breach. The
    guardrail that exists to stop a planner buying target coverage with the cord
    would have approved that trade and rejected the plans that spared the organ.

    Real case that exposed it: one OpenKBP patient reached full target coverage
    with 70.1 Gy in a cord limited to 45."""
    from ai4science.harness.agents.research_agents.search import Trial, Candidate
    from ai4science.harness.agents.research_agents.runners import MEDPHYS

    dirs = MEDPHYS.guardrail_directions()
    assert dirs["SpinalCord_Dmax"] is False, "lower is better for a cord"
    assert dirs["hot_spot"] is False

    worse = Trial(Candidate({}), (0,), (60.0,), (62.0,),
                  guardrails={"SpinalCord_Dmax": (38.0, 70.1)})
    assert worse.guardrail_breaches(dirs), \
        "a cord going 38 -> 70 Gy is a breach, whatever happened to coverage"

    better = Trial(Candidate({}), (0,), (60.0,), (62.0,),
                   guardrails={"SpinalCord_Dmax": (38.0, 30.0)})
    assert not better.guardrail_breaches(dirs), \
        "and sparing the cord is not"


def test_every_declared_guardrail_has_a_stated_direction():
    """Silence defaults to higher-is-better, which is how the inversion hid."""
    from ai4science.harness.agents.research_agents.runners import BENCHMARKS
    for name, b in BENCHMARKS.items():
        d = b.guardrail_directions()
        assert set(d) == set(b.guardrails), name
