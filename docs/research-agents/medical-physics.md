# The medical physics agent — how to design it

**Status: built, on real data, planner rewritten 2026-08-05.** The benchmark
reads **OpenKBP** — eight real head-and-neck cases with CT, contours, and the
dose the patient was actually treated with, which is the answer key and never
enters the sandbox. The protocol is the real one: D99 to three target volumes,
brainstem 54 Gy, cord 45, parotid mean 26, mandible 70.

**The planner was not short of 3D modulation, as claimed here earlier — it was
wrong in three ways.** Its objective penalised target *underdose* only, so
nothing pushed dose down and normalising D99 to the prescription dragged the
slice up with it: target mean 101.9 Gy against a 70 Gy prescription, and 381 of
655 body voxels above 80. The plan met D99 because D99 is the coldest
percentile — the one statistic that structurally cannot see an overdose. Made
two-sided, it went uniformly *cold*; made asymmetric, as clinical objectives are
because missing the tumour is worse than a hot spot inside it, it plans.

**It now passes on 5 of the 8 patients** with one global set of objective
weights: coverage short on two, and on a third the optimiser bought full
coverage by putting **70.1 Gy into a cord limited to 45**. That is not a defect
to tune away. Objective weights are patient-specific — finding them per case is
what a dosimetrist does, and it is what the night loop's search is for.

**Its reference method fails, and the failure is honest.** A coplanar 2D planner
reaches every target and tracks the delivered plan closely — PTV70 D99 = **70.0
Gy against the clinical 70.02** — and cannot spare a spinal cord that abuts the
target: **51.8 Gy against a 45 Gy limit**, with a hot spot of 190 against 80.5.
Sparing that cord takes full 3D modulation. Raising the penalties traded cord
against hot spot and cleared neither, so the tuning stopped rather than
continuing until something passed.

## 0b. What the benchmark can and cannot ask of these beams

**Measured before being argued about, which is the correction this section
exists to record.** For each patient, the declared parameter space was driven to
its most coverage-favouring corner — target penalties at maximum, organ-at-risk
and hot-spot penalties at minimum — and the resulting D99 is the best these nine
coplanar beams can deliver at this beamlet resolution, whatever objective is
written.

| patient | D99 floor | best D99 reachable | verdict on the floor |
|---|---|---|---|
| 1 | 66.5 | 68.13 | reachable |
| 2 | 66.5 | 68.79 | reachable |
| 3 | 66.5 | **67.85** | reachable — and the planner gets 64.49 |
| 4 | 66.5 | **62.62** | **NOT reachable** |

**Patient 4 is an impossible case and the judge is right to fail it.** At that
corner the hot spot also reaches 94.6 Gy against an 80.5 limit, so the coverage
is not merely unreached but unreachable without a violation elsewhere. Nine
coplanar beams cannot conform to that target on that slice. No objective
function fixes it, and tuning toward it would only be fitting the benchmark.

**Patient 3 is the opposite, and is the real open problem.** A passing plan
exists inside the declared space — D99 67.85 with the cord at 38.9 against a 45
limit and the hot spot at 75.9 against 80.5 — and the planner converges 3.4 Gy
short of it. That is a planner shortfall, not a geometry limit, and it is left
failing rather than hand-tuned: the search space demonstrably contains the
answer, so finding it is the search's job.

> **Three wrong diagnoses preceded this table**, and each was a guess at a cause
> rather than a measurement of what was possible: an impossible constraint set
> (for the wrong reason — the overlap was read off the wrong axis), a step-size
> collapse, and nested targets fighting each other. One achievability run
> separates the two failures in a way none of them did. **Measure the ceiling
> before theorising about the gap.**

## 1. The field

The physics of radiation used to treat and image people, and the quality systems
around it.

| Subfield | What it covers |
|---|---|
| **treatment planning** | IMRT, VMAT, stereotactic; inverse optimisation; the Pareto trade-off surface |
| **dose calculation** | Monte Carlo, collapsed cone, GPU dose engines; the ground truth everything else approximates |
| **auto-segmentation** | organs at risk and targets; structure nomenclature standardisation |
| **adaptive radiotherapy** | online replanning on CBCT and MR-linac, where the whole loop must finish while the patient is on the couch |
| **image guidance and motion** | 4-D, gating, tracking, intrafraction motion |
| **particle therapy** | proton and carbon; range uncertainty, LET and RBE modelling |
| **FLASH** | ultra-high dose rate; dosimetry that existing detectors cannot do |
| **brachytherapy** | source modelling, applicator reconstruction, direction-modulated devices |
| **dosimetry and machine QA** | detectors, commissioning, output constancy, log-file analysis |
| **radiobiology modelling** | TCP/NTCP, fractionation, dose-response from outcome data |
| **imaging physics** | CBCT quality, MR distortion, synthetic CT, dose-of-imaging |
| **incident learning and safety** | the field's own error data, systematically under-analysed |
| **outcome modelling** | linking delivered dose to what happened to the patient |

## 2. What this field is short of

| Shortage | How bad |
|---|---|
| **planning-time bottleneck** | adaptive RT is limited by how fast a plan can be made and checked while a patient waits. This is the field's defining constraint. |
| **inter-planner and inter-institution variability** | the same case planned at two centres gives materially different plans; almost nothing measures this systematically |
| **QA that scales** | more plans, more adaptivity, no more physicists. Automated QA is not a convenience, it is the only way adaptive RT works. |
| **outcome data linked to delivered dose** | dose is recorded, outcome is recorded, the join is rare |
| **nomenclature and data plumbing** | the unglamorous blocker that stops multi-institution work before it starts |
| **uncertainty that is actually reported** | most models give a number and no interval |
| **incident learning under-analysed** | a large safety corpus that nobody has the time to mine |
| **prospective clinical validation** | **an agent cannot close this.** Trials need patients, ethics approval and years. |

> **The field's shortage is throughput of trustworthy checking, not novelty.**
> That is an unusually good match for a tireless governed agent, and an unusually
> dangerous one, because the checking is what stands between a plan and a person.

## 3. How this agent advances it

1. **Automate the retrospective QA sweep** — run every plan in an archive
   against its protocol constraints and surface the outliers. Cheap for an
   agent, impossible for a department.
2. **Measure variability** across planners, institutions and time, on
   retrospective cohorts. Nobody has the hours; an agent does.
3. **Benchmark dose-prediction and auto-segmentation models honestly**, per
   structure and per constraint, on external cohorts.
4. **Mine incident-learning corpora** for patterns, as a report to physicists.
5. **Standardise nomenclature** across datasets so multi-institution work
   becomes possible at all.
6. **Carry methods across subfields** — uncertainty estimation from imaging,
   diffusion priors from reconstruction, active learning from segmentation.
7. **Link delivered dose to outcome** on retrospective data, with the
   confounding stated rather than hidden.

The academic work this is measured against is the medical-physics AI
literature generally — dose prediction, Pareto surface navigation, beam
orientation optimisation, nomenclature standardisation, uncertainty estimation,
and AI-based QA for online adaptive radiotherapy on MR-linacs. The field's move
from single models toward compound agentic systems is the same shape as this
design. That literature is one anchor, not the boundary of the field.

## 4. The rule this agent exists to hold

> **It produces plan candidates and QA findings. A qualified medical physicist
> signs anything that touches a patient.**

This is the one of the six whose output has a direct physical path to a human
body. Every other agent can be wrong and cost time or money. This one can be
wrong and cost a person.

| | |
|---|---|
| compute a plan, a dose prediction, a QA verdict, an uncertainty | ✅ |
| rank candidates and explain the trade-off | ✅ |
| write into a treatment planning system, export a deliverable plan, mark a plan approved | ❌ **never** |
| operate on live patient data in the autonomous function | ❌ **never** — retrospective, de-identified or phantom only |

> **The autonomous function is bounded to data where being wrong is free.**
> "Unattended" and "waiting patient" must never appear in the same sentence in
> this system.

## 5. Self-model dimensions

| Dimension | Measured by | The trap |
|---|---|---|
| **dose prediction error** | **max** and mean difference vs the delivered plan | mean hides the hot spot, which is the clinical event |
| **DVH criterion pass rate** | fraction of clinical constraints met, per protocol, per structure | 9 of 10 can be unusable if the tenth is cord dose |
| **deliverability** | MU, segment count, leaf motion, machine constraints | a mathematically better plan the linac cannot deliver |
| **contour agreement** | DSC **and** surface distance, per structure | mean DSC across structures, which hides a small bad one |
| **uncertainty calibration** | stated confidence vs observed error | accuracy without calibration is unusable clinically |
| **nomenclature conformance** | fraction of structures resolvable to a standard | the boring dimension that gates everything else |
| **time to plan** | wall-clock for the adaptive loop | throughput on a warm cache |

## 6. What it may improve, and what it may not

| | |
|---|---|
| **may** | its prediction models, optimisation search, contour models, uncertainty estimators |
| **may** | which cohort, structure, protocol or subfield to work on next |
| **may not** | clinical constraint sets, protocols, or acceptance criteria |
| **may not** | anything about a plan's approval state |

> **Constraints are the clinic's.** An agent that could relax a constraint could
> make any plan pass, and the passing plan is the one delivered.

## 7. What an improvement must survive

1. **A retrospective cohort with the delivered plan as ground truth**, split by
   patient.
2. **Per-structure and per-constraint reporting** — no aggregate alone.
3. **Deliverability checked**, not assumed.
4. **An external institution's data** where a claim is about generality.
5. **A physicist's review of the failure cases** — the agent's job is to surface
   the worst cases and make them easy to look at.
6. **Calibration reported with accuracy.**

## 8. Autonomous work it may propose unasked

- QA sweeps over retrospective archives, flagging outliers and patterns
- benchmark dose prediction or segmentation on a retrospective cohort
- measure inter-planner or inter-institution variability
- standardise structure nomenclature across a dataset
- mine an incident-learning corpus for recurring failure modes
- ablate inputs and report what actually carries the signal
- estimate and calibrate uncertainty on held-out cases

**Not unasked, and not at any ceiling:** anything touching a live plan, a
treatment system, a patient record, or a clinical claim.

## 9. Tools and sub-agents

| Needs | For |
|---|---|
| GPU compute | model training, dose computation |
| a Monte Carlo dose engine | recomputation — physics that must not be approximated by the model under test |
| de-identified dataset access | retrospective cohorts |
| **GUI control** | planning systems are desktop applications; this is the second place the unnamed tool bites |
| a **domain verifier** | criteria are DVH lines, and judging them should be mechanical |

## 10. Budget shape

Model training is the expensive unit; QA sweeps and evaluation are cheap. A
night's grant covers **QA sweeps and retrospective evaluation** — which is also
the work whose value is highest and whose risk unattended is lowest.

## 11. The regulatory line

**Clinical deployment is not a permission the owner can grant alone.** An
outward gate covers acts that leave the machine; it does not confer regulatory
clearance, institutional review, or clinical validation. The agent refuses to
describe any output as clinically validated, cleared, or ready for use on
patients — including when the owner asks it to.

---

## The problem queue — in the order they must be solved

| # | problem | why it must come first | state |
|---|---|---|---|
| 1 | **3D volumetric dose** | nine beams on one axial plane cannot spare an organ sitting above or below the target, and a cord that abuts the PTV in 3D looks adjacent-or-absent depending on which slice was picked. Every other number on this page is provisional until this holds | open — scoped in [`medical-physics-3d-plan.md`](medical-physics-3d-plan.md) |
| 2 | **Achievability measured before the planner is blamed** | "the model achieved X" is unreadable without knowing what was reachable. An infeasible constraint set and a weak optimiser produce identical evidence. This is the one genuinely novel thing here | **done in 2D** — one case has a D99 ceiling of 62.6 against a 66.5 floor; must be re-measured in 3D before it is repeated |
| 3 | **The full DVH metric set** | D95/D99/D2, V95/V107, homogeneity and conformity indices, gEUD. This is the language the field reviews in; reporting anything else reads as an outsider and, worse, hides the trade being made | open |
| 4 | **Deliverability** | MLC and aperture constraints. A fluence map no linac can deliver is not a plan, and the gap between the two is where optimiser gains usually evaporate | open |
| 5 | **Protocol templates** (RTOG / NRG goal sheets) | the judge should encode a real clinical goal sheet rather than limits chosen by whoever wrote the benchmark | open |
| 6 | **Comparison against the delivered clinical plan** | per structure, differences named. A single score cannot say whether a plan is better or merely different | open |
| 7 | **Adaptive replanning and setup robustness** | last, because it presumes every one of the above | open |

> **2 must be re-measured, not carried.** The finding that one case is
> unreachable is a **2D** result. Nine coplanar beams are a far weaker delivery
> system than nine beams in 3D, so the ceiling will rise and the case may become
> feasible. Carrying that conclusion into a 3D planner would be exactly the
> error this agent keeps making: a property of the measurement reported as a
> property of the world.

## The four layers

| layer | this field's instance |
|---|---|
| **Principle** | A plan is a constraint set and a delivery system. Before an optimiser is called weak, what the geometry permits must be measured |
| **Digital twin** | The beamlet dose kernel — exponential depth attenuation along the ray with a lateral Gaussian for penumbra — fixed, shared between generation and scoring, and unreachable by the agent. Not a Monte Carlo engine, and the docs must never imply otherwise |
| **Benchmark** | OpenKBP head-and-neck plans, real contours, DVH criteria, with the achievability bound reported beside every verdict |
| **Solution** | A gradient-descent fluence optimiser with backtracking line search; `under_weight`, `oar_weight`, `hot_weight`, `cold_weight`, `step`, `iters`, `tuning_rounds` declared |

## At AGI and ASI

**On demand.** "Plan this patient." The answer is a plan, the achievability
bound for every constraint, and an explicit statement of which constraints are
in tension — plus a refusal when coverage was only obtainable by breaching an
organ limit.

**Autonomous.** It measures ceilings across a cohort and reports which published
"the model achieved X" claims were made against infeasible constraint sets. That
is a contribution the field cannot easily make about itself.

**How a person verifies.** A physicist reads the DVH, checks deliverability, and
re-runs the corner sweep that establishes the bound. **The plan is never
approved by the agent** — at every stage, including stage 4, a plan that treats
a patient carries a human signature. This is the one place in these seven where
the regulatory line does not move with the technology.

**How sub-agents verify.** A *geometry* verifier that recomputes structure
overlaps directly from the masks — the check that would have caught a wrong
array axis reporting parotid overlap as 21% when it was 56%; a *feasibility*
verifier that drives the declared space to the corner favouring the failing
metric; and a *guardrail* verifier that re-derives every organ constraint from
the DVH rather than from the optimiser's own objective.

**How a person is taught to check it.** Three wrong diagnoses preceded the real
one: impossible constraints, step-size collapse, nested targets — and the actual
cause was a NaN that silently disabled the optimiser because one mask guard was
missing. The teaching artifact is the habit of asking *what is the ceiling* before
theorising about the gap. A reader who takes only that away can refute most
auto-planning claims in the literature.

## When this field collapses — and what it becomes

**Not soon, and not by saturation.** Delivery hardware keeps changing, and each
change reopens the whole problem. What will collapse is the *human-verification
rate for routine plans* — a saturated field where standard cases are planned and
checked by machines and only the difficult ones reach a person. The signature
requirement survives the collapse; the review time does not.

**Candidate fission: biologically adaptive dose.** Dose that responds to
mid-course tumour response — where the target is not a fixed contour but a
trajectory — cannot be scored by a benchmark whose answer key is a static DVH on
a static geometry. Changing the benchmark to accommodate it would destroy what
makes it a benchmark. New field, new twin, new agent.
