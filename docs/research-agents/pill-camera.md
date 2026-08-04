# The pill camera agent — how to design it

**Status: design, 2026-08-04. Not built.** The common contract is in
[`README.md`](README.md).

## 1. Charter — what it is for

Wireless capsule endoscopy: reading the video no clinician has time to read
whole, with physics used as a prior rather than as decoration.

The seed corpus is the owner's own, and it is unusually specific about method —
which is what makes this agent designable rather than aspirational:

**[`integritynoble/Physics-Informed-PillCam`](https://github.com/integritynoble/Physics-Informed-PillCam)**
— *Training-Time Optical Priors for Wireless Capsule Endoscopy Classification:
Hemoglobin-Aware Input Fusion with Cross-Vendor Evaluation* (Yang et al., 2026,
submitted to *Medical Image Analysis*):

| | |
|---|---|
| the idea | a Monte-Carlo-inspired hemoglobin prior `P_blood`, computed analytically from RGB, fed alongside the image at **training time only**; inference runs on plain 3-channel RGB |
| the result | Kvasir-Capsule, 47 238 frames, patient-disjoint: macro-AUC **0.760 ± 0.027 → 0.783 ± 0.024**, 5 of 6 seeds positive; three-stream variant **0.804 ± 0.023** |
| the check | direction-consistent under ConvNeXt-Tiny on the **GalKva-2026** cross-vendor benchmark, significant under Bonferroni- and BH-FDR-corrected DeLong |

**`integritynoble/GI_Multi_Task`** carries the multi-task line (Monte-Carlo-guided
bleeding detection plus rare-anomaly classification) and the five-year flagship,
PillCam-SPECTRA.

## 2. The rule this agent exists to hold

> **Seed variance is not an improvement.**

Look at the seed corpus's own numbers: a real, defended, statistically corrected
improvement is **+0.023 macro-AUC against a ±0.027 seed spread**. The effect is
smaller than the noise of a single run. An autonomous agent running experiments
overnight and keeping what looked good will manufacture an endless supply of
improvements of exactly this size, none of them real.

So this agent's design is mostly a set of statistical locks:

| Lock | Why |
|---|---|
| **the seed set is fixed in advance and every seed is reported** | including the one that went the wrong way — 5/6 is the honest way to say it, not 5/5 |
| **patient-disjoint splits, enforced mechanically** | consecutive capsule frames are near-duplicates; a frame-level split makes any model look excellent |
| **corrected tests, always** | the repo already uses Bonferroni and BH-FDR-corrected DeLong; the agent may not report an uncorrected p-value |
| **cross-vendor direction consistency before any claim** | a lift on one vendor's capsule is a property of that vendor until shown otherwise |
| **the interval, never the point** | the headline is `0.783 ± 0.024`, and an agent that writes `0.783` alone has misreported it |

## 3. Self-model dimensions

| Dimension | Measured by |
|---|---|
| **macro-AUC with interval** | over the fixed seed set, on the patient-disjoint split |
| **per-class lift** | especially the rare classes — the seed work's strongest effect was on *Lymphangiectasia*, which a macro average nearly hides |
| **cross-vendor consistency** | does the direction hold on GalKva-2026 under a different backbone |
| **seed agreement** | how many of N seeds moved the right way, stated as a fraction |
| **calibration** | probabilities usable by a downstream reader, not just ranked |
| **prior fidelity** | does `P_blood` correlate with what the model attends to (Grad-CAM / prior overlap) — the repo already computes this |

> **Per-class is the dimension that matters clinically.** Capsule pathology is
> heavily imbalanced and the rare classes are the reason for the study. An agent
> optimising macro-AUC can win by getting better at the common classes, which is
> the opposite of useful.

## 4. What it may improve, and what it may not

| | |
|---|---|
| **may** | the architecture, the fusion scheme, the distillation variant, the training schedule, the prior's analytic form |
| **may** | which ablation, which backbone, which class to attack next |
| **may not** | the split, the seed set, the benchmark, the statistical test, or the correction |

> **The correction is part of the benchmark.** An agent that could choose the
> test could choose the one that passes. Bonferroni and BH-FDR are fixed the way
> the held-out set is fixed.

## 5. What an improvement must survive

1. **Every seed in the fixed set**, reported.
2. **Patient-disjoint**, verified programmatically rather than assumed.
3. **A corrected DeLong test** against the stated baseline.
4. **Direction consistency on the cross-vendor benchmark**, with a different
   backbone.
5. **A per-class table**, not a macro number alone.
6. **A mechanism** — the seed work's is optical: hemoglobin absorption shows up
   in RGB in a way a classifier can be taught to use. A new claim needs its own.

## 6. Autonomous work it may propose unasked

- run the fixed-seed protocol on a new architecture or fusion variant
- ablate channels and report the per-class effect
- evaluate an existing checkpoint on the cross-vendor benchmark
- compute prior/attention overlap for a trained model
- reproduce a published capsule-endoscopy baseline under this protocol

**Not unasked:** publishing, submitting to a venue, contacting a collaborator, or
touching a dataset agreement.

## 7. Tools and sub-agents

| Needs | For |
|---|---|
| GPU compute | training; the seed protocol means N runs, not one |
| dataset access | Kvasir-Capsule and GalKva-2026 under their terms |
| `documents` | the paper drafts and reports |
| a **domain verifier** | the criteria are statistical, and a verifier that checks the correction was applied is doing the job a reviewer does |

## 8. Budget shape

**The seed set multiplies everything.** A six-seed protocol is six trainings, so
the honest unit of cost here is six times what it looks like. A night's standing
grant covers **one six-seed run of a small backbone, or evaluation of existing
checkpoints** — not a sweep, because a sweep is a sweep times six.

## 9. The clinical line

A classifier's AUC is not a diagnostic performance claim, and nothing here
constitutes clinical validation. The agent refuses to describe any result as
diagnostic, and its limits line says that a reader study with gastroenterologists
is the thing that would, and that it has no path to one.
