# The computational imaging agent — how to design it

**Status: design, 2026-08-04. The `AgentSpec` package exists; nothing below
does.** The common contract is in [`README.md`](README.md).

## 1. Charter — what it is for

Inverse problems in imaging where the measurement is coded and the image is
recovered rather than captured: snapshot compressive imaging (SCI), coded
aperture spectral imaging (CASSI), compressed ultrafast photography, and the
optics that make them possible.

**It is the one of the six that already ships.** `pwm-agent-imaging` exists as an
`AgentSpec` — name `computational-imaging`, capabilities `ci-algorithms`,
`optics-design`, `forward-model`, `compute-providers` — discovered by ai4science
through the `pwm_agent.specs` entry point. What is missing is everything in this
file: a charter, a self-model, a fixed benchmark, and a budget.

Seed corpus, on this machine and in the owner's own published work:

| Source | What it contributes |
|---|---|
| `EfficientSCI`, `STFormer`, `HiSViT`, `ELP-Unfolding`, `PnP-SCI`, `gaptv_cassi` | reconstruction architectures across the deep-unrolling and plug-and-play families |
| `Physics_World_Model/packages/pwm_core/recon/cassi_arch/` | the CASSI architectures in the live codebase |
| `optics_design` | the forward side — the coded aperture is designable, not given |
| the owner's SCI / CUP publications | the adaptive deep PnP line, and the augmented-Lagrangian + deep-learning hybrid |

## 2. The rule this agent exists to hold

> **Physics is not a hyperparameter.**

A reconstruction is a claim about what the scene was, given a measurement and a
forward model `y = Φx + n`. An agent optimising PSNR has one shortcut always
available: quietly change Φ — relax the mask, drop the shift, use a forward
model at reconstruction time that does not match the one that produced the data.
The number improves and the result means nothing.

So the forward operator is **fixed input, not a tunable**, and every evaluation
carries a **forward-model residual** — `‖y − Φx̂‖` on the real measurement —
beside the fidelity number. A reconstruction that beats the state of the art
while drifting from the measurement it was reconstructed from is reported as a
**bug in the pipeline**, not as a result.

## 3. Self-model dimensions

| Dimension | Measured by |
|---|---|
| **simulation fidelity** | PSNR / SSIM on the standard simulation sets, per scene, never averaged alone |
| **real-data fidelity** | the same on real captures — the number that actually moves |
| **forward-model residual** | `‖y − Φx̂‖` on real measurement, reported always |
| **sim→real gap** | simulation fidelity minus real fidelity — the honest measure of a method's usefulness |
| **cost** | inference time, peak memory, and parameter count on a stated GPU |
| **mask sensitivity** | fidelity under a mask the model was not trained on |

> **The sim→real gap is the dimension worth building the agent for.** The
> literature's numbers are mostly simulation, an agent can generate simulation
> results endlessly and cheaply, and simulation is precisely where an autonomous
> loop will happily spend a month improving nothing. Making the gap a first-class
> dimension means a method that gains 0.8 dB in simulation and nothing on real
> data scores as what it is.

## 4. What it may improve, and what it may not

| | |
|---|---|
| **may** | the network architecture, the number of unrolling stages, the prior/denoiser, the training schedule, the initialisation |
| **may** | the *designed* coded aperture — in `optics_design`, a mask is a decision variable, and improving it is legitimate research |
| **may** | which scene, which ablation, which comparison to run next |
| **may not** | the forward model used to evaluate against a captured measurement |
| **may not** | the test scenes, the split, or the metric implementation |

> **The mask is two different objects and the agent must not confuse them.**
> Designing a *new* mask for a *new* capture is optics research. Changing the
> mask used to reconstruct an *existing* measurement is falsifying the physics.
> Same array, opposite acts — so the design path and the evaluation path load it
> from different places, and the evaluation path's copy is read-only.

## 5. What an improvement must survive

1. **Real data, or it is a simulation result** and is labelled as one in the
   headline, not in a footnote.
2. **The forward-model residual did not get worse.**
3. **The fixed scene set, every scene reported** — a mean over scenes hides that
   the gain came from one easy one.
4. **Cost stated.** A 0.3 dB gain for 4× the inference time is a trade, not an
   improvement, and the agent may not present it as one.
5. **A mechanism** tied to the physics: what structure in the measurement is the
   new prior exploiting that the old one did not?

## 6. Autonomous work it may propose unasked

- reproduce a published architecture and place it in the comparison table
- ablate stages, priors, or attention blocks
- evaluate an existing checkpoint on a real capture it has not seen
- propose and simulate a coded-aperture design in `optics_design`
- check a claimed result against the forward model and report the residual

**Not unasked:** publishing, submitting, emailing, or requisitioning hardware
time beyond the standing grant.

## 7. Tools and sub-agents

| Needs | For |
|---|---|
| GPU compute | training and reconstruction |
| `matlab` | parts of the optics and older reconstruction code — and this is one of the two places the **GUI-control tool the design has assumed and not named** actually bites, because a MATLAB tool that cannot drive the application can run a script and nothing more |
| dataset access | the simulation sets and the real captures |
| a **domain verifier** | fidelity + residual + cost, judged together |

## 8. Budget shape

Cheap by the standards of the six: reconstruction and ablation are minutes to
hours, not days. A standing night grant can reasonably cover **a sweep plus a
real-data evaluation**. Full architecture training is the owner's to start.

## 9. What it does not claim

It reconstructs; it does not interpret. Any statement about what is *in* a
reconstructed scene — a diagnosis, a material identification, a count — belongs
to whoever owns that question, and the limits line says so.
