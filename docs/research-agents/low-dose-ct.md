# The low-dose CT agent — how to design it

**Status: design, 2026-08-04. Not built.** The common contract is in
[`README.md`](README.md).

## 1. The field

Getting a diagnostic CT image from fewer photons — and the whole apparatus of
deciding whether you got one.

| Subfield | What is at stake |
|---|---|
| **low-dose reconstruction** | denoising and restoration at reduced tube current |
| **sparse-view** | fewer projections, structured streak artefacts |
| **limited-angle** | missing wedge, a genuinely ill-posed null space |
| **interior / region-of-interest** | truncated data |
| **photon-counting CT** | a new detector class changing the noise model entirely |
| **dual- and multi-energy** | material decomposition, and its own noise amplification |
| **metal artefact reduction** | the artefact that survives every generation of method |
| **motion and 4-D CT** | cardiac and respiratory, where the object moves during acquisition |
| **cone-beam CT** | on-board imaging, scatter-dominated, the RT and dental workhorse |
| **dose estimation and management** | CTDIvol, SSDE, organ dose — what "low dose" even means |
| **task-based image quality** | detectability, observer models, the ICRU/AAPM tradition |
| **reader studies and clinical validation** | the only evidence that any of it helped |

**Why this is a separate agent from computational imaging.** Not the
mathematics — that is shared, and the transfer table in
[`computational-imaging.md`](computational-imaging.md) §3 is the same table. It
is separate because low-dose CT has a **patient, a regulator, and a metric that
disagrees with the one everyone optimises**. Those three things need their own
charter.

## 2. What this field is short of

| Shortage | How bad |
|---|---|
| **a metric that matches the purpose** | the field optimises PSNR/SSIM; radiology cares about lesion detectability. **These two disagree in a specific and dangerous direction** — see §4. |
| **paired data across vendors** | most work is one vendor, often one public dataset; generalisation across scanners is largely unmeasured |
| **reproduction** | published gains rarely re-derived; code often unrunnable |
| **comparability** | different doses, different reconstruction kernels, different slice thicknesses, all called "low-dose" |
| **dose equivalence** | "50% dose" is not a defined quantity across scanners without a framework |
| **reader studies** | the evidence that matters, and there are very few. **An agent cannot close this** — it needs radiologists' time. |
| **photon-counting method transfer** | a new detector class where most existing methods have not been re-evaluated at all |

> **The field's central problem is measurement, not method.** More methods are
> not the shortage. A field where "better" is measured by a proxy that can be
> improved by destroying the diagnostic content has a measurement problem, and
> the most valuable thing an agent can do is make the honest measurement cheap
> and routine.

## 3. How this agent advances it

1. **Reproduce the top methods under one protocol** — same dose definition, same
   split, same kernel, same hardware — and publish the table with what failed to
   reproduce. This alone would be a service to the field.
2. **Report task-based detectability beside fidelity, always**, using model
   observers so that it costs an agent's time rather than a radiologist's.
3. **Cross-vendor generalisation as a standing measurement**, not a paper.
4. **Re-evaluate the field's methods on photon-counting data**, where the noise
   model has changed and most prior work has simply not been retried.
5. **Carry methods in from neighbouring subfields** using the shared transfer
   table — self-supervised denoising, diffusion priors, INRs for sparse-view.
6. **Keep a dose-equivalence framework applied**, so numbers from two scanners
   can be compared at all.

There is a strong existing seed for this on the owner's machine —
[`integritynoble/low_dose_CT`](https://github.com/integritynoble/low_dose_CT),
whose workstreams already build a multi-vendor paired dataset (WS-1), a formal
signal-equivalence framework (WS-2), a reference method **designed with a
swappable denoiser** (WS-3), a permanent competition (WS-4) and a foundation
model follow-on (WS-6). That makes this the one of the six whose improvement
substrate already exists rather than needing to be built. It is a seed, not the
scope: the field is the scope.

## 4. The rule this agent exists to hold

> **A fidelity gain with flat detectability is a failure, not a mixed result.**

A denoiser raises PSNR most easily by smoothing, and the first thing smoothing
removes is the low-contrast lesion the scan was ordered for. PSNR rises; the
scan becomes useless. This is not a hypothetical failure mode — it is the
predictable optimum of the metric the field reports.

So both numbers appear together or neither appears, and the agent is forbidden
to headline fidelity alone.

## 5. Self-model dimensions

| Dimension | Measured by | Not to be confused with |
|---|---|---|
| **task detectability** | model-observer detectability (e.g. CHO/NPWE) on inserted low-contrast signals | image quality by eye |
| **reconstruction fidelity** | PSNR / SSIM against the paired full-dose scan, per vendor | detectability |
| **baseline reproduction** | reproducing a published baseline to a stated tolerance | agreeing with the published number |
| **dose-equivalence calibration** | error between predicted and measured equivalent dose | a dose-reduction factor quoted with no framework |
| **cross-vendor generalisation** | fidelity and detectability on a vendor held out entirely | the average across vendors |
| **artefact-specific behaviour** | metal, motion, truncation cases scored separately | overall mean |
| **runtime** | seconds per volume on a stated GPU | throughput on a warm cached run |

## 6. What it may improve, and what it may not

| | |
|---|---|
| **may** | the denoiser/reconstruction module, the prior, unrolling depth, training schedule, augmentation, ensembling |
| **may** | which subfield, which scanner, which artefact class to attack next |
| **may not** | the held-out split, the dose-equivalence framework, the observer model, the leaderboard, or the evaluation code |

> **It competes on a leaderboard it must not be able to touch.** This is the
> sharpest instance of the general rule, because the scorer is a public artefact
> with a real incentive attached. The held-out set lives outside `W_name`; the
> leaderboard is written by a submission the owner grants at `OWN`. There is no
> write path, and no policy is relied on to create one.

## 7. What an improvement must survive

1. **Reproduce first** — comparisons are against baselines this agent reproduced
   in a container on this machine, never against a number from a paper.
2. **Split by patient and held out by vendor.** Slice-level splits leak:
   adjacent slices are nearly the same image.
3. **The fixed seed set, all of it**, mean and interval.
4. **Both metrics**, fidelity and detectability, together.
5. **Artefact classes reported separately** — a method that helps everywhere
   except metal is a useful method described honestly.
6. **A mechanism**, not just a number.

## 8. Autonomous work it may propose unasked

- reproduce a newly published method and add it to the common table
- run the whole comparison table on a vendor or dose level nobody has used
- re-evaluate existing methods on photon-counting data
- ablate a component and report the effect on **both** metrics
- carry a method in from a neighbouring subfield and evaluate it here
- publish the negative result when it does not carry

**Not unasked:** submitting to a leaderboard, posting a preprint, mailing a
collaborator, touching a dataset release, or starting a training run beyond the
standing grant.

## 9. Tools and sub-agents

| Needs | For |
|---|---|
| GPU compute | training and reconstruction |
| `docker` | reproducibility here *is* a container, so this is not optional |
| dataset access | paired multi-vendor corpora under their terms |
| an observer-model implementation | detectability, computed rather than eyeballed |
| a **domain verifier** | a reconstruction claim needs metric, split and both numbers — not prose |

## 10. Budget shape

| Unit | Rough cost | Buys |
|---|---|---|
| one ablation or evaluation | a few GPU-hours | one row of a table |
| one baseline reproduction | a day | the right to compare against it at all |
| one full training | days | one candidate method |

A night's standing grant should cover **evaluations, reproductions and
ablations, not full trainings.** A training run is the unit where an unattended
mistake becomes expensive rather than merely wrong, so the owner starts it.

## 11. The clinical line

**A reconstruction quality gain is not a diagnostic claim.** Non-inferiority for
diagnosis requires a reader study with radiologists, and nothing in this agent's
reach produces one — model observers are a proxy for that study, not a
substitute. Every output carries this in its limits line, and the agent refuses
to write "diagnostically equivalent" about a computed result however the
question is phrased.
