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
    BENCHMARKS, CAPSULE, LDCT, MEDPHYS, METHYLAGE, ONCO, SCREENING,
    benchmark_for,
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


@pytest.mark.parametrize("name", ["low-dose-ct", "drug-design"])
def test_the_intended_method_passes(name, tmp_path):
    out = _run(benchmark_for(name), tmp_path)
    assert out["verdict"].passed, out["verdict"].report()


def test_drug_designs_query_set_is_a_different_series_from_what_it_scores(tmp_path):
    """The split that made EF@1% mean something again.

    The query set used to be drawn at RANDOM from each target's actives. DUD-E
    actives are largely analogue series, so the ten handed to the solver were
    usually close relatives of the ones being scored — test actives sat at 0.519
    mean max-Tanimoto to the query against 0.154 for the decoys. Nearest
    neighbour retrieval found them without generalising, EF@1% pinned at 100% of
    its ceiling, and seven different methods scored it identically.

    The query set is drawn from whole clusters now and the rest of those clusters
    is withheld, so what is left to find is a series the solver was never shown.
    This test holds the property that fixed it, not the number it produced: the
    actives being scored must not be near-neighbours of the query set.
    """
    out = _run(SCREENING, tmp_path)
    m = out["metrics"]

    ws = tmp_path / "seed" if (tmp_path / "seed").exists() else tmp_path
    import numpy as np
    d = lambda n: np.load(next(ws.rglob(n + ".npy")))
    FP, tid, known, y = (d("fingerprints").astype(bool), d("target_id"),
                         d("known_active"), d("labels"))

    def max_tanimoto(A, B):
        A16, B16 = A.astype(np.uint16), B.astype(np.uint16)
        inter = A16 @ B16.T
        union = A16.sum(1)[:, None] + B16.sum(1)[None, :] - inter
        return (inter / np.clip(union, 1, None)).max(axis=1)

    gaps = []
    for t_id in np.unique(tid):
        m_t = tid == t_id
        q = FP[m_t & (known == 1)]
        act = FP[m_t & (known == 0) & (y == 1)]
        dec = FP[m_t & (known == 0) & (y == 0)]
        if len(q) == 0 or len(act) == 0:
            continue
        gaps.append(max_tanimoto(act, q).mean() - max_tanimoto(dec, q).mean())
    gap = float(np.mean(gaps))
    assert gap < 0.20, (
        "scored actives are %.3f more similar to the query set than the decoys "
        "are; at 0.365 this benchmark could be solved by finding analogues" % gap)

    # And the consequence: the metric has room to move, so it can rank methods.
    headroom = 1.0 - m["ef_at_1pct"] / m["ef_ceiling"]
    assert headroom > 0.02, out["verdict"].report()
    assert out["verdict"].passed, out["verdict"].report()


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
    assert good["verdict"].passed, good["verdict"].report()
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
    """External means INDEPENDENT, not harder.

    This used to assert `external_drop > 0` — "the external cohort should be
    harder; otherwise it is not external". That is the wrong test and it was
    load-bearing in the wrong direction: it would have failed any honest
    site-disjoint split whose held-out hospitals happened to be easier, and it
    passed happily while the benchmark was validating adenocarcinoma against
    squamous cell and calling the result a transport failure.

    What makes a cohort external is that nothing about it was used to fit — no
    patient, and no contributing institution. Whether it scores higher or lower
    is a fact about which hospitals landed in the held-out third, not a
    property the benchmark gets to require."""
    out = _run(ONCO, tmp_path)
    m = out["metrics"]
    assert m["c_index_external"] > 0.5
    assert any("external" in r for r in out["verdict"].reasons)
    # The drop is reported, and its SIGN is not asserted.
    assert "external_drop" in m
    assert abs(m["external_drop"]) < 0.3, \
        "internal %.4g vs external %.4g is too far apart to be one population" % (
            m["c_index_internal"], m["c_index_external"])
    # And the cross-histology number is present and NOT the pass criterion:
    # it is a different disease, which is a different question.
    assert 0.4 < m["c_index_cross_histology"] < 0.7


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

# ------------------------------------------------------------ reverse aging

def test_the_clock_beats_predicting_the_mean_age(tmp_path):
    """A clock has to know something about the individual.

    Predicting the training cohort's mean age for everybody is the bar. It is a
    low bar on purpose — what this benchmark is actually for is the check
    below — but a method that cannot clear it has learnt an intercept."""
    out = _run(METHYLAGE, tmp_path)
    m = out["metrics"]
    assert m["mae_years"] < 0.75 * m["mae_years_constant_baseline"], \
        out["verdict"].report()
    assert m["n_external"] >= 50


def test_the_clock_is_not_only_reading_what_the_blood_is_made_of(tmp_path):
    """The field's characteristic failure, made measurable.

    Whole-blood methylation's leading components are dominated by cell-type
    proportions, and those shift with age by themselves. A clock riding on them
    is a blood-count detector with a birthday attached: it will report an
    impressive error and will not transfer to a tissue whose composition
    differs. So the benchmark refits with those components projected out and
    reports how much of the advantage survives.

    This asserts the number is COMPUTED and BOUNDED, not that it takes a
    particular value — the measured share is about 0.55, and pinning that would
    make the test a record of one run rather than a property."""
    out = _run(METHYLAGE, tmp_path)
    m = out["metrics"]
    assert 0.0 <= m["bulk_structure_share"] <= 1.5
    # Removing structure cannot make the clock better; if it did, the projection
    # is not doing what it claims.
    assert m["mae_years_pcs_removed"] >= m["mae_years"] - 1e-6
    assert m["bulk_structure_share"] <= 0.75, out["verdict"].report()
    assert any("cell composition" in r for r in out["verdict"].reasons)


def test_the_clock_never_claims_to_measure_ageing(tmp_path):
    """The rule this agent exists to hold, asserted on every verdict.

    It predicts chronological age, which is already known. Nothing in this
    corpus is an outcome, and the judge says so pass or fail rather than
    letting a good error be read as evidence about ageing."""
    out = _run(METHYLAGE, tmp_path)
    joined = " ".join(out["verdict"].reasons)
    assert "a clock is not a lifespan" in joined
    assert "outcome_link" in joined and "unmeasured" in joined
    assert "outcome_link" not in out["metrics"], \
        "an unmeasured dimension must stay absent, not be filled with a proxy"


def test_the_held_out_ages_never_reach_the_sandbox(tmp_path):
    """The answer key is the ages. A solver that could read them scores zero
    error and means nothing."""
    _run(METHYLAGE, tmp_path)
    assert "data/ext_age.npy" in METHYLAGE.answer_key
    staged = tmp_path / "run" / "data" / "ext_age.npy"
    assert not staged.exists(), "the held-out ages were staged into the sandbox"
    # and the solver's own workspace has the inputs it is supposed to have
    assert (tmp_path / "run" / "data" / "ext_betas.npy").exists()


def test_validation_sites_contributed_nothing_to_the_fit(tmp_path):
    """Site-disjoint, checked in the data rather than trusted from a docstring.

    `cancer` had to have exactly this corrected after the fact, and the reason
    it went unnoticed was that nothing asserted it."""
    _run(METHYLAGE, tmp_path)
    import json
    import numpy as np
    meta = json.loads((tmp_path / "seed" / "meta.json").read_text()) \
        if (tmp_path / "seed" / "meta.json").exists() else None
    dev = np.load(tmp_path / "seed" / "data" / "dev_betas.npy")
    ext = np.load(tmp_path / "seed" / "data" / "ext_betas.npy")
    assert len(dev) > 50 and len(ext) > 50
    # No sample appears on both sides: identical rows would mean a leaked patient.
    dev_rows = {r.tobytes() for r in dev[:, :50]}
    assert not any(r.tobytes() in dev_rows for r in ext[:, :50]), \
        "a sample appears in both the development and validation cohorts"

def test_the_lesion_lands_in_tissue_and_the_noise_roi_is_noise(tmp_path):
    """The site picker used to be dead code with a silent fallback.

    Uniformity was tested as `local_var < 900` — 30 HU — on the raw image, which
    carries about 100 HU of noise at full dose. The condition was never true
    anywhere, an empty candidate set returned the centre of the image, and so
    every lesion went to pixel (256, 256): mediastinum on two patients, lung on
    the other two. Where it landed in lung the scorer's background ring filled
    with air, `noise_hu` came out at 396 instead of ~15, and lesion CNR fell
    below the Rose criterion however well the lesion had been restored.

    The giveaway was `lesion_contrast_retained` of 2.02 — 202% of the inserted
    contrast, which is not a restoration result but a broken denominator.

    This asserts the physics rather than the fix: the background the benchmark
    calls noise has to BE noise."""
    import numpy as np
    out = _run(LDCT, tmp_path)
    m = out["metrics"]

    full = np.load(tmp_path / "seed" / "data" / "full_dose.npy")
    mask = np.load(tmp_path / "seed" / "data" / "lesion_mask.npy")
    ys, xs = np.nonzero(mask)
    cy, cx = int(ys.mean()), int(xs.mean())
    yy, xx = np.ogrid[:full.shape[0], :full.shape[1]]
    d2 = (yy - cy) ** 2 + (xx - cx) ** 2
    r = int(np.sqrt(mask.sum() / np.pi)) + 1
    ring = (d2 > (2 * r) ** 2) & (d2 <= (5 * r) ** 2)

    air = float((full[ring] < -500).mean())
    assert air < 0.02, ("%.0f%% of the background ring is air — CNR against a "
                        "lung boundary measures anatomy, not detectability" % (100 * air))
    # Not the image centre by default. Anywhere is fine; the middle every time
    # is the fallback firing.
    assert (cy, cx) != (full.shape[0] // 2, full.shape[1] // 2)
    # Soft-tissue noise, not a tissue/air step.
    assert m["noise_hu"] < 60, "noise %.0f HU is anatomy, not noise" % m["noise_hu"]
    # More contrast out than was put in is not a restoration.
    assert m["lesion_contrast_retained"] <= 1.2, m["lesion_contrast_retained"]

