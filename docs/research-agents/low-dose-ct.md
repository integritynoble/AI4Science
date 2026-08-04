# The low-dose CT agent — how to design it

**Status: design, 2026-08-04. Not built.** The common contract is in
[`README.md`](README.md); this file is only what is specific to this agent.

## 1. Charter — what it is for

Reconstruction at reduced dose, and the apparatus around it: a vendor-agnostic
benchmark, a dose-equivalence framework, an improvable reference method, and a
permanent competition.

The seed corpus is already written and is the strongest of the six —
[`integritynoble/low_dose_CT`](https://github.com/integritynoble/low_dose_CT),
organised as seven workstreams whose READMEs *are* the plan:

| Workstream | What the agent inherits |
|---|---|
| **WS-1** dataset | a multi-vendor paired-dose corpus and its loader (`pwm_ldct_loader`), the schema, and the annotation plan |
| **WS-2** framework | `pwm_dose_equivalence` — the formal signal-equivalence theory the whole comparison rests on |
| **WS-3** reference method | an open reference reconstruction built for **decomposable improvability**: the denoiser is a swappable module |
| **WS-4** leaderboard | the permanent competition, and the annual review |
| **WS-6** foundation model | the follow-on that swaps WS-3's denoiser for a foundation-model variant |

> **This agent exists because WS-3 was designed to be improved.** A pipeline
> whose denoiser is a named, swappable module is exactly the substrate an
> autonomous improvement loop needs — and the reason this is the first of the
> six worth building is that the substrate already exists rather than having to
> be invented.

## 2. Self-model dimensions

| Dimension | Measured by | Not to be confused with |
|---|---|---|
| **reconstruction fidelity** | PSNR / SSIM against the paired full-dose scan, per vendor | image quality as judged by looking at it |
| **baseline reproduction** | can it reproduce a published baseline to **± 0.5 dB** — the tolerance WS-1/WS-3 already set | agreeing with the published number |
| **dose-equivalence calibration** | error between predicted and measured equivalent dose, via `pwm_dose_equivalence` | a dose reduction factor quoted without a framework |
| **cross-vendor generalisation** | fidelity on a vendor held out of training entirely | average across all vendors |
| **task fidelity** | detectability of the lesion class, not just pixel error | PSNR |
| **runtime** | seconds per volume on the stated GPU | throughput on a cached warm run |

> **The dimension that keeps this honest is task fidelity.** A denoiser can
> raise PSNR by smoothing away the low-contrast lesion that was the reason for
> the scan. PSNR goes up; the scan becomes useless. So a fidelity gain with a
> flat or falling detectability number is **reported as a failure**, not as a
> mixed result.

## 3. What it may improve, and what it may not

| | |
|---|---|
| **may** | the WS-3 denoiser module, the prior, the unrolling depth, training schedule, augmentation, ensemble |
| **may** | which experiment to run next, and what to abandon |
| **may not** | the WS-1 held-out split, the WS-2 equivalence framework, the WS-4 leaderboard, or the evaluation code |

> **It competes on a leaderboard it must not be able to touch.** This is the
> sharpest instance of the general rule, because here the scorer is a real,
> public artefact with a real incentive attached. The held-out set lives outside
> `W_name` and the leaderboard is written by a submission the owner grants at
> `OWN` — the agent never has a write path to either, and no policy is relied on
> to stop it.

## 4. What an improvement must survive

1. **Reproduce first.** No comparison is made against a number from a paper —
   only against a baseline this agent reproduced to ± 0.5 dB, in Docker, on this
   machine. The WS-1 pipeline is Docker-reproducible for exactly this reason.
2. **Held out by vendor, not by slice.** Slice-level splits leak: adjacent
   slices of one patient are nearly the same image. The split is by patient, and
   generalisation is judged on a *vendor* never trained on.
3. **The fixed seed set, all of it**, mean and interval.
4. **Both metrics, always.** Fidelity and detectability are reported together or
   not at all.
5. **A mechanism.** "The new denoiser is better" is a lead. "It is better
   because the prior now models the correlated noise the reconstruction
   introduces at this dose" is a finding.

## 5. Autonomous work it may propose unasked

- reproduce a newly published baseline and add it to the comparison table
- ablate one component of WS-3 and report the effect
- sweep a hyperparameter within a declared budget
- test an existing checkpoint on a vendor it has never seen
- draft a candidate WS-6 denoiser swap and evaluate it on the same footing

**Not unasked:** submitting to the leaderboard, posting a preprint, mailing a
collaborator, touching the dataset release, or starting a training run whose
budget exceeds the standing grant.

## 6. Tools and sub-agents

| Needs | For |
|---|---|
| `shell`, `editor` | the ordinary loop |
| GPU compute | training and reconstruction — declared at `CAP`, refused by name when absent |
| `docker` | the reproducibility guarantee is a container, so this is not optional |
| `pwm_ldct_loader` | the dataset contract |
| a **domain verifier** sub-agent | judging a reconstruction claim needs the metric and the split, not prose |

## 7. Budget shape

| Unit | Rough cost | Buys |
|---|---|---|
| one ablation run | a few GPU-hours | one row in a table |
| one baseline reproduction | a day | the right to compare against it at all |
| one full training | days | one candidate denoiser |

A night's standing grant should cover **ablations and evaluations, not full
trainings.** A training run is a thing the owner starts, because it is the unit
where an unattended mistake becomes expensive rather than merely wrong.

## 8. The clinical line

**A reconstruction quality gain is not a diagnostic claim.** Non-inferiority for
diagnosis requires a reader study with radiologists, and nothing in this agent's
reach produces one. Every output carries that boundary in its limits line, and
the agent refuses to write "diagnostically equivalent" about a PSNR result no
matter how the question is phrased.
