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


def _run(bench, tmp_path, override=""):
    _needs_corpus(bench)
    return run_domain_task(bench, client=Sim(tmp_path / "run", override),
                           workspace=tmp_path / "seed", seed=42)


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


@pytest.mark.parametrize("name", ["low-dose-ct", "medical-physics",
                                  "pill-camera", "drug-design"])
def test_the_intended_method_passes(name, tmp_path):
    out = _run(benchmark_for(name), tmp_path)
    assert out["verdict"].passed, out["verdict"].report()


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
    assert list(out["withheld"]) == list(bench.answer_key)


def test_a_run_is_reproducible_from_its_seed(tmp_path):
    a = _run(SCREENING, tmp_path / "a")
    b = _run(SCREENING, tmp_path / "b")
    assert a["metrics"]["ef_at_1pct"] == b["metrics"]["ef_at_1pct"]


# ------------------------------------- low-dose CT: the smoothing failure

BLUR = '''
import argparse, os, sys
import numpy as np
from scipy.ndimage import gaussian_filter
sys.path.insert(0, os.path.dirname(__file__))
from run_solver import fbp
ap = argparse.ArgumentParser(); ap.add_argument("--workspace", default=".")
ws = ap.parse_args().workspace
sino = np.load(os.path.join(ws, "data", "sinogram.npy"))
ang = np.load(os.path.join(ws, "data", "angles.npy"))
rec = fbp(sino, ang, sino.shape[1])
rec = (rec - rec.min()) / max(float(np.ptp(rec)), 1e-9) * 1.35
rec = gaussian_filter(rec, 3.2)
os.makedirs(os.path.join(ws, "results"), exist_ok=True)
np.save(os.path.join(ws, "results", "reconstruction.npy"), rec)
'''


def test_a_higher_psnr_that_erases_the_lesion_FAILS(tmp_path):
    """The refusal this agent exists for, executable.

    The blur wins on PSNR — the metric the field reports — and loses, because
    the low-contrast finding the scan was ordered to detect is gone."""
    good = _run(LDCT, tmp_path / "good")
    blur = _run(LDCT, tmp_path / "blur", override=BLUR)

    assert blur["metrics"]["psnr"] > good["metrics"]["psnr"], \
        "the blur is supposed to win on PSNR; otherwise this proves nothing"
    assert good["verdict"].passed
    assert not blur["verdict"].passed
    assert any("smooth" in r or "gone" in r for r in blur["verdict"].reasons)
    assert blur["metrics"]["lesion_cnr"] < good["metrics"]["lesion_cnr"]


# ------------------------------- medical physics: modulation is not optional

NAIVE_PLAN = '''
import argparse, json, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from run_solver import beamlets, ANGLES
ap = argparse.ArgumentParser(); ap.add_argument("--workspace", default=".")
ws = ap.parse_args().workspace
target = np.load(os.path.join(ws, "data", "target.npy"))
proto = json.load(open(os.path.join(ws, "data", "protocol.json")))
ty, tx = np.argwhere(target).mean(axis=0)
A = np.stack([b for a in ANGLES for b in beamlets(a, ty, tx)])
dose = np.tensordot(np.ones(len(A)), A, axes=(0, 0))
dose = dose * (proto["prescription"] / max(np.percentile(dose[target], 5), 1e-9))
os.makedirs(os.path.join(ws, "results"), exist_ok=True)
np.save(os.path.join(ws, "results", "dose.npy"), dose)
json.dump({"status": "candidate"}, open(os.path.join(ws, "results", "plan_candidate.json"), "w"))
'''


def test_an_unmodulated_plan_fails_the_protocol(tmp_path):
    """Every beamlet wide open covers the target and irradiates the organ. If
    this passed, the benchmark would not be measuring planning at all."""
    good = _run(MEDPHYS, tmp_path / "good")
    naive = _run(MEDPHYS, tmp_path / "naive", override=NAIVE_PLAN)
    assert good["verdict"].passed
    assert not naive["verdict"].passed
    assert naive["metrics"]["oar_Dmean"] > good["metrics"]["oar_Dmean"] * 2
    assert any("OAR" in r and "VIOLATED" in r for r in naive["verdict"].reasons)


def test_the_plan_is_a_candidate_and_says_so(tmp_path):
    import json
    out = _run(MEDPHYS, tmp_path)
    plan = json.loads((Path(out["run_workspace"]) / "results"
                       / "plan_candidate.json").read_text())
    assert plan["status"] == "candidate"
    assert "physicist" in plan["requires"]
    assert any("physicist" in r for r in out["verdict"].reasons)


# ------------------------------------ pill camera: the split, and the prior

def test_the_split_is_patient_disjoint_and_checked(tmp_path):
    out = _run(CAPSULE, tmp_path)
    assert out["metrics"]["patients_crossing_the_split"] == 0
    assert any("patient-disjoint" in r for r in out["verdict"].reasons)


def test_the_physics_prior_beats_the_naive_baseline(tmp_path):
    """Illumination gain varies per patient. An absolute intensity carries it;
    a channel ratio cancels it — which is why the prior is worth having."""
    out = _run(CAPSULE, tmp_path)
    assert out["metrics"]["auc"] > out["metrics"]["baseline_auc"]


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
    assert good["verdict"].passed, good["verdict"].report()
    assert not weight["verdict"].passed
    assert any("it is that baseline" in r for r in weight["verdict"].reasons)
    assert weight["metrics"]["auc_unseen"] < good["metrics"]["auc_unseen"]


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
