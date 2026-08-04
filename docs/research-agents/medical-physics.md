# The medical physics agent — how to design it

**Status: design, 2026-08-04. Not built.** The common contract is in
[`README.md`](README.md).

## 1. Charter — what it is for

Radiotherapy physics: treatment planning, dose prediction, plan quality
assurance, contouring, and the automation around them.

The reference point the owner named is **Steve Jiang's group at UT Southwestern**
— the Medical Artificial Intelligence and Automation (MAIA) Lab, where Jiang is
Professor, Vice Chair for Digital Health and AI, and Chief of the Division of
Medical Physics and Engineering in Radiation Oncology. Their published problem
set maps almost one-to-one onto what this agent should be able to hold:

| MAIA line of work | What it becomes here |
|---|---|
| volumetric dose prediction | predict the achievable dose distribution from anatomy |
| Pareto surface navigation | explore the trade-off surface instead of returning one plan |
| beam orientation optimisation | a search problem with a physical cost |
| incorporating human and learned domain knowledge | the plan a physicist would accept, not the plan that scores |
| anatomical structure nomenclature standardisation | the unglamorous data problem that blocks everything else |
| uncertainty estimation | the dimension that decides whether any of it is usable |
| AI-based QA for online adaptive radiotherapy (MR-linac) | the highest-value and highest-risk target |

The lab's own framing — *clinical deployment of AI, from single models to
compound agentic systems* — is the same shape as this design, which is why it is
the right anchor rather than a courtesy citation.

## 2. The rule this agent exists to hold

> **It produces plan candidates and QA findings. A qualified medical physicist
> signs anything that touches a patient.**

This is the one of the six whose output has a direct physical path to a human
body. Every other agent in the set can be wrong and cost time or money. This one
can be wrong and cost a person.

So the design is deliberately asymmetric:

| | |
|---|---|
| it may **compute** a plan, a dose prediction, a QA verdict, an uncertainty | ✅ |
| it may **rank** candidates and explain the trade-off | ✅ |
| it may **write into a treatment planning system**, export a deliverable plan, or mark a plan approved | ❌ **never** |
| it may operate on **live patient data** in the autonomous function | ❌ **never** — retrospective, de-identified, or phantom only |

> **The autonomous function is bounded to data where being wrong is free.**
> Retrospective cohorts, public datasets and phantoms. Nothing the agent does
> unattended is on a patient who is waiting, because "unattended" and "waiting
> patient" must never appear in the same sentence in this system.

## 3. Self-model dimensions

| Dimension | Measured by | The trap |
|---|---|---|
| **dose prediction error** | mean and max dose difference vs the delivered clinical plan | mean error hides the hot spot, which is the thing that matters |
| **DVH criterion pass rate** | fraction of clinical constraints met, per protocol | a plan that meets 9 of 10 constraints may be unusable if the tenth is a cord dose |
| **deliverability** | does it survive the machine's constraints — MU, segment count, leaf motion | a mathematically better plan the linac cannot deliver |
| **contour agreement** | DSC *and* surface distance vs expert contours, per structure | mean DSC over structures — a small structure with a bad contour disappears in it |
| **uncertainty calibration** | does the stated confidence match observed error | a well-calibrated model that is confidently wrong 5% of the time is fine; an uncalibrated one is not usable at all |
| **nomenclature conformance** | fraction of structures resolvable to a standard name | the boring dimension that determines whether anything else can run at all |

> **Max, not mean, is the headline for dose.** In this domain the tail is the
> clinical event. An agent reporting mean dose error as its score has chosen the
> statistic that hides exactly the failure the field cares about, and its
> self-model is required to lead with the max.

## 4. What it may improve, and what it may not

| | |
|---|---|
| **may** | its prediction model, its optimisation search, its contour model, its uncertainty estimator |
| **may** | which cohort, which structure, which protocol to work on next |
| **may not** | the clinical constraint set, the protocol, or the acceptance criteria |
| **may not** | anything about a plan's approval state |

> **Constraints are the clinic's, not the agent's.** A DVH constraint is a
> clinical decision made by people accountable for it. An agent that could relax
> a constraint could make any plan pass, and the passing plan would be the one
> delivered.

## 5. What an improvement must survive

1. **A retrospective cohort with the delivered plan as ground truth**, split by
   patient, never by slice.
2. **Per-structure and per-constraint reporting** — no aggregate alone.
3. **Deliverability checked**, not assumed.
4. **A physicist's review of the failure cases**, not just the summary. The
   agent's job here is to surface the worst cases and make them easy to look at.
5. **Calibration reported** with the accuracy.

## 6. Autonomous work it may propose unasked

- benchmark a dose-prediction model on a retrospective cohort
- ablate inputs and report what actually carries the signal
- run QA checks over an archive and flag patterns
- standardise structure nomenclature across a dataset and report the mapping
- estimate and calibrate uncertainty on held-out cases

**Not unasked, and not at any ceiling:** anything touching a live plan, a
treatment system, a patient record, or a clinical claim.

## 7. Tools and sub-agents

| Needs | For |
|---|---|
| GPU compute | model training and dose computation |
| dataset access, de-identified | retrospective cohorts |
| a dose engine | recomputation — physics that must not be approximated by the model being tested |
| a **domain verifier** | the criteria are DVH lines; judging them is mechanical and should be |
| **GUI control** | planning systems are desktop applications, and this is the second place the unnamed tool bites |

## 8. Budget shape

Model training is the expensive unit; evaluation and QA sweeps are cheap. A
night's grant should cover **QA sweeps and retrospective evaluation**.

## 9. The regulatory line

**Clinical deployment is not a permission the owner can grant alone.** An
outward gate covers acts that leave the machine; it does not confer regulatory
clearance, institutional review, or clinical validation. The agent's limits line
says this in every report, and the agent refuses to describe any output as
clinically validated, cleared, or ready for use on patients — including when the
owner asks it to.
