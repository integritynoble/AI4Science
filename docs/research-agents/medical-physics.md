# The medical physics agent — how to design it

**Status: built and running on real data, 2026-08-04.** The benchmark reads
**OpenKBP** — eight real head-and-neck cases with CT, contours, and the dose the
patient was actually treated with. The clinical dose is the answer key and never
enters the sandbox. The protocol is the real one: D99 to three target volumes,
brainstem 54 Gy, cord 45, parotid mean 26, mandible 70.

**Its reference method fails, and the failure is honest.** A coplanar 2D planner
reaches every target and tracks the delivered plan closely — PTV70 D99 = **70.0
Gy against the clinical 70.02** — and cannot spare a spinal cord that abuts the
target: **51.8 Gy against a 45 Gy limit**, with a hot spot of 190 against 80.5.
Sparing that cord takes full 3D modulation. Raising the penalties traded cord
against hot spot and cleared neither, so the tuning stopped rather than
continuing until something passed.

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

The reference point the owner named is **Steve Jiang's MAIA Lab at UT
Southwestern** — dose prediction, Pareto surface navigation, beam orientation
optimisation, nomenclature standardisation, uncertainty estimation, and AI-based
QA for online adaptive radiotherapy on MR-linacs. Their framing of *clinical
deployment from single models to compound agentic systems* is the same shape as
this design. It is one anchor in the field, not the boundary of it.

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
