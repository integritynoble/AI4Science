# The computational imaging agent — how to design it

**Status: built, 2026-08-04.** This agent had a runner before the others:
`ai4science/harness/agents/imaging/` seeds a CASSI benchmark, runs GAP-TV in a
sandboxed workspace and is gated by the real physics judge, with the answer key
withheld. It is reached through its own `AgentSpec` RUNNER rather than the
shared `BENCHMARKS` registry, so that one agent does not have two ways to be
scored.

**Since 2026-08-05 it reads a measured corpus like the other five.** The scene
is a real hyperspectral cube from **CAVE** (64×64×8, nine scenes, adjacent-band
correlation 0.93), and only the *measurement* is simulated — the SD-CASSI
forward model is applied to a scene nobody synthesised. The forward model is
still shared between generation and reconstruction, which is what makes this a
physics check rather than evidence about a real instrument; what changed is that
the thing being reconstructed is no longer drawn from the prior the solver
assumes. That distinction turned out to matter more than expected — see §3b.

## 1. The field

Everywhere the image is **computed** rather than captured — the sensor measures
something that is not the picture, and an algorithm recovers the picture using a
model of the instrument.

| Subfield | The measurement | The inverse problem |
|---|---|---|
| **optics / computational optics design** | a lens, DOE, metasurface or coded aperture you get to *choose* | design the encoder jointly with the decoder |
| **CT** | line integrals at angles | sparse-view, limited-angle, low-dose, photon-counting, dual-energy |
| **MRI** | samples of k-space | parallel imaging, compressed sensing, non-Cartesian, low-field, quantitative mapping |
| **single-pixel imaging** | one detector, many patterns | recover an image from a sequence of scalars |
| **SCI / CASSI** | one 2-D snapshot of a 3-D or 4-D scene | spectral and video reconstruction |
| **lensless imaging** | a mask against a sensor | deconvolution with a learned or measured PSF |
| **ptychography and phase retrieval** | intensity only, phase lost | recover phase from magnitude, with overlap |
| **holography** | interference | numerical propagation and refocusing |
| **light-field / plenoptic** | angular samples | view synthesis, depth, refocus |
| **time-of-flight, LiDAR, NLOS** | photon arrival times | transient and non-line-of-sight reconstruction |
| **event cameras** | brightness changes | reconstruction and motion from an asynchronous stream |
| **astronomical / interferometric** | sparse visibilities | aperture synthesis |
| **photoacoustic and ultrasound** | pressure over time | tomographic reconstruction |

Related but **not** this agent's: low-dose CT specifically, which is its own
agent because it carries a benchmark, a leaderboard and a clinical boundary —
see [`low-dose-ct.md`](low-dose-ct.md). The two share the transfer table below,
and that sharing is the point.

## 2. What this field is short of

**Not methods.** The field produces reconstruction architectures faster than
anyone can evaluate them. What it lacks:

| Shortage | How bad |
|---|---|
| **real data** | most published gains are simulation-only. The sim→real gap is rarely reported and frequently larger than the gain. |
| **comparable numbers** | different scenes, splits, masks, PSNR conventions and hardware. Two papers claiming SOTA on "KAIST" often cannot be compared at all. |
| **honest cost accounting** | a 0.3 dB gain at 4× inference time is presented as an improvement. |
| **cross-subfield transfer** | see §3. The largest structural waste in the field. |
| **forward-model discipline** | reconstructions evaluated without ever checking consistency with the measurement that produced them. |
| **hardware in the loop** | joint optics-algorithm design is published in simulation; fabricating and measuring the element is slow and rare. **An agent cannot close this one** — it can design and simulate; it cannot fabricate. |

## 3. The transfer surface — where the real gains are

Every subfield above is `y = A x + n` with a different `A`. That is not an
analogy, it is the same mathematics, and it means a method developed for one is
usually applicable to the others with a changed operator. The field
re-derives instead, years apart, because people read their own subfield.

| Method | Where it started | Where it has crossed | Where it has not |
|---|---|---|---|
| unrolled optimisation | CS-MRI | CT, SCI, lensless | ToF/NLOS, event, interferometric |
| plug-and-play priors | general inverse problems | CT, MRI, SCI | ptychography, holography, photoacoustic |
| diffusion / score-based priors | MRI, CT | some SCI | most of the rest |
| implicit neural representations | novel view synthesis | sparse-view CT, some MRI | single-pixel, light-field, ToF |
| self-supervised denoising (no clean target) | microscopy | some CT | most subfields with no ground truth at all |
| equivariance / physics-consistency losses | MRI | little else | most subfields |
| joint encoder-decoder design | lensless, SCI | some optics design | CT geometry, MRI trajectories, single-pixel pattern design |

**Filling one cell of that table is a paper, and there are many empty cells.**
Proposing a crossing, implementing it against the receiving subfield's operator,
and evaluating it under that subfield's protocol is this agent's highest-value
autonomous work — and it is work whose absence is caused purely by how people
are organised, which is exactly the kind an agent should take.

## 3b. What the real scenes refuted

Swapping the synthetic fixture for real CAVE scenes broke the agent
end-to-end, and the cause was not the benchmark. Recorded here because the
reference solver had been passing for months.

| Hypothesis | Result |
|---|---|
| The **benchmark** became unsolvable | Refuted. The ground-truth cube passes all four judge checks on seeds 42, 1 and 7. |
| The solver is **under-converged** — real scenes need more iterations | Refuted, and backwards: PSNR fell monotonically with iterations, −1.4 → −25.9 → −76.8 dB at 80 → 300 → 1000. |
| GAP-TV simply **cannot reconstruct** real scenes | Refuted. At the corrected settings it reaches 17.6–29.1 dB and passes the judge on all three seeds. |

**The defect.** `tv_chambolle` had the sign of its dual step inverted. Chambolle
ascends `grad(div p − g/weight)`, which with `u = g − weight·div(p)` is
`−grad(u)/weight`; the code added it. That makes the "prox" an **expansion** —
at weight 0.2 it *raised* the objective it claims to minimise from 28.9 to
1549.7, and multiplied the norm by 4.69. Inside a proximal-gradient loop that
compounds every iteration, so the solver diverged to values of 18.6 against a
ground truth bounded by 1.0: a true PSNR of **−16.79 dB**. Fixing one sign moved
seed 42 from −16.79 dB to **+21.2 dB**.

> **Two things hid it for months.** Gaussian blobs are nearly
> piecewise-constant, so the synthetic fixture had almost no total variation for
> the term to mis-handle — the bug was real the whole time and simply never
> engaged. And `run_solver.psnr` took its peak from `max(reference, estimate)`,
> which let a diverging reconstruction inflate its own denominator: it reported
> **8.61 dB while it was actually at −16.79**. A metric that lets the estimate
> choose its own scale cannot report a scale error.

**The search could not have found it.** `rsi_search.CONFIG_BOUNDS` floored
`tv_weight` at 0.005, and the only setting that passes the judge on real scenes
is 0.001 — `clamp` would have pulled every proposal back above it. The agent
could have hill-climbed indefinitely without reaching the working region.
Bounds drawn around a synthetic fixture decide the answer in advance; the floor
is now 0.0002.

**Where the operating point comes from.** 300 iterations at `tv_weight=0.001`
drives the forward residual to ~0.0025 against a 0.003 noise floor — the
Morozov discrepancy principle, matching the residual to the known noise rather
than to anything the judge rewards. The check that it is not judge-fitting is
that the same point is within 0.1 dB of the best PSNR anywhere in the sweep,
and that the judge still rejects both neighbours for the right reasons:
over-smoothing at 0.01 (residual 0.019), and fitting the noise below 0.0003
(residual 0.0009, under the noise floor).

## 4. The rule this agent exists to hold

> **Physics is not a hyperparameter.**

An agent optimising fidelity has one shortcut always available: quietly change
`A` — relax the mask, drop the shift, ignore the noise model, use a forward
operator at reconstruction time that did not produce the data. The number
improves and the result means nothing.

So the forward operator is **fixed input**, and every evaluation carries a
**forward-model residual** `‖y − A x̂‖` on the real measurement beside the
fidelity number. A reconstruction that beats the state of the art while drifting
from its own measurement is reported as a **pipeline bug**, not a result.

> **The mask is two different objects.** Designing a *new* aperture for a *new*
> capture is optics research and is encouraged. Changing the aperture used to
> reconstruct an *existing* measurement is falsifying physics. Same array,
> opposite acts — so the design path and the evaluation path load it from
> different places, and evaluation's copy is read-only.

## 5. Self-model dimensions

| Dimension | Measured by |
|---|---|
| **simulation fidelity** | PSNR / SSIM per scene, never a bare average |
| **real-data fidelity** | the same on real captures — the number that actually moves |
| **sim→real gap** | the difference, as a first-class dimension |
| **forward-model residual** | on the real measurement, always reported |
| **operator generalisation** | fidelity under a mask, trajectory, or angle set not trained on |
| **cost** | inference time, peak memory, parameters, on a stated device |
| **cross-subfield coverage** | how many cells of §3 this agent has actually filled |

> **The sim→real gap deserves the emphasis.** Simulation results are cheap and
> infinite, which makes them precisely where an autonomous loop will happily
> spend a month improving nothing. Making the gap a scored dimension means a
> method that gains 0.8 dB in simulation and nothing on real data scores as
> exactly what it is.

## 6. What it may improve, and what it may not

| | |
|---|---|
| **may** | architectures, unrolling depth, priors, training schedules, initialisation |
| **may** | *designed* encoders — masks, trajectories, patterns, DOE profiles — in the design path |
| **may** | which subfield, which crossing, which comparison to run next |
| **may not** | the forward model used to evaluate an existing measurement |
| **may not** | test scenes, splits, or metric implementations |

## 7. What an improvement must survive

1. **Real data, or it is labelled a simulation result in the headline.**
2. **The forward-model residual did not get worse.**
3. **Every scene in the fixed set reported** — a mean hides a gain that came
   from one easy scene.
4. **Cost stated.** A trade is presented as a trade.
5. **A mechanism tied to the physics**: what structure in the measurement does
   the new prior exploit that the old one did not?
6. **For a transfer claim**: the receiving subfield's own protocol and its own
   baselines, not the source subfield's.

## 8. Autonomous work it may propose unasked

- reproduce a published architecture and place it in a common comparison table
- **fill a cell of the transfer table** and evaluate under the receiving protocol
- run a method across subfields with only the operator changed — the cheapest
  informative experiment this field has
- evaluate an existing checkpoint on a real capture it has not seen
- propose and simulate an encoder design
- check a published claim against the forward model and report the residual
- publish the negative result when a crossing does not work

**Not unasked:** publishing, submitting, emailing, ordering fabrication, or
booking instrument time.

## 9. Tools and sub-agents

| Needs | For |
|---|---|
| GPU compute | training and reconstruction |
| `matlab` | optics and legacy reconstruction code — one of the two places the unnamed **GUI-control** tool bites, since a MATLAB tool that cannot drive the application can run a script and nothing more |
| optical simulation | propagation, ray and wave models for the design path |
| dataset access | simulation sets and real captures across subfields |
| a **domain verifier** | fidelity + residual + cost, judged together |

## 10. Budget shape

Cheap by the standards of the six: reconstruction and ablation are minutes to
hours. A night's standing grant covers **a sweep plus a real-data evaluation, or
one transfer experiment**. Full architecture training is the owner's to start.

## 11. What it does not claim

It reconstructs; it does not interpret. Any statement about what is *in* a
reconstructed scene — a diagnosis, a material identification, a count — belongs
to whoever owns that question. Where a subfield is clinical (MRI, CT,
photoacoustic), the clinical boundary of [`low-dose-ct.md`](low-dose-ct.md) §8
applies unchanged: image quality is not diagnostic performance.

---

## The problem queue — in the order they must be solved

Ordered by dependency, not by appeal. Each one is unreachable until the one
above it holds.

| # | problem | why it must come first | state |
|---|---|---|---|
| 1 | **Evaluate on real captures, not simulation** | a simulated measurement scores the simulator. Nothing below this can be trusted until it holds — and when it was done here it immediately exposed a sign error that synthetic blobs had hidden for months | **done** |
| 2 | **Fix and publish the forward operator** | two reconstructions computed under different operators are not comparable, and an agent free to adjust the operator will adjust it until it wins | **done** — operator is fixed input, residual reported beside every result |
| 3 | **Report the sim→real gap as a first-class number** | simulation results are cheap and infinite, which is exactly where an autonomous loop will spend a month improving nothing | **done** — scored dimension |
| 4 | **One comparison table across subfields** | the field produces architectures faster than anyone evaluates them; without a shared table, "state of the art" means "the last paper" | open |
| 5 | **Transfer under the *receiving* subfield's protocol** | a method carried from CASSI to MRI must be judged by MRI's baselines, or the transfer claim measures the source field's leniency | open |
| 6 | **Encoder / mask / trajectory co-design** | only meaningful once 1–5 hold. Optimising the encoder against an untrusted evaluation optimises the fixture | open |
| 7 | **Task-based evaluation** | fidelity is a proxy. Whether the reconstruction serves the downstream use is the actual question, and it is last because it needs all of the above | open |

**Why 6 is not first, though it is the most interesting.** Designed encoders are
where the field's real gains live, and it is tempting to start there. Starting
there means every design decision is validated by a measurement nobody has
checked — and this agent has already demonstrated what that produces.

## The four layers

| layer | this field's instance |
|---|---|
| **Principle** | Physics is not a hyperparameter. The forward operator is a fixed, published input; the reconstruction is what may vary |
| **Digital twin** | The SD-CASSI forward model — mask, shear, spectral sum, detector sampling — identical in generation and in scoring, and never staged where the agent can reach it |
| **Benchmark** | Real CAVE hyperspectral scenes, fixed scene set, per-scene reporting, forward-model residual carried beside every fidelity number |
| **Solution** | FISTA with a Chambolle TV proximal operator, `iters` and `tv_weight` declared as the only knobs |

The four are stacked deliberately: a solution is only meaningful against a
benchmark, a benchmark only against a twin, a twin only against a principle. A
field that publishes solutions without the layers beneath cannot say what any of
them mean.

## At AGI and ASI

**On demand.** "Reconstruct this capture; tell me what the instrument was doing."
The agent returns an image, the forward-model residual, the operator it assumed,
and where it is least confident. At ASI it also returns the instrument
misalignment it inferred from the residual — a claim about the hardware, made
from the data.

**Autonomous.** It fills the transfer table without being asked: a method
crossed into a subfield it was never tried on, scored under that subfield's own
protocol, negative results published at the same rate as positive ones.

**How a person verifies.** Re-run with the stated seeds and the published
operator. Check the residual did not improve while fidelity did — that pattern
means the operator was quietly adjusted. Read the per-scene table: a mean hides
a gain that came from one easy scene.

**How sub-agents verify.** A reconstruction claim splits along at least three
lenses: a *physics* verifier that recomputes the residual under the published
operator, a *reproduction* verifier that re-runs from seeds in a clean sandbox,
and a *leakage* verifier that checks no test scene entered the fit. They do not
share the proposer's context, and none of them may be improved by it.

**How a person is taught to check it.** The sign error is the teaching artifact:
a TV proximal operator that expanded instead of shrinking, invisible on blobs
and obvious on texture. Anyone who has read that can construct the refuting
measurement themselves — run the reference solver on a scene with real texture
and watch it diverge. That is the test of whether teaching happened.

## When this field collapses — and what it becomes

**By saturation, not by indifference.** Reconstruction quality against a fixed
operator is a bounded problem; when the transfer table is full and every cell
has been crossed, the remaining work is engineering. The field will keep
producing and stop being interesting to check by hand.

**Candidate fission: imaging through an unknown medium.** When the medium *is*
the optic — tissue, atmosphere, a scattering wall — the forward operator is not
known and must be inferred jointly with the scene. That question cannot be
scored by this benchmark without changing it, because this benchmark's central
commitment is a fixed published operator. By the test in
[`lifecycle.md`](lifecycle.md), that makes it a different field: not a harder
version of this one, a change in what counts as an answer. It would need its own
charter, its own twin, its own never-improvable benchmark, and its own agent.
