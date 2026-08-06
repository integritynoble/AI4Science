# The pill camera agent — how to design it

| | |
|---|---|
| **corpus** | Kvasir-Capsule — 4,443 frames from 46 videos |
| **reference method** | **passes** |
| **the number that matters** | 0.614 → **0.624**, found by its own night loop |

> **The finding this page is built around.** The improvement is small on purpose, and that is why it is credible: paired across seeds, validated on seeds not used to select it. With 46 videos the spread between seeds is comparable to the effects people claim, so a large delta here is a symptom rather than a result.


**Status: built, on real data, and improved by its own night loop, 2026-08-05.**
The benchmark reads **Kvasir-Capsule** — 4,443 frames from 9 positive and 37
negative videos, split by video and verified patient-disjoint in code.

**Real frames first refuted this agent's premise, and then a search recovered
it — narrowly.** At the hand-picked 95th percentile the analytic haemoglobin
prior *lost* to plain green intensity, 0.598 against 0.614. The synthetic
version of this benchmark had claimed the opposite by construction: it gave each
patient a lognormal illumination gain precisely so a channel ratio would win.

The autonomous loop then found 99.5 — **+0.029 AUC across six held-out seeds,
paired, corrected p 0.044** — and refused it for having no mechanism. The
mechanism was supplied and *tested*: a lesion covers a small share of a frame
and the prior map is elevated only over it, so a quantile summary works better
the more it isolates the lesion's own pixels. The account predicts its own
limit, and the prediction holds — effect size runs 0.833 (q=99) → 0.863 (99.5)
→ 0.219 (99.8) → 0.058 (99.9), with the pure maximum no better than noise.

Adopted on that basis. At the adopted setting the prior beats intensity, 0.624
against 0.614 — a narrow margin on one split, resting on the six-seed result
rather than on that gap.

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

---

## The problem queue — in the order they must be solved

| # | problem | **solved when** | why it is placed here | state |
|---|---|---|---|---|
| 1 | **Video-disjoint splits** | `no frame from a test video appears in training, checked by video id` | consecutive capsule frames are near-duplicates. A random frame split puts the same anatomy on both sides and measures nothing; a patient-disjoint split is the minimum unit of independence | **done** — sampled per video, split by video |
| 2 | **Seed variance separated from improvement** | `the reported delta exceeds the measured seed spread, paired across seeds` | with 46 videos, the spread between seeds is comparable to the effect sizes being claimed. Without a paired comparison across seeds, every result is a coin flip with a narrative | **done** — the standing rule of this agent |
| 3 | **Pooled positives, honestly labelled** | `the pooling is stated in the corpus metadata and the reason is on the page` | the positive classes were pooled because each alone spans too few videos to split. That is a limitation of the corpus, and it is written into the benchmark rather than hidden in it | **done** — recorded in the bundle metadata |
| 4 | **Per-finding classes as data allows** | `each finding class spans enough videos to split, and is scored separately` | pooling costs clinical meaning: "an abnormality" is not a finding a report can carry. Unlocking this needs more videos, not a better model | blocked — corpus-bound |
| 5 | **Sequence, not a bag of frames** | `a sequence model beats the frame-pooled one on the same video-disjoint split` | a capsule study is a trajectory through the gut. Treating frames independently discards the strongest available signal, and it is the field's most common shortcut | open |
| 6 | **Localisation along the tract** | `a predicted location matches the ground-truth segment of the tract` | a finding without a location is not actionable; the clinician has to know where to go back to | open |
| 7 | **Miss rate at a fixed review time** | `miss rate is reported at a fixed review-time budget, not at unlimited time` | the real clinical quantity. A reader has minutes, not hours, and a model that improves accuracy while lengthening review has not helped | open |

> **"Solved when" is the entry fee.** A problem with no measurement that would
> settle it is a research *interest*, and interests belong in the charter. The
> ladder is the part this agent can be wrong about in public.
>
> **A rung is closed by the registry, not by the agent.** "Solved" means a
> benchmark has a published solution that meets it, runnable by anyone. The
> agent may propose that a rung is closed; the closing is an artifact.
>
> The failure this is built against is **an agent that solves what it can**.
> Given a free hand the cheapest defensible night is the easy rung, and a year
> of easy rungs looks like a year of progress.

## The four layers

| layer | this field's instance |
|---|---|
| **Principle** | Seed variance is not an improvement, and a video is not a bag of frames |
| **Digital twin** | The study model — frames sampled per video rather than per archive, so class balance reflects videos and not whichever tar entries came first. A global cap silently makes the corpus a sample of the first few videos |
| **Benchmark** | Kvasir-Capsule, 4,443 frames from 46 videos, video-disjoint split, pooled vascular positives declared in the metadata |
| **Solution** | A percentile-pooled frame classifier with `percentile` declared — improved once by the agent's own night loop, 0.614 → 0.624, and signed |

---

## Scope, and the experts who set it

**Current scope.** Frame and sequence classification on capsule endoscopy video, split by **video**, with per-video results reported.

**Out of scope:** any use on a person, and any device modification intended for clinical use.

**Scope is set by experts in the field — not by this agent, and not by the owner
alone.** It is expected to move: a scope change is signed like an adoption, with
who changed it, on what evidence, and what it invalidates. The mechanism, the
guards against a panel that only ever widens, and the recusal rule are in
[`lifecycle.md`](lifecycle.md).

| expert role | what they decide here |
|---|---|
| **a gastroenterologist who reads capsule studies** | what a finding must look like to be actionable, and what miss rate at what review time is acceptable |
| **a capsule device engineer** | illumination, frame rate and what the hardware could capture instead — the co-design questions |
| **a clinical data steward** | which studies may be used, and what pooling of findings is defensible |
| **a biomedical safety engineer** | what the bench rig may do, and the ingestion-safety boundary |

> **They may also retire the benchmark.** The agent may never change what judges
> it; the field's experts may, and when they do it re-bases the history rather
> than improving on it. Every comparison made before a revision stops being
> comparable, and the record says so.

**No individual is named in this repository.** These are roles.

## The group — who does what, and which of them have bodies

This agent is not one model. It is a **group** with three kinds of member,
defined by what their acts reach: **reasoning** members touch a file,
**judging** members produce a verdict and never act, and **embodied** members
touch the world and cannot be undone. Outside the group it is one agent, with
one workspace, one task list, one ceiling and one verdict — the owner deals with
a thing, not a committee. The shared machinery is in
[`lifecycle.md`](lifecycle.md).

| member | kind | acts on | its refusal |
|---|---|---|---|
| planner | reasoning | the seed plan | refuses a split that is not by video |
| classifier runner | reasoning | the GPU, the workspace files | refuses when Kvasir-Capsule is absent, **naming the fetch command** |
| variance verifier | judging | the seed spread | refuses a delta smaller than the spread it measured |
| domain verifier | judging | the benchmark | refuses a pooled mean presented without per-video results |
| teacher | judging | the owner's own check | refuses to report an improvement without the seed spread beside it |
| **bench GI rig** | **embodied** | a physical phantom tract | refuses to be used on a person |
| **device handling robot** | **embodied** | capsule hardware | refuses to modify a device intended for clinical use |

**Why a body, here.** The bench rig makes this a hardware field again. Frame classification on a fixed corpus is bounded; localisation, illumination and frame rate are co-design questions, and co-design needs something to build.

**Three rules hold for every embodied row above**, and they are the reason the
bench is listed separately rather than as another tool:

1. **An embodied act is irreversible and is treated so by default.** It needs a
   grant naming that act, every time. A standing night grant does not cover it.
2. **An embodied sub-agent may not verify its own act.** The verifier judges
   from evidence the body produced, never from the body's report of what it did.
3. **The group's ceiling is the lowest of its members', not the agent's.** The
   ceiling belongs to the act, and the act with a body sets it.

**Nothing embodied is built.** These rows are design; what exists today is the
reasoning and judging members. See [`lifecycle.md`](lifecycle.md).

> **What the bodies do not fix.** More videos is the binding constraint on per-finding classes, and a bench rig produces phantom footage, not patients.

## At AGI and ASI

**On demand.** "Read this study and tell me where to look." A ranked set of
timestamps with a location and a confidence, and an explicit statement of what
fraction of the study was uninterpretable — bubbles, debris, motion.

**Autonomous.** It re-evaluates published capsule classifiers under
video-disjoint splits and reports which ones were reading duplicate frames.

**How a person verifies.** Ask whether any frame from a test video appeared in
training, in any form, including as a near-duplicate neighbour. Then ask for the
per-video result: 46 videos means the mean is fragile, and one video can carry
the whole difference.

**How sub-agents verify.** A *split* verifier checking video identity across the
partition, a *variance* verifier re-running across seeds to establish the spread
before any delta is believed, and a *sampling* verifier confirming frames were
drawn per video rather than per archive.

**How a person is taught to check it.** This agent's own night loop produced a
real improvement — 0.614 → 0.624 — and the thing worth teaching is why that
number is credible: it was paired across seeds, validated on seeds not used to
select it, and it is small. A reader who learns to distrust large deltas on
small corpora has learned the most useful thing this field has to offer.

## When this field collapses — and what it becomes

**By indifference in one direction and saturation in the other.** Frame
classification on capsule video is a narrow problem that will be finished; what
it feeds — whether the study changes management — is a clinical question that
this benchmark never asked.

**Candidate fission: the capsule that acts.** A device that samples, marks, or
delivers at a located finding is not scored by any frame-classification metric —
the answer key would have to describe an intervention and its outcome, which
this benchmark cannot express. New twin (a device with actuation), new benchmark
(outcome, not label), new agent.

**Retired from research, not from service.** A reader that shortens review time is worth the same after the frontier closes.
