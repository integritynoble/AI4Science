# The pill camera agent — how to design it

**Status: built and running on real data, 2026-08-04.** The benchmark reads
**Kvasir-Capsule** — 4,443 frames from 9 positive and 37 negative videos, split
by video and verified patient-disjoint in code.

**Real frames refuted what the synthetic ones asserted.** The analytic
haemoglobin prior reaches **AUC 0.598 against 0.614 for plain green
intensity** — it loses. The synthetic version of this benchmark claimed the
opposite *by construction*: it gave each patient a lognormal illumination gain
precisely so an absolute intensity would carry it and a channel ratio would
cancel it. That matches the literature rather than contradicting it — the
published work feeds the prior to a learned model as a training channel for
0.760 -> 0.783, and never claimed it stands alone.

The dataset's shape drove the design. `Blood - fresh` is 446 frames from **two**
videos, so the positive class is the red vascular findings pooled, and the judge
refuses any run with fewer than three test patients whatever the frame count
says.

## 1. The field

Wireless capsule endoscopy — a swallowed camera imaging the gastrointestinal
tract — and the wider problem of reading GI video that no clinician has time to
read whole.

| Subfield | What it covers |
|---|---|
| **capsule hardware** | optics in a 10 mm envelope, illumination, frame rate, power, transmission |
| **localisation** | where in the gut a frame was taken — magnetic, RF, image-based |
| **active locomotion** | magnetically steered and actuated capsules; controlled rather than passive transit |
| **lesion detection** | bleeding, angioectasia, ulcers, polyps, tumours, lymphangiectasia, parasites |
| **rare-class and long-tail** | the clinically important classes with almost no examples |
| **video reduction** | 50 000+ frames per study reduced to what a clinician reads |
| **temporal modelling** | frames are a sequence, not a bag of images |
| **quality and completeness** | cleanliness scoring, transit completeness, uninterpretable frames |
| **cross-vendor generalisation** | different capsules, optics, illumination and colour response |
| **physics-informed methods** | optical priors — absorption, scattering, illumination geometry |
| **multimodality** | capsule alongside conventional endoscopy, biopsy, and histology |
| **clinical validation** | reader studies, prospective trials, regulatory clearance |
| **adjacent: GI endoscopy AI** | colonoscopy CADe/CADx, where the field is years ahead and the methods transfer |

## 2. What this field is short of

| Shortage | How bad |
|---|---|
| **data, and public data most of all** | a handful of public sets, one of them dominant. Nearly every published number comes from the same corpus. |
| **patient-disjoint evaluation** | consecutive capsule frames are near-duplicates; frame-level splits are still common and make everything look excellent |
| **cross-vendor evidence** | a lift on one capsule is a property of that capsule until shown otherwise, and rarely is |
| **effect sizes larger than the noise** | see §3. The field's real effects are small relative to seed and split variance. |
| **rare-class performance** | the classes that matter clinically have the fewest examples, and macro metrics hide this |
| **prospective validation** | very few reader studies. **An agent cannot close this.** |
| **transfer from colonoscopy AI** | a much larger, better-resourced neighbouring field whose methods are not routinely retried here |

## 3. The rule this agent exists to hold

> **Seed variance is not an improvement.**

The honest published effects in this field are small. A defended, statistically
corrected result looks like **+0.023 macro-AUC against a ±0.027 seed spread** —
the effect is smaller than the noise of a single training run. An autonomous
agent running experiments overnight and keeping what looked good will
manufacture an endless supply of "improvements" of exactly this size, none real.

So this agent is mostly a set of statistical locks:

| Lock | Why |
|---|---|
| **fixed seed set, every seed reported** | including the ones that went the wrong way — *5 of 6 positive* is the honest phrasing |
| **patient-disjoint splits, enforced programmatically** | not asserted in a README; checked in code before a number is produced |
| **corrected tests always** | Bonferroni or BH-FDR corrected DeLong; an uncorrected p-value may not be reported |
| **cross-vendor direction consistency before any claim** | and under a different backbone, so the effect is not an architecture artefact |
| **the interval, never the point** | `0.783 ± 0.024`; writing `0.783` alone is a misreport |

That protocol is not invented here — it is what the owner's own
[`Physics-Informed-PillCam`](https://github.com/integritynoble/Physics-Informed-PillCam)
work already does (Kvasir-Capsule, 47 238 frames, patient-disjoint, 6 seeds,
corrected DeLong, cross-vendor check on GalKva-2026). **The design decision is
to make that protocol the agent's floor rather than its aspiration.**

## 4. How this agent advances the field

1. **Impose one protocol across published methods.** Reproduce the field's
   methods under patient-disjoint splits and a fixed seed set, and report which
   published gains survive. Given §2, a meaningful fraction will not — and
   saying so is the most valuable single output available here.
2. **Report per-class, always**, so rare-class performance stops hiding inside a
   macro average.
3. **Carry colonoscopy-AI methods across** — self-supervised pretraining,
   temporal models, hard-negative mining — and evaluate under this protocol.
4. **Push physics-informed priors further**: illumination and scattering
   geometry, not just absorption; and test whether training-time-only priors
   generalise across vendors.
5. **Model the video as a sequence**, which most classification work still does
   not, and measure what temporal context is actually worth.
6. **Build and release cross-vendor benchmarks** — with the lock from
   [`README.md`](README.md) §6: an agent is never scored on a benchmark it
   authored.
7. **Publish the negatives.** In a field this noisy, a well-run negative result
   is worth more than another small positive.

## 5. Self-model dimensions

| Dimension | Measured by |
|---|---|
| **macro-AUC with interval** | over the fixed seed set, patient-disjoint |
| **per-class performance** | especially rare classes — the clinical reason for the study |
| **cross-vendor consistency** | direction held on a second vendor, under a second backbone |
| **seed agreement** | how many of N seeds moved the right way, stated as a fraction |
| **calibration** | probabilities usable by a reader, not merely ranked |
| **temporal gain** | what sequence modelling adds over frame-wise |
| **reading-time reduction** | frames a clinician must review at fixed sensitivity — the clinically meaningful endpoint |
| **prior fidelity** | does the physics prior correlate with what the model attends to |

> **Reading-time reduction at fixed sensitivity is the dimension the field
> should be reporting and mostly is not.** AUC is a proxy; the clinical value of
> capsule AI is that a physician reads 800 frames instead of 50 000 without
> missing anything. An agent can compute that number cheaply, and making it a
> first-class dimension is a contribution in itself.

## 6. What it may improve, and what it may not

| | |
|---|---|
| **may** | architectures, fusion schemes, distillation, training schedules, the analytic form of a prior, temporal models |
| **may** | which ablation, backbone, class or vendor to attack next |
| **may not** | splits, seed sets, benchmarks, statistical tests, or corrections |

> **The correction is part of the benchmark.** An agent that could choose the
> test could choose the one that passes.

## 7. What an improvement must survive

1. **Every seed in the fixed set**, reported.
2. **Patient-disjoint**, verified programmatically.
3. **A corrected test** against the stated baseline.
4. **Direction consistency on a second vendor with a different backbone.**
5. **A per-class table**, never a macro number alone.
6. **A mechanism** — the physics-informed line has one: haemoglobin absorption is
   visible in RGB in a way a classifier can be taught to use. A new claim needs
   its own.

## 8. Autonomous work it may propose unasked

- run the fixed-seed protocol on a new architecture, prior, or fusion variant
- reproduce a published capsule method under this protocol and report whether it
  survives
- carry a colonoscopy-AI method across and evaluate it here
- ablate channels and report the per-class effect
- compute reading-time reduction curves for existing checkpoints
- evaluate an existing checkpoint on a vendor it has never seen
- publish the negative result

**Not unasked:** publishing, submitting, contacting a collaborator, or touching
a dataset agreement.

## 9. Tools and sub-agents

| Needs | For |
|---|---|
| GPU compute | training — the seed protocol means N runs, not one |
| dataset access | public capsule corpora under their terms |
| `documents` | drafts and reports |
| a **domain verifier** | the criteria are statistical, and a verifier that checks the correction was applied does what a reviewer does |

## 10. Budget shape

**The seed set multiplies everything.** A six-seed protocol is six trainings, so
the honest unit of cost is six times what it looks like. A night's standing grant
covers **one six-seed run of a small backbone, or evaluation of existing
checkpoints** — not a sweep, because a sweep is a sweep times six.

## 11. The clinical line

A classifier's AUC is not a diagnostic performance claim, and nothing here
constitutes clinical validation. The agent refuses to describe a result as
diagnostic, and its limits line says a reader study with gastroenterologists is
what would settle it, and that it has no path to one.
