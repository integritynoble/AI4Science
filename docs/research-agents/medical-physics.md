# The medical physics agent — how to design it

| | |
|---|---|
| **corpus** | OpenKBP — real head-and-neck plans |
| **reference method** | **2 of 4 slices pass** |
| **the number that matters** | one case has a D99 ceiling of **62.6** against a **66.5** floor |

> **The finding this page is built around.** Three wrong diagnoses preceded the real one — impossible constraints, step-size collapse, nested targets — and the cause was a NaN that silently disabled the optimiser. One case is *provably unreachable by these beams*, which no optimiser fixes and which looks identical to a weak model unless someone measures the ceiling.

## Useful, and accepted — where this actually stands

The goal for every agent in this directory is to be **the best in its field:
useful, and accepted by people who know the field**. Those are two different
tests and this agent passes neither completely. Stating where it fails is not
modesty — an agent that cannot say what would refute it is not evidence of
anything.

| | |
|---|---|
| **useful to whom, today** | Nobody yet, as a planner. As a **method** it is already useful: the achievability bound separates an infeasible constraint set from a weak optimiser, and that distinction is missing from the field's literature. |
| **what blocks usefulness** | **It is 2D.** Nine beams on one plane cannot spare an organ above or below the target, so every plan it produces is a statement about one slice. |
| **what a field expert objects to first** | *"This is a student project."* Said politely, and correctly, by anyone who runs a planning group — and there is no framing that hides it, because this is their own field at their own altitude. |
| **the next action** | Finish and run the 3D planner, then **re-measure the achievability ceiling before looking at what the planner achieves**, so the bar is not set by the result. The 62.6 Gy ceiling is a 2D number and must not be quoted as anything else. |

## How experts guide this into a self-aware, self-improving agent — and then into collapse

The whole arc, in one place, because the sections that follow only make sense
inside it. The mechanism is shared and lives in [`lifecycle.md`](lifecycle.md);
what changes between fields is what the experts had to decide, and what the
agent is not allowed to buy improvement with.

**1 · Experts write the criterion, before the agent exists.** The field's
experts set the scope and decide the goal sheet — which constraints are absolute and which are trades — and that an **achievability bound** is reported beside every verdict. This is the load-bearing human
act: the agent inherits what counts as an answer here and may never change it.
An agent that could would be choosing its own benchmark.

**2 · The agent becomes self-aware in the only sense that is checkable.** Not
introspection — bookkeeping. It holds a measured record of what it has tested
and, kept strictly apart, what it has **not**: that its bound was measured in 2D, and which geometries it has never planned. Unmeasured reads as
unmeasured, and it costs something to write, because a self-model where
"unmeasured" is free empties its own queue. The gaps are the queue: where the
evidence is thinnest is where the next self-directed night goes.

**3 · It improves itself, bounded by something it cannot move.** Propose →
measure → an authority signs → adopt. It may change its method, its plan and its
own parameters; it may never change the benchmark, the metric or the verifier.
In this field the binding guardrail is **organ dose and hot spot: coverage bought with either is refused, naming the constraint and the amount**. That boundary is the
entire safety argument: an agent that can move what judges it does not improve,
it drifts, and it reports success the whole way.

**4 · Verification is handed over, in stages, and never all at once.** A person
signs every adoption today. Later, independent verifiers judge against criteria
fixed *before* the result existed — a DVH is recomputable from a dose volume and a contour set by anyone holding both — and a person audits a
sample. Later still, other fields' agents reproduce claims, which is the
strongest check available because agreement between two agents sharing a
codebase is nearly free. Experts keep scope throughout: *"is this worth
researching"* is not a measurement and no verifier answers it.

**5 · The field collapses.** Human verification goes to zero — either because
everything checkable has been checked and machines check faster than people can
follow, or because nobody cares any more. Both look identical from inside. What
tells them apart is whether anyone acts on the results.

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

**Retired from research, not from service** — and here the service half is the whole point: planning tools outlive the papers about them, and a physicist still signs every plan either way.

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

| # | problem | **solved when** | why it is placed here | state |
|---|---|---|---|---|
| 1 | **3D volumetric dose** | `dose is computed on the full volume and an OAR outside the target's plane changes the plan` | nine beams on one axial plane cannot spare an organ sitting above or below the target, and a cord that abuts the PTV in 3D looks adjacent-or-absent depending on which slice was picked. Every other number on this page is provisional until this holds | open — scoped in [`medical-physics-3d-plan.md`](medical-physics-3d-plan.md) |
| 2 | **Achievability measured before the planner is blamed** | `every verdict prints the ceiling beside the achieved value, re-measured in 3D` | "the model achieved X" is unreadable without knowing what was reachable. An infeasible constraint set and a weak optimiser produce identical evidence. This is the one genuinely novel thing here | **done in 2D** — one case has a D99 ceiling of 62.6 against a 66.5 floor; must be re-measured in 3D before it is repeated |
| 3 | **The full DVH metric set** | `D95/D99/D2, V95/V107, HI, CI and gEUD are all reported per structure` | D95/D99/D2, V95/V107, homogeneity and conformity indices, gEUD. This is the language the field reviews in; reporting anything else reads as an outsider and, worse, hides the trade being made | open |
| 4 | **Deliverability** | `the plan is expressed as deliverable apertures and re-scored after that conversion` | MLC and aperture constraints. A fluence map no linac can deliver is not a plan, and the gap between the two is where optimiser gains usually evaporate | open |
| 5 | **Protocol templates** (RTOG / NRG goal sheets) | `the judge's limits are loaded from a published goal sheet, not written in the benchmark` | the judge should encode a real clinical goal sheet rather than limits chosen by whoever wrote the benchmark | open |
| 6 | **Comparison against the delivered clinical plan** | `each structure is compared against the delivered clinical plan with the difference named` | per structure, differences named. A single score cannot say whether a plan is better or merely different | open |
| 7 | **Adaptive replanning and setup robustness** | `a plan holds under a stated setup error, and the degradation is reported` | last, because it presumes every one of the above | open |

> **2 must be re-measured, not carried.** The finding that one case is
> unreachable is a **2D** result. Nine coplanar beams are a far weaker delivery
> system than nine beams in 3D, so the ceiling will rise and the case may become
> feasible. Carrying that conclusion into a 3D planner would be exactly the
> error this agent keeps making: a property of the measurement reported as a
> property of the world.

> **Blocked by, and unblocks.** The order *is* the dependency graph: each rung
> is blocked by the ones above it and unblocks the ones below. They are not
> itemised per rung yet, which is a gap against the spec rather than a claim
> that the graph is a chain.
>
> **Evidence that would reorder it.** a 3D achievability sweep showing the unreachable case is reachable would reopen rung 2 and change what rung 1 was for. A ladder nobody can argue with is a
> ladder nobody checked.

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

## 12b. Rung 5 decomposed — automated QA that scales

**Rung 5 is decomposed and not the floor, because it is the rung that is a
programme rather than a measurement.** "An automated check flags the plans a
physicist would flag, at a stated sensitivity, with its misses characterised"
is one line covering what to check, what threshold, measured against what, and
what happens when it is wrong — and it is the field's defining constraint,
since adaptive RT is limited by how fast a plan can be checked while a patient
waits.

It is also the rung where this design's warning bites hardest: **the checking
is what stands between a plan and a person.** Every sub-rung below is written
so that automation makes the physicist's signature *fast*, never optional.

Owned by **`feasibility`** (5.1), **`verifier`** (5.2–5.3) and **`runner`**
(5.4); 5.5 is the physicist's.

### 5.1 · The catalogue of what can go wrong

**The problem.** "QA" is not a check until someone enumerates the failures it
is checking for. A large incident-learning corpus exists and is under-analysed,
and an automated check built without it will look for what its author imagined.

| | |
|---|---|
| **solved when** | a published failure catalogue, derived from incident data rather than from intuition, states each failure mode, how it presents in a plan, and how often it has actually occurred |
| **blocked by** | nothing — the floor |
| **unblocks** | everything below. A sensitivity figure is meaningless without a stated population of failures to be sensitive to |
| **what would reorder it** | nothing. It is unglamorous, it is derivable from data the field already holds, and nothing above it is interpretable without it |

### 5.2 · A check per failure mode, with its own criterion

**The problem.** One aggregate "plan quality" score is not a QA system: it
cannot say *what* is wrong, and a physicist cannot act on it.

| | |
|---|---|
| **solved when** | each catalogue entry has a check with a criterion written before any plan is scored, and each check reports pass, fail, or *cannot tell* — the third being mandatory and the one usually missing |
| **blocked by** | 5.1, and main rung 1 — a check that flags an infeasible target is flagging the geometry |
| **unblocks** | 5.3 |
| **what would reorder it** | nothing |

> **"Cannot tell" is a required verdict.** A check forced to choose between pass
> and fail on a plan it cannot assess will produce a pass, because passes are
> cheap and false alarms are expensive to the person reading them.

### 5.3 · Thresholds set against human spread, not against an ideal

**The problem.** A threshold chosen from a model's confidence is a statement
about the model. The useful question is whether the plan is outside what
competent planners produce.

| | |
|---|---|
| **solved when** | every check's threshold is expressed relative to main rung 3's inter-planner spread, and its sensitivity and false-alarm rate are reported at that threshold, with the **misses characterised** rather than only counted |
| **blocked by** | 5.2, main rung 3 (the spread) and main rung 4 (intervals) |
| **unblocks** | 5.4 |
| **what would reorder it** | evidence that the spread differs so much between institutions that a common threshold is meaningless — which would be a rung-3 finding and would change this rung's shape rather than its position |

### 5.4 · Measured against delivery, not only against calculation

**The problem.** A check that compares a plan to a dose calculation shares the
calculation's errors. The plan is delivered by a machine, and machines differ
from their models.

| | |
|---|---|
| **solved when** | the automated checks are validated against **measured** delivery on a phantom, across machines, and the disagreement between calculated and delivered is reported per check |
| **blocked by** | 5.3 |
| **unblocks** | 5.5, and any claim that automated QA is safe to rely on |
| **what would reorder it** | nothing |

> **This is the physical-labour rung, and §13i is what reaches it**: an embodied
> `runner` delivers to a phantom and an embodied `corpus` measures. **Every
> embodied act in this field is on a phantom** — that is in the scope, so
> removing it is a visible change rather than an efficiency.

### 5.5 · In the clinic, with the signature intact

**The problem.** A validated check that nobody uses has changed nothing; a
check that replaces the physicist has changed too much.

| | |
|---|---|
| **solved when** | the checks run in a clinical workflow, the time from plan to signature is measured and reported as reduced, and **every plan is still signed** — with the count of checks the physicist overrode published, because that number is how anyone learns the automation is drifting |
| **blocked by** | 5.4 |
| **unblocks** | adaptive RT at the throughput it needs |
| **what would reorder it** | nothing |

> **The override count is the safety instrument.** A QA system whose overrides
> fall to zero is either perfect or no longer being read, and those two look
> identical from the outside unless the number is published.

### The order, and what it says

```
5.1 failure catalogue ─> 5.2 per-mode checks ─> 5.3 thresholds vs human spread ─┐
                              (needs main 1)        (needs main 3, 4)           │
                                                                                ▼
                                              5.4 measured delivery ─> 5.5 clinic
                                                    (a body, on a phantom)   (a signature)
```

**The floor is a reading of incident data, and the ceiling is a signature that
does not move.** Between them the work is unglamorous: enumerate, threshold,
measure, deploy. That is the correct shape for a field whose shortage is
throughput of trustworthy checking rather than novelty — and it is why an
autonomous agent is both the obvious thing to point at it and the thing that
must never be left holding the pen.

## The four layers

| layer | this field's instance |
|---|---|
| **Principle** | A plan is a constraint set and a delivery system. Before an optimiser is called weak, what the geometry permits must be measured |
| **Digital twin** | The beamlet dose kernel — exponential depth attenuation along the ray with a lateral Gaussian for penumbra — fixed, shared between generation and scoring, and unreachable by the agent. Not a Monte Carlo engine, and the docs must never imply otherwise |
| **Benchmark** | OpenKBP head-and-neck plans, real contours, DVH criteria, with the achievability bound reported beside every verdict  — and its reference method is allowed to fail — it fails 2 of 4 cases, and one of those is provably unreachable |
| **Solution** | A gradient-descent fluence optimiser with backtracking line search; `under_weight`, `oar_weight`, `hot_weight`, `cold_weight`, `step`, `iters`, `tuning_rounds` declared |

---

## Scope, and the experts who set it

**Current scope.** Inverse treatment planning for external-beam radiotherapy, judged on DVH criteria **with an achievability bound reported beside every verdict**.

**Out of scope:** auto-segmentation, dose-engine development, and any claim of clinical readiness. A plan that treats a patient carries a human signature at every stage.

**Scope is set by experts in the field — not by this agent, and not by the owner
alone.** It is expected to move: a scope change is signed like an adoption, with
who changed it, on what evidence, and what it invalidates. The mechanism, the
guards against a panel that only ever widens, and the recusal rule are in
[`lifecycle.md`](lifecycle.md).

| expert role | what they decide here |
|---|---|
| **a clinical medical physicist** | the goal sheets in scope, what counts as deliverable, and whether a plan is comparable to the delivered clinical one |
| **a radiation oncologist** | which constraints are real trades and which are absolute — the judgement no optimiser encodes |
| **a QA / regulatory specialist** | what the QA robot may do, what must be measured on the machine, and where the signature line sits |
| **a planning-systems engineer** | whether a fluence map corresponds to something a linac can actually deliver |

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
| literature | reasoning | prior work, with citations | refuses a claim it cannot cite, and never reads while the method is being written |
| twin | reasoning | the beamlet dose kernel | refuses to be graded outside the regime it declares valid |
| corpus | reasoning | OpenKBP head-and-neck plans | refuses when the corpus is absent, **naming the fetch command** rather than substituting generated data |
| method | reasoning | the candidate solution | the only member that writes the thing being judged |
| runner | reasoning | compute | refuses a run whose cost or placement it cannot state |
| verifier | judging | the benchmark | refuses to judge against a criterion written after the result; refuses coverage bought with organ dose, naming the constraint and the amount |
| reproducer | judging | published artifacts alone | refuses a result it cannot re-run from what was published — catching the result that only exists on the machine that made it |
| teacher | judging | the owner's own check | refuses to report plan quality without the achievability bound beside it |
| writer | judging | the field page and the paper | writes last, from the record, never from intent |
| **QA robot** | **embodied** | phantoms, detectors, film | refuses to be in the room during beam-on |
| **delivery measurement robot** | **embodied** | the linac | refuses to adjust the plan to reduce the discrepancy it just measured |
> **Nine members are the floor, not the design.** A field may add; it may not
> remove. An agent whose manifest omits the **verifier** or the **twin** is not a
> research agent with fewer parts — it is *a method with a scoreboard*. Those two
> are deliberately not the worker's: they answer *"what should this produce"* and
> *"did it"*, and an agent owning both can pass any benchmark it likes by moving
> one of them.


**Why a body, here.** A fluence map is a plan; what the machine delivers is a fact, and the difference is where optimiser gains usually evaporate. **The signature does not move** — at every stage, including the last, a plan that treats a patient carries a human one.

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

> **What the bodies do not fix.** Nothing about a body shortens a clinical trial, and nothing about it makes a 2D planner 3D. Problem 1 on the queue is arithmetic, not labour.

## 13. The field page

| Layer | This field |
|---|---|
| **L1 · principle** | dose deposition is physics: energy transferred from a beam to tissue is computable from first principles. Planning is constrained optimisation against that computation — and **what the principle does not contain is what the dose does to the patient** |
| **L2 · spec — the digital twin** | the dose engine (Monte Carlo or convolution-superposition) plus the machine model and the patient geometry. **Where it stops:** heterogeneity approximations, motion, and — importantly — biology. The twin predicts *dose*, never *outcome*, and rung 6 exists because of that boundary |
| **L3 · benchmark** | OpenKBP, with a **computed feasibility ceiling per case** (rung 1). 2 of 4 slices pass: one target is unreachable by these beams at all (D99 ceiling 62.6 Gy against a 66.5 Gy floor) and one is reachable with the planner 3.4 Gy short |
| **L4 · solution** | a planner meeting the reachable objectives, reported only on cases the geometry allows |

**This field's twin is the strongest of the seven and its L1 is the narrowest.**
Dose can be computed to a few percent; what that dose does cannot be computed at
all. Every rung above 4 is an attempt to connect a precise physical model to a
biological question it cannot express.

**Not built:** no page on physicsworldmodel.org; the feasibility ceilings are
computed in the benchmark and are not published as an artifact others can use.

## 15. The teacher

The path from "knows what radiotherapy is" to checking one result:

1. **L1** — why a beam deposits dose where it does; why a target behind a
   critical structure is a geometry problem before it is a planning problem.
2. **L2** — run the dose engine on one phantom case and look at the
   distribution.
3. **L3** — compute the feasibility ceiling for the hard case and read
   **62.6 Gy against a 66.5 Gy floor**.
4. **L4** — run the planner on both cases and see it fall **3.4 Gy short** on
   the reachable one.

**The lesson is step 3 into step 4**: two failures that look identical in a
score and mean opposite things. A learner who can tell "the planner is weak
here" from "nothing could do this" can read the field's literature properly,
and that is a short path to a real skill.

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
