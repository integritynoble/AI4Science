"""The governor's research agents, built.

Each is a charter, a self-model, a budget shape and a seeded field map. The
domain content comes from the design set in
``docs/research-agents/`` — one file per agent — and the point of putting it in
code rather than prose is that a charter which is only prose is a charter the
runtime cannot enforce.

Three of the six already have an ``AgentSpec`` reaching them (``imaging`` here,
``drug-design`` and ``cancer`` from the installed ``pwm-agent-*`` packages); the
other three get specs alongside this module. This registry is keyed by agent
name and attaches to whichever spec provides it, so nothing here collides with
an entry-point package.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from .budget import Budget, Switch
from .charter import Charter
from .fieldmap import Claim, FieldMap, UNTRIED
from .selfmodel import Dimension, SelfModel


@dataclass
class ResearchAgent:
    """One field, and everything that bounds an agent working in it."""

    charter: Charter
    self_model: SelfModel
    switch: Switch
    #: What a night's standing grant should cover, in the agent's own units.
    night: Tuple[float, str]
    field_map: FieldMap

    @property
    def name(self) -> str:
        return self.charter.name

    def benchmark(self):
        """This agent's runnable problem, or None.

        `imaging` is the exception and deliberately so: it had a runner before
        this package existed (`agents/imaging/`, driven by `run_imaging_task`),
        and pointing it at a second one would give the same agent two ways to be
        scored. Its runner is reached through its own AgentSpec's RUNNER."""
        from .runners import BENCHMARKS
        return BENCHMARKS.get(self.name)

    def can_compute(self) -> bool:
        return self.benchmark() is not None or self.name == "imaging"

    def night_budget(self) -> Budget:
        units, unit = self.night
        return Budget(self.name, units=units, unit=unit)

    def report(self) -> str:
        return "\n\n".join([self.charter.describe(), self.self_model.report(),
                            self.field_map.report()])


def _agent(charter: Charter, dims: Tuple[Dimension, ...], limits: Tuple[str, ...],
           night: Tuple[float, str], claims=()) -> ResearchAgent:
    return ResearchAgent(charter=charter,
                         self_model=SelfModel(charter.name, dims, limits),
                         switch=Switch(charter.name), night=night,
                         field_map=FieldMap(charter.name, claims))


# --------------------------------------------------------------------------
# computational imaging
# --------------------------------------------------------------------------

def _computational_imaging() -> ResearchAgent:
    ch = Charter(
        name="imaging",
        field="computational imaging — the image is computed, not captured",
        subfields=("optics-design", "ct", "mri", "single-pixel", "sci-cassi",
                   "lensless", "ptychography", "holography", "light-field",
                   "time-of-flight", "event", "interferometric", "photoacoustic",
                   # Also covered, and each of these is a standalone agent too.
                   # A generalist here inherits that agent's refusals — see
                   # coverage.py; this list is what makes the inheritance apply.
                   "low-dose", "sparse-view", "photon-counting",
                   "imaging-physics", "lesion-detection", "video-reduction"),
                owns=("optics-design", "mri", "single-pixel", "sci-cassi", "lensless", "ptychography", "holography", "light-field", "time-of-flight", "event", "interferometric", "photoacoustic"),
may_improve=("method", "plan", "own_parameters"),
        includes=("low-dose-ct", "medical-physics", "pill-camera"),
        # The forward operator is the measurement's physics. An agent that can
        # change it can improve any number by describing a different experiment.
        also_never=("forward_model",),
        refusals=(
            "physics is not a hyperparameter — the operator used to evaluate an "
            "existing measurement is fixed input",
            "a reconstruction that beats the state of the art while its "
            "forward-model residual worsens is a pipeline bug, not a result",
            "a simulation-only gain is labelled simulation-only in the headline",
        ),
        scope=(
            "it reconstructs; it does not interpret what is in the scene — a "
            "boundary of its own role, not a rule for the specialists whose job "
            "interpreting is",
            "on a subfield another agent covers — CT, imaging physics, capsule — "
            "it works under that agent's binding refusals as well as its own, "
            "whether or not that agent is installed",
        ),
        transfer_from=("mri", "ct", "sci-cassi", "microscopy", "novel-view-synthesis"),
        autonomous_work=("reproduce a published architecture into the common table",
                         "fill a cell of the transfer table",
                         "run a method across subfields with only the operator changed",
                         "evaluate a checkpoint on a real capture it has not seen",
                         "propose and simulate an encoder design",
                         "publish the negative result when a crossing fails"),
    )
    dims = (
        Dimension("sim_fidelity", "simulation fidelity",
                  "PSNR/SSIM per scene on the fixed simulation set, never a bare average"),
        Dimension("real_fidelity", "real-data fidelity",
                  "the same on real captures — the number that actually moves"),
        Dimension("sim_real_gap", "sim→real gap",
                  "simulation fidelity minus real fidelity",
                  higher_is_better=False,
                  not_to_be_confused_with="either number on its own"),
        Dimension("residual", "forward-model residual",
                  "||y - A x_hat|| on the real measurement", higher_is_better=False),
        Dimension("operator_generalisation", "operator generalisation",
                  "fidelity under a mask/trajectory/angle set not trained on"),
        Dimension("cost", "inference cost",
                  "seconds and peak memory on a stated device", higher_is_better=False),
        Dimension("transfer_cells", "transfer cells filled",
                  "count of subfield crossings implemented and evaluated here"),
    )
    limits = (
        "simulation results are cheap and infinite; a gain that does not appear "
        "on real data has not been shown to exist",
        "it does not interpret a reconstructed scene — no diagnosis, no material "
        "identification, no count",
        "it cannot fabricate or measure an optical element; designed encoders are "
        "simulated until someone makes one",
    )
    claims = (
        Claim(key="diffusion-priors-to-ptychography",
              statement="score-based priors, standard in MRI/CT, untried in ptychography",
              source="transfer table", status=UNTRIED, subfield="ptychography",
              from_subfield="mri"),
        Claim(key="inr-to-single-pixel",
              statement="implicit neural representations, used in sparse-view CT, untried for single-pixel",
              source="transfer table", status=UNTRIED, subfield="single-pixel",
              from_subfield="ct"),
        Claim(key="selfsup-denoise-to-nolatent",
              statement="self-supervised denoising with no clean target, from microscopy, untried in most subfields",
              source="transfer table", status=UNTRIED, subfield="photoacoustic",
              from_subfield="microscopy"),
    )
    return _agent(ch, dims, limits, night=(6.0, "gpu-hour"), claims=claims)


# --------------------------------------------------------------------------
# low-dose CT
# --------------------------------------------------------------------------

def _low_dose_ct() -> ResearchAgent:
    ch = Charter(
        name="low-dose-ct",
        specialises="imaging",
        field="diagnostic CT from fewer photons, and deciding whether you got one",
        subfields=("low-dose", "sparse-view", "limited-angle", "interior",
                   "photon-counting", "dual-energy", "metal-artefact", "motion-4d",
                   "cone-beam", "dose-estimation", "task-based-iq", "reader-studies"),
                owns=("low-dose", "sparse-view", "limited-angle", "interior", "photon-counting", "dual-energy", "metal-artefact", "motion-4d", "cone-beam", "dose-estimation", "task-based-iq", "reader-studies"),
may_improve=("method", "plan", "own_parameters"),
        also_never=("forward_model", "dose_equivalence_framework", "observer_model",
                    "leaderboard"),
        refusals=(
            "a fidelity gain with flat detectability is a failure, not a mixed "
            "result — smoothing raises PSNR by removing the lesion the scan was for",
            "it competes on a leaderboard it has no write path to",
            "reconstruction quality is not a diagnostic claim; a model observer is "
            "a proxy for a reader study, not a substitute",
        ),
        transfer_from=("mri", "sci-cassi", "microscopy", "novel-view-synthesis"),
        autonomous_work=("reproduce a newly published method into the common table",
                         "run the comparison table on an unused vendor or dose level",
                         "re-evaluate existing methods on photon-counting data",
                         "ablate a component and report the effect on both metrics",
                         "carry a method in from a neighbouring subfield",
                         "publish the negative result when it does not carry"),
    )
    dims = (
        Dimension("detectability", "task detectability",
                  "model-observer detectability on inserted low-contrast signals",
                  not_to_be_confused_with="image quality by eye"),
        Dimension("fidelity", "reconstruction fidelity",
                  "PSNR/SSIM against the paired full-dose scan, per vendor",
                  not_to_be_confused_with="detectability",
                  requires="detectability"),
        Dimension("reproduction", "baseline reproduction",
                  "reproducing a published baseline in a container, to a stated tolerance",
                  not_to_be_confused_with="agreeing with the published number"),
        Dimension("dose_calibration", "dose-equivalence calibration",
                  "error between predicted and measured equivalent dose",
                  higher_is_better=False),
        Dimension("cross_vendor", "cross-vendor generalisation",
                  "both metrics on a vendor held out entirely",
                  not_to_be_confused_with="the average across vendors"),
        Dimension("artefact_classes", "artefact-specific behaviour",
                  "metal, motion and truncation cases scored separately"),
        Dimension("runtime", "runtime", "seconds per volume on a stated GPU",
                  higher_is_better=False),
    )
    limits = (
        "a reconstruction quality gain is not a diagnostic claim; non-inferiority "
        "needs a reader study with radiologists and there is no path to one here",
        "model observers are a proxy for that study",
        "vendor generalisation is unmeasured unless a vendor was held out entirely",
    )
    claims = (
        Claim(key="photon-counting-retry",
              statement="most published low-dose methods have never been re-evaluated on photon-counting data",
              source="field survey", status=UNTRIED, subfield="photon-counting",
              from_subfield="low-dose"),
        Claim(key="selfsup-to-ldct",
              statement="self-supervised denoising without clean targets, from microscopy, only partly tried here",
              source="transfer table", status=UNTRIED, subfield="low-dose",
              from_subfield="microscopy"),
    )
    return _agent(ch, dims, limits, night=(8.0, "gpu-hour"), claims=claims)


# --------------------------------------------------------------------------
# medical physics
# --------------------------------------------------------------------------

def _medical_physics() -> ResearchAgent:
    ch = Charter(
        name="medical-physics",
        specialises="imaging",
        field="the physics of radiation used to treat and image people",
        subfields=("treatment-planning", "dose-calculation", "auto-segmentation",
                   "adaptive-rt", "image-guidance", "particle-therapy", "flash",
                   "brachytherapy", "dosimetry-qa", "radiobiology", "imaging-physics",
                   "incident-learning", "outcome-modelling"),
                owns=("treatment-planning", "dose-calculation", "auto-segmentation", "adaptive-rt", "image-guidance", "particle-therapy", "flash", "brachytherapy", "dosimetry-qa", "radiobiology", "imaging-physics", "incident-learning", "outcome-modelling"),
may_improve=("method", "plan", "own_parameters"),
        also_never=("clinical_constraints", "protocol", "acceptance_criteria",
                    "approval_state"),
        refusals=(
            "it produces plan candidates and QA findings; a qualified medical "
            "physicist signs anything that touches a patient",
            "it never writes into a treatment planning system, exports a "
            "deliverable plan, or marks a plan approved",
            "the autonomous function runs on retrospective, de-identified or "
            "phantom data only — 'unattended' and 'waiting patient' never meet",
            "clinical deployment is not a permission the owner can grant alone",
        ),
        transfer_from=("imaging", "ct", "mri", "uncertainty-estimation"),
        autonomous_work=("QA sweeps over retrospective archives",
                         "benchmark dose prediction or segmentation on a cohort",
                         "measure inter-planner or inter-institution variability",
                         "standardise structure nomenclature across a dataset",
                         "mine an incident-learning corpus for failure modes",
                         "calibrate uncertainty on held-out cases"),
    )
    dims = (
        Dimension("dose_error_max", "dose prediction error (max)",
                  "maximum dose difference vs the delivered plan",
                  higher_is_better=False,
                  not_to_be_confused_with="the mean, which hides the hot spot"),
        Dimension("dose_error_mean", "dose prediction error (mean)",
                  "mean dose difference vs the delivered plan", higher_is_better=False,
                  requires="dose_error_max"),
        Dimension("dvh_pass", "DVH criterion pass rate",
                  "fraction of clinical constraints met, per protocol and structure"),
        Dimension("deliverability", "deliverability",
                  "MU, segment count and leaf motion against machine constraints"),
        Dimension("contour_dsc", "contour agreement",
                  "DSC and surface distance per structure, never a mean across them"),
        Dimension("calibration", "uncertainty calibration",
                  "stated confidence against observed error"),
        Dimension("nomenclature", "nomenclature conformance",
                  "fraction of structures resolvable to a standard name"),
        Dimension("time_to_plan", "time to plan",
                  "wall-clock for the adaptive loop", higher_is_better=False),
    )
    limits = (
        "no output is clinically validated, cleared, or ready for use on patients, "
        "and the agent refuses to describe one that way even when asked",
        "it has no access to live patient data and no path to a prospective trial",
        "a plan candidate is not a plan until a physicist signs it",
    )
    claims = (
        Claim(key="interplanner-variability",
              statement="inter-planner and inter-institution plan variability is largely unmeasured",
              source="field survey", status="proxy_only", subfield="treatment-planning"),
        Claim(key="incident-corpus-unmined",
              statement="incident-learning corpora are large and systematically under-analysed",
              source="field survey", status="unreplicated", subfield="incident-learning"),
    )
    return _agent(ch, dims, limits, night=(4.0, "gpu-hour"), claims=claims)


# --------------------------------------------------------------------------
# pill camera
# --------------------------------------------------------------------------

def _pill_camera() -> ResearchAgent:
    ch = Charter(
        name="pill-camera",
        specialises="imaging",
        field="wireless capsule endoscopy, and reading GI video nobody has time to read",
        subfields=("capsule-hardware", "localisation", "active-locomotion",
                   "lesion-detection", "rare-class", "video-reduction",
                   "temporal-modelling", "quality-completeness", "cross-vendor",
                   "physics-informed", "clinical-validation"),
                owns=("capsule-hardware", "localisation", "active-locomotion", "lesion-detection", "rare-class", "video-reduction", "temporal-modelling", "quality-completeness", "cross-vendor", "physics-informed", "clinical-validation"),
may_improve=("method", "plan", "own_parameters"),
        also_never=("split", "seed_set", "statistical_test", "correction"),
        refusals=(
            "seed variance is not an improvement — the honest effects in this "
            "field are smaller than the run-to-run spread",
            "every seed in the fixed set is reported, including the ones that went "
            "the wrong way",
            "patient-disjoint splits are verified programmatically, not asserted",
            "an uncorrected p-value is not reported at all",
            "an AUC is not a diagnostic performance claim",
        ),
        transfer_from=("colonoscopy-ai", "video-understanding", "self-supervised-pretraining"),
        autonomous_work=("run the fixed-seed protocol on a new architecture or prior",
                         "reproduce a published capsule method under this protocol",
                         "carry a colonoscopy-AI method across",
                         "ablate channels and report the per-class effect",
                         "compute reading-time reduction curves",
                         "publish the negative result"),
    )
    dims = (
        Dimension("macro_auc", "macro-AUC with interval",
                  "over the fixed seed set, on the patient-disjoint split",
                  not_to_be_confused_with="a point estimate from one run",
                  requires="per_class"),
        Dimension("per_class", "per-class performance",
                  "per-class AUC, especially the rare classes the study exists for"),
        Dimension("cross_vendor", "cross-vendor consistency",
                  "direction held on a second vendor under a second backbone"),
        Dimension("seed_agreement", "seed agreement",
                  "how many of N seeds moved the right way, as a fraction"),
        Dimension("calibration", "calibration",
                  "probabilities usable by a reader, not merely ranked"),
        Dimension("temporal_gain", "temporal gain",
                  "what sequence modelling adds over frame-wise"),
        Dimension("reading_time", "reading-time reduction",
                  "frames a clinician must review at fixed sensitivity",
                  higher_is_better=False),
        Dimension("prior_fidelity", "prior fidelity",
                  "correlation between the physics prior and model attention"),
    )
    limits = (
        "an AUC is not a diagnostic performance claim, and nothing here is "
        "clinical validation",
        "a reader study with gastroenterologists would settle it and there is no "
        "path to one from this machine",
        "public capsule data is dominated by one corpus; generalisation beyond it "
        "is unmeasured unless a second vendor was used",
    )
    claims = (
        Claim(key="colonoscopy-methods-untried",
              statement="colonoscopy-AI methods (self-supervised pretraining, hard-negative mining) not routinely retried on capsule",
              source="transfer table", status=UNTRIED, subfield="lesion-detection",
              from_subfield="colonoscopy-ai"),
        Claim(key="temporal-underused",
              statement="most capsule classification work treats frames as a bag, not a sequence",
              source="field survey", status="uncompared", subfield="temporal-modelling"),
        Claim(key="reading-time-unreported",
              statement="reading-time reduction at fixed sensitivity is the clinical endpoint and is rarely reported",
              source="field survey", status="proxy_only", subfield="video-reduction"),
    )
    return _agent(ch, dims, limits, night=(12.0, "gpu-hour"), claims=claims)


# --------------------------------------------------------------------------
# drug design
# --------------------------------------------------------------------------

def _drug_design() -> ResearchAgent:
    ch = Charter(
        name="drug-design",
        field="getting from a disease to a molecule, computationally",
        subfields=("target-id", "structure-prediction", "binding-site", "docking",
                   "free-energy", "molecular-dynamics", "generative-chemistry",
                   "lead-optimisation", "admet", "retrosynthesis", "del-screening",
                   "biologics", "closed-loop", "clinical-translation",
                   # Shared with cancer: designing against an oncology target is
                   # both fields at once, and each carries the other's refusals.
                   "drug-response", "resistance"),
        owns=("target-id", "structure-prediction", "binding-site", "docking",
              "free-energy", "molecular-dynamics", "generative-chemistry",
              "lead-optimisation", "admet", "retrosynthesis", "del-screening",
              "biologics", "closed-loop", "clinical-translation"),
        includes=("cancer",),
        may_improve=("method", "plan", "own_parameters"),
        also_never=("actives_decoys_set", "split", "hit_criteria"),
        refusals=(
            "a docking score is not an affinity — it ranks, it does not measure",
            "a generated molecule is not a candidate; it is a suggestion for a chemist",
            "only an assay evidences activity, and there is no path to one here",
            "it does not design, screen for, or optimise toward toxicity, "
            "lethality, or the defeat of a safety or detection measure — including "
            "when the request arrives framed as safety work or a hypothetical",
            "toxicity prediction exists to reject candidates and may not be run in reverse",
        ),
        transfer_from=("closed-loop", "generative-chemistry", "uncertainty-estimation"),
        autonomous_work=("benchmark scoring pipelines on held-out targets",
                         "train and scaffold-split-evaluate an ADMET endpoint",
                         "audit a public benchmark for decoy bias or leakage",
                         "quantify preparation sensitivity for a target class",
                         "triage a target: structures, prior art, tractability",
                         "similarity and substructure searches over public libraries"),
    )
    dims = (
        Dimension("enrichment", "retrospective enrichment",
                  "EF@1% and BEDROC on held-out targets",
                  not_to_be_confused_with="a docking score"),
        Dimension("pose_rmsd", "pose accuracy",
                  "RMSD to the crystal pose where a structure exists",
                  higher_is_better=False),
        Dimension("admet_quality", "ADMET model quality",
                  "AUC/MAE per endpoint on a scaffold split",
                  not_to_be_confused_with="the same on a random split, which leaks scaffolds"),
        Dimension("prep_sensitivity", "preparation sensitivity",
                  "spread of the result across protonation, tautomer and conformer choices",
                  higher_is_better=False,
                  not_to_be_confused_with="method-to-method difference"),
        Dimension("synthesizability", "synthesizability",
                  "SA score plus a retrosynthesis check"),
        Dimension("novelty", "novelty",
                  "distance to the nearest training compound"),
        Dimension("calibration", "calibration",
                  "stated confidence against observed enrichment"),
    )
    limits = (
        "every result is computational and retrospective; no proposed compound has "
        "been made or assayed",
        "the distance between 'ranks well' and 'works' is the whole field",
        "nothing here is a therapeutic claim, a dosing suggestion, or medical advice",
        "ordering, synthesising and assaying are outward acts it prepares and "
        "never performs",
    )
    claims = (
        Claim(key="prep-confound",
              statement="preparation choices may move enrichment more than method choice does, and this is rarely controlled",
              source="field survey", status="proxy_only", subfield="docking"),
        Claim(key="decoy-bias",
              statement="standard decoy sets carry property bias that inflates enrichment",
              source="field survey", status="unreplicated", subfield="docking"),
        Claim(key="random-splits-admet",
              statement="published ADMET numbers largely use random splits, which leak scaffolds",
              source="field survey", status="unreplicated", subfield="admet"),
    )
    return _agent(ch, dims, limits, night=(6.0, "gpu-hour"), claims=claims)


# --------------------------------------------------------------------------
# cancer
# --------------------------------------------------------------------------

def _cancer() -> ResearchAgent:
    ch = Charter(
        name="cancer",
        field="computational cancer biology and oncology data science",
        subfields=("genomics", "variant-interpretation", "multi-omics",
                   "single-cell-spatial", "tumour-evolution", "immuno-oncology",
                   "liquid-biopsy", "digital-pathology", "radiomics",
                   "drug-response", "prognostic-modelling", "trials",
                   "real-world-evidence",
                   # Shared: with drug-design where an oncology target is being
                   # designed against, and with medical-physics where the
                   # question is what the delivered dose did to the patient.
                   "resistance", "target-id", "outcome-modelling",
                   "clinical-translation"),
        owns=("genomics", "variant-interpretation", "multi-omics",
              "single-cell-spatial", "tumour-evolution", "immuno-oncology",
              "liquid-biopsy", "digital-pathology", "radiomics",
              "drug-response", "prognostic-modelling", "trials",
              "real-world-evidence", "resistance"),
        includes=("drug-design",),
        may_improve=("method", "plan", "own_parameters"),
        also_never=("tiering_guidelines", "validation_cohort", "adjudicated_matches",
                    "patient_record"),
        refusals=(
            "it advises a clinician; it never advises a patient",
            "it produces trial candidates; a site determines eligibility",
            "it never recommends, adjusts, or discourages a treatment",
            "patient-level data is W_host — never published, never in a prompt "
            "that leaves the machine, never in an outward act",
            "de-identification is a precondition of the autonomous function, not a "
            "step inside it",
        ),
        transfer_from=("digital-pathology", "real-world-evidence", "uncertainty-estimation"),
        autonomous_work=("externally validate a published model on a public cohort",
                         "benchmark variant classification against a held-out expert set",
                         "quantify disagreement between pipelines on the same data",
                         "measure cohort representativeness for a used dataset",
                         "refresh trial and guideline snapshots and report the diff",
                         "reproduce a published signature and report whether it holds"),
    )
    dims = (
        Dimension("concordance", "variant classification concordance",
                  "agreement with consensus calls under AMP/ASCO/CAP tiering, held out",
                  not_to_be_confused_with="agreement with a database"),
        Dimension("evidence_codes", "evidence completeness",
                  "fraction of calls carrying their evidence codes"),
        Dimension("discrimination", "prognostic discrimination",
                  "C-index or time-dependent AUC on an external cohort",
                  not_to_be_confused_with="internal cross-validation",
                  requires="calibration"),
        Dimension("calibration", "calibration",
                  "predicted against observed survival"),
        Dimension("cohort_coverage", "cohort coverage",
                  "which populations the evidence covers, stated explicitly"),
        Dimension("match_precision", "trial-match precision and recall",
                  "against clinician-adjudicated matches",
                  not_to_be_confused_with="recall alone, maximised by matching everything"),
        Dimension("currency", "currency",
                  "staleness of the trial and guideline snapshot", higher_is_better=False),
    )
    limits = (
        "computational and retrospective; no patient-level claim, not a diagnosis, "
        "not clinical advice — the appropriate reader is a clinician",
        "it refuses to write patient-facing text, and being asked twice does not "
        "change the answer",
        "a model validated only internally is reported as internally validated, "
        "which is usually the most decision-relevant fact about it",
    )
    claims = (
        Claim(key="external-validation-missing",
              statement="most published oncology prognostic models have never been tried on an external cohort",
              source="field survey", status="unreplicated", subfield="prognostic-modelling"),
        Claim(key="pipeline-disagreement",
              statement="variant calls differ materially between pipelines on the same data, rarely quantified",
              source="field survey", status="uncompared", subfield="genomics"),
        Claim(key="cohort-representativeness",
              statement="widely used cohorts do not resemble the patients models are used on",
              source="field survey", status="proxy_only", subfield="real-world-evidence"),
    )
    return _agent(ch, dims, limits, night=(2.0, "gpu-hour"), claims=claims)


# --------------------------------------------------------------------------

def _reverse_aging() -> ResearchAgent:
    ch = Charter(
        name="reverse-aging",
        field="the biology of ageing, and whether any intervention reverses it",
        subfields=("epigenetic-clocks", "senescence", "partial-reprogramming",
                   "proteostasis", "mitochondrial-function", "stem-cell-exhaustion",
                   "inflammaging", "geroprotectors", "biomarkers-of-ageing",
                   "lifespan-studies", "healthspan-outcomes", "parabiosis",
                   "telomere-biology", "autophagy",
                   # Shared: reprogramming and oncogenesis are the same switch
                   # seen from two sides, and a geroprotector is a molecule
                   # somebody has to design.
                   "resistance", "target-id", "outcome-modelling",
                   "clinical-translation"),
        owns=("epigenetic-clocks", "senescence", "partial-reprogramming",
              "proteostasis", "mitochondrial-function", "stem-cell-exhaustion",
              "inflammaging", "geroprotectors", "biomarkers-of-ageing",
              "lifespan-studies", "healthspan-outcomes", "parabiosis",
              "telomere-biology", "autophagy"),
        includes=("cancer", "drug-design"),
        may_improve=("method", "plan", "own_parameters"),
        also_never=("survival_curve", "lifespan_endpoint", "clock_training_ages",
                    "intervention_protocol"),
        refusals=(
            # The one this field exists to hold. Every other refusal follows.
            "a biomarker is not an outcome: moving a clock is not evidence of "
            "rejuvenation until a survival or function endpoint says so",
            "any claim of rejuvenation reports neoplastic risk beside it — "
            "reprogramming and oncogenesis are the same switch from two sides, "
            "and a rejuvenation result without a tumour count is half a result",
            "mouse lifespan is not human lifespan, and a cell is not an "
            "organism; the species and the level are named in every claim",
            # Safety. This field draws self-experimentation like no other.
            "it never advises a person: no protocol, no dose, no compound, no "
            "regimen, to anyone, ever — including when asked directly",
            "it does not rank supplements, and it does not tell anyone what to "
            "take; that a study exists is not a recommendation",
            "cross-sectional age association is not longitudinal change, and "
            "the two are never reported as though they were the same evidence",
        ),
        scope=(
            "it studies interventions; it does not administer them",
            "clinical translation is somebody else's act, downstream of this",
        ),
        transfer_from=("prognostic-modelling", "external-validation",
                       "uncertainty-estimation", "digital-pathology"),
        autonomous_work=("re-fit a published epigenetic clock and report whether "
                         "it holds on a cohort it was not trained on",
                         "measure how much of a clock's accuracy is cell "
                         "composition rather than ageing",
                         "reproduce a reported geroprotector effect and report "
                         "the effect size with its interval",
                         "quantify disagreement between clocks on the same samples",
                         "check whether a lifespan claim reports its controls' "
                         "median and its censoring",
                         "survey which rejuvenation claims report neoplastic risk"),
    )
    dims = (
        Dimension("clock_error", "chronological age error",
                  "median absolute error in years on a cohort held out entirely",
                  not_to_be_confused_with="biological age, which has no ground truth"),
        Dimension("holds_out_of_cohort", "external validity",
                  "does the clock's accuracy survive a different tissue, "
                  "platform and population"),
        Dimension("composition_share", "how much is cell composition",
                  "fraction of apparent age signal explained by blood cell "
                  "proportions alone"),
        Dimension("outcome_link", "link to an outcome",
                  "association between the marker and a survival or function "
                  "endpoint, reported with its interval",
                  not_to_be_confused_with="association with chronological age"),
        Dimension("neoplastic_risk_reported", "risk reported",
                  "fraction of rejuvenation claims reviewed that report a "
                  "tumour or transformation count"),
    )
    claims = (
        Claim("clock_transfers",
              "a clock re-fitted on one cohort holds on another tissue and platform",
              source="field survey", status=UNTRIED, subfield="epigenetic-clocks"),
        Claim("clock_tracks_outcome",
              "clock acceleration tracks a survival or function endpoint, not "
              "merely chronological age",
              source="field survey", status=UNTRIED, subfield="biomarkers-of-ageing"),
        Claim("rejuvenation_reports_risk",
              "published rejuvenation results report a neoplastic risk count",
              source="field survey", status=UNTRIED, subfield="partial-reprogramming"),
        Claim("senescence_methods_agree",
              "senescent-cell burden methods agree with each other on the same sample",
              source="transfer table", status=UNTRIED, subfield="senescence"),
    )
    limits = (
        "there is no ground truth for biological age. Every number this agent "
        "reports is against chronological age or against an outcome — never "
        "against how old someone 'really is', which is not a measurable quantity",
        "nothing here has been tested in a human intervention, and this agent "
        "has run no trial, no animal study and no experiment on tissue",
        "cross-sectional cohorts cannot separate the rate of ageing from cohort "
        "effects, and most public methylation data is cross-sectional",
        "a benchmark for this field is NOT yet built: the other agents each "
        "read a measured corpus, and this one so far has a charter and a field "
        "map. It can hold owner-set work; it cannot yet run a benchmark night",
    )
    return _agent(ch, dims, limits, (12.0, "benchmark runs"), claims)


_BUILDERS = {
    "imaging": _computational_imaging,
    "low-dose-ct": _low_dose_ct,
    "medical-physics": _medical_physics,
    "pill-camera": _pill_camera,
    "drug-design": _drug_design,
    "cancer": _cancer,
    "reverse-aging": _reverse_aging,
}

#: The names in the order the design set lists them.
NAMES: Tuple[str, ...] = tuple(_BUILDERS)


def build(name: str) -> ResearchAgent:
    """A fresh agent. Fresh rather than shared, because a self-model accumulates
    observations and a budget accumulates spend — handing two callers the same
    object would let one agent's night exhaust another's."""
    if name not in _BUILDERS:
        raise KeyError("no research agent %r — have: %s"
                       % (name, ", ".join(NAMES)))
    return _BUILDERS[name]()


def build_all() -> Dict[str, ResearchAgent]:
    return {n: build(n) for n in NAMES}
