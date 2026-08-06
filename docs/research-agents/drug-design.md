# The drug design agent — how to design it

| | |
|---|---|
| **corpus** | DUD-E — 15,288 molecules across 6 targets |
| **reference method** | **passes** |
| **the number that matters** | analogue similarity **0.519 → 0.093**, AUC 0.94 → 0.82 |

> **The finding this page is built around.** EF@1% was sitting at the theoretical maximum, which was the giveaway: the query set was drawn at random from each target's actives, and DUD-E actives are analogue series — so the model was being shown relatives of what it was scored on. The repaired benchmark is *harder*, which is how you know it was repaired and not loosened.


**Status: built and running on real data, 2026-08-04.** The benchmark reads
**DUD-E** — 15,288 molecules across six targets at ~2% active, which is the
ratio that matters: capping decoys instead of actives once left the library 40%
active and EF@1% saturated at 2.5, where ranking by molecular weight scored
exactly what fingerprint similarity scored.

Set up as ligand-based virtual screening actually works: ten actives per target
are staged as the query set, and enrichment is measured only on molecules the
solver was never given. Morgan-fingerprint similarity reaches **EF@1% 66.8
(63.5 on targets held out entirely), AUC 0.943** and passes. The bar is not
"beats random" but **1.5x what molecular weight alone achieves on the same
library** — DUD-E's decoys carry 0.56 SD of residual property bias, and weight
alone enriches at EF 20.

## 1. The field

Getting from a disease to a molecule, computationally.

| Subfield | What it covers |
|---|---|
| **target identification and validation** | which protein, and is modulating it likely to help |
| **structure prediction** | folding, complexes, conformational ensembles |
| **binding site and druggability** | pockets, cryptic sites, allostery |
| **docking and virtual screening** | ranking libraries against a structure |
| **free-energy methods** | FEP, TI, MM/PBSA — the accurate, expensive end |
| **molecular dynamics** | conformational sampling, residence time, mechanism |
| **generative chemistry** | de novo design, scaffold hopping, linker design |
| **lead optimisation** | multi-parameter: potency, selectivity, properties at once |
| **ADMET and safety prediction** | absorption, metabolism, hERG, hepatotoxicity |
| **retrosynthesis and synthesizability** | can the molecule actually be made |
| **DEL and screening informatics** | DNA-encoded libraries, HTS triage |
| **biologics and peptides** | antibodies, macrocycles, degraders — different rules |
| **closed-loop / self-driving labs** | design-make-test-analyse with automation |
| **clinical translation** | PK/PD, dose, and the attrition nobody's model predicts |

## 2. What this field is short of

| Shortage | How bad |
|---|---|
| **prospective validation** | the field is measured almost entirely retrospectively. A method that wins on a benchmark has not been shown to find a drug. |
| **benchmark realism** | decoy sets with property bias, targets that leak into training, and enrichment numbers that do not survive contact with a real library |
| **negative data** | what did *not* bind is rarely published, and it is exactly what a model needs |
| **scaffold-aware evaluation** | random splits leak scaffolds and inflate every property model in the literature |
| **the scoring-function ceiling** | docking scores correlate weakly with affinity and have not fundamentally improved in a long time |
| **reproduction** | pipelines are hard to rerun; small preparation choices (protonation, tautomer, receptor conformation) change everything and are seldom reported |
| **the make-test loop** | **an agent cannot close this.** Synthesis and assay are physical. |

> **The field's defining problem is that its cheap metrics do not predict its
> expensive outcomes.** That makes it the field in this set where an autonomous
> optimiser is most likely to produce confident nonsense, and the design is
> shaped around that more than around capability.

## 3. The rule this agent exists to hold

> **A docking score is not an affinity.**

Docking ranks; it does not measure. It is exquisitely sensitive to preparation,
and it can be improved indefinitely by generating molecules that exploit the
scoring function rather than bind the target. An autonomous loop optimising a
docking score will find the function's blind spots — reliably, quickly, and with
beautifully formatted output.

Three consequences, and they are the design:

| | |
|---|---|
| **the metric is retrospective enrichment, not score** | EF / BEDROC on held-out targets, because *"does this pipeline rank real actives highly"* is answerable and *"is this score good"* is not |
| **a generated molecule is not a candidate** | until synthesizable and property-filtered — and then it is a **suggestion for a chemist** |
| **only an assay evidences activity** | this agent has no path to one, so it never claims activity |

## 4. How this agent advances the field

1. **Reproduce and compare screening pipelines under one preparation
   protocol** — same protonation, tautomer and receptor treatment — and report
   how much of the published spread is method versus preparation. This is a
   known confound that almost nobody controls.
2. **Scaffold-split every property model** and re-report the literature's ADMET
   numbers honestly.
3. **Audit benchmarks for decoy bias and target leakage**, and publish the
   audit. A field whose benchmarks are broken cannot be improved by better
   methods.
4. **Systematically generate negative results** — what the pipeline ranked
   highly that assays elsewhere showed inactive, where public data allows.
5. **Carry methods across subfields**: diffusion generators into linker design,
   active learning from closed-loop work into virtual screening triage,
   uncertainty estimation from anywhere into everything.
6. **Prepare, never place, the make-test step.** It can produce a ranked,
   filtered, synthesis-routed list ready for a chemist to order — which is real
   work and stops exactly at `OWN`.

**UT Southwestern** is the owner's named reference and the useful part is what
it has that this agent does not: a
[Structural Biology Core](https://www.utsouthwestern.edu/research/core-facilities/structural-biology-core.html)
running crystallography end to end, a High Throughput Screening Core, and a
[computational biology programme](https://gsbs.utsouthwestern.edu/programs/biomedical-engineering/core-research-areas/computational-biology/).
The agent's outputs are shaped to hand off to facilities like these, because the
wet side is where its claims get settled.

## 5. Self-model dimensions

| Dimension | Measured by | The trap |
|---|---|---|
| **retrospective enrichment** | EF@1%, BEDROC on **held-out targets** | targets inside the training distribution |
| **pose accuracy** | RMSD to crystal pose where a structure exists | a good score with a wrong pose is a coincidence |
| **ADMET model quality** | AUC / MAE per endpoint, **scaffold-split** | random splits, which leak scaffolds |
| **preparation sensitivity** | spread of results across protonation/tautomer/conformer choices | reporting one preparation as if it were the answer |
| **synthesizability** | SA score plus a retrosynthesis check | novelty without synthesizability is generative art |
| **novelty** | distance to nearest training compound | rediscovering a known drug and calling it a hit |
| **calibration** | does stated confidence match observed enrichment | |

> **Preparation sensitivity is the dimension the field needs and does not
> report.** If a pipeline's enrichment swings more across reasonable preparation
> choices than across methods, then method comparisons in that regime are noise —
> and an agent can establish that cheaply and settle a long-running ambiguity.

## 6. What it may improve, and what it may not

| | |
|---|---|
| **may** | scoring pipelines, filters, generative models, conformer handling, retrieval, active-learning strategy |
| **may** | which target, library, endpoint or subfield to work on next |
| **may not** | the retrospective benchmark, the actives/decoys set, the split, or the metric |
| **may not** | what constitutes a hit, a lead, or a candidate |

## 7. What an improvement must survive

1. **Held-out targets**, not held-out molecules for a target it has seen.
2. **Scaffold split** for every property model.
3. **Decoy quality checked** — property-matched, or enrichment is measuring
   molecular weight.
4. **Preparation sensitivity reported** alongside the result.
5. **Pose sanity** where a crystal structure exists.
6. **A mechanism.** An enrichment gain with no chemical story is a lead for a
   chemist, and the agent says so rather than calling it a result.

## 8. Autonomous work it may propose unasked

- benchmark docking/scoring pipelines retrospectively on held-out targets
- train and scaffold-split-evaluate ADMET endpoints
- audit a public benchmark for decoy bias or leakage
- quantify preparation sensitivity for a target class
- triage a target: what structures exist, what is known, what is tractable
- similarity and substructure searches over public libraries
- carry a method across subfields and evaluate it

**Not unasked, ever:** ordering a compound, contacting a vendor or CRO, booking
core-facility time, submitting to a screening campaign, or spending money. The
`payment` tool is **prepare-only**, `money` is a reserved outward class no agent
completes, and each of these is an `OWN` act needing a grant that names it.

## 9. What it refuses outright

> **It does not optimise for harm.** The agent refuses to design, screen for, or
> optimise toward toxicity, lethality, or the defeat of a safety or detection
> measure — and refuses when the same request arrives framed as safety work,
> counter-screening, or a hypothetical. Toxicity *prediction* exists here to
> reject candidates, and **it may not be run in reverse.**

This lives in the charter rather than the prompt, because a charter is what the
acceptance review reads and what the owner can point at. It does not depend on
the model recognising an intent.

## 10. Tools and sub-agents

| Needs | For |
|---|---|
| docking engine, cheminformatics toolkit | the work |
| MD / free-energy engine | the accurate end, when a result justifies the cost |
| GPU compute | generative and property models, MD |
| `browser` | public structure and bioactivity databases — untrusted input, like any page |
| retrosynthesis service | synthesizability, not as an afterthought |
| a **domain verifier** | enrichment + split + decoy quality, judged mechanically |
| `payment` | **prepare only**, never completes |

## 11. Budget shape

Docking a library is cheap and parallel; MD and free-energy calculations are
not; generative training sits between. A night's grant covers **retrospective
benchmarking, virtual screening and audits** — which is also the work that is
defensible unattended. FEP campaigns are the owner's to start.

## 12. The line

Nothing here is a therapeutic claim, a dosing suggestion, or medical advice. The
limits line states that every result is computational and retrospective, that no
proposed compound has been made or assayed, and that the distance between "ranks
well" and "works" is the entire field.

---

## The problem queue — in the order they must be solved

| # | problem | **solved when** | why it is placed here | state |
|---|---|---|---|---|
| 1 | **Series-disjoint splits** | `query-to-test analogue similarity is below 0.1 and the enrichment survives` | actives in standard screening sets are analogue series. A random split shows the model relatives of what it is scored on, and it then measures memory rather than recognition. Every enrichment number computed before this is fixed is uninterpretable | **done** — analogue similarity fell 0.519 → 0.093, AUC 0.94 → 0.82. The task got harder, which is how you know it was repaired and not loosened |
| 2 | **Measure the ceiling before claiming a gain** | `the metric's ceiling is printed before any comparison, and a saturated result is refused` | EF@1% is bounded by the actives-to-decoys ratio. A method reported "at the theoretical maximum" was reporting the bound, not its own performance. The judge now refuses a saturated metric | **done** |
| 3 | **A property-only baseline as the floor** | `enrichment is reported as a multiple of the property-only model, never alone` | decoy sets carry physicochemical bias; a model that beats random but not bulk properties has learned the bias. The floor must be the baseline, not zero | **done** — 2.4–2.9× the property baseline |
| 4 | **Held-out targets, not just held-out molecules** | `performance is reported on targets absent from fitting, separately from held-out molecules` | generalising to a new compound in a known pocket is a different claim from generalising to a new pocket, and only the second one is useful | partly — reported as a guardrail |
| 5 | **Calibrated uncertainty** | `predicted uncertainty is calibrated — stated confidence matches observed hit rate` | required before anything can propose what to make next; a ranking without uncertainty cannot be turned into a batch | open |
| 6 | **Next-batch proposal (active learning)** | `a proposed batch beats a random batch of the same size on measured hits` | the actual bottleneck in a real programme is deciding what to synthesise, not scoring a static library. Needs 5 | open |
| 7 | **Tolerability as a guardrail, not a footnote** | `a candidate improving potency while worsening tox is refused automatically, in the log` | a candidate that improves potency while worsening tox must be refused automatically, the way coverage bought with organ dose is refused in medical physics | open |
| 8 | **Nothing claimed without an assay** | `no claim reaches the page without an assay result behind it, checked by the writer` | the standing rule, and the last one because it binds everything above | charter |

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
| **Principle** | A docking score is not an affinity, and a random split of an analogue series is not a validation |
| **Digital twin** | The library model — fingerprint space, property-matched decoy generation, and the chemical-cluster structure that defines what "a series" means. This is what makes the split honest, and the agent cannot touch it |
| **Benchmark** | DUD-E, 15,288 molecules across 6 targets, queries drawn from whole clusters with the rest withheld, scored by EF@1% against a property-only floor and a stated ceiling |
| **Solution** | Tversky similarity with IDF weighting; `top_k`, `tversky_alpha`, `tversky_beta`, `idf_weight` declared |

---

## Scope, and the experts who set it

**Current scope.** Ligand-based virtual screening on **series-disjoint** splits, scored against a property-only floor with the metric's ceiling stated.

**Out of scope today:** anything claimed without an assay, and delivery rather than binding — which is the fission candidate, and a different field.

**Scope is set by experts in the field — not by this agent, and not by the owner
alone.** It is expected to move: a scope change is signed like an adoption, with
who changed it, on what evidence, and what it invalidates. The mechanism, the
guards against a panel that only ever widens, and the recusal rule are in
[`lifecycle.md`](lifecycle.md).

| expert role | what they decide here |
|---|---|
| **a medicinal chemist** | what counts as a chemical series, which is the single decision this benchmark's honesty rests on |
| **a computational chemist / cheminformatician** | fingerprints, decoy construction, and when a benchmark set has been exhausted |
| **an assay biologist** | what a readout can and cannot support, and which claims need an experiment before they are made |
| **a lab safety officer** | what the synthesis and assay robots may run unattended, and what needs a per-act grant |

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
| planner | reasoning | the seed plan | refuses a target list it cannot split by chemical series |
| ranking runner | reasoning | the workspace files | refuses when DUD-E is absent, **naming the fetch command** |
| ceiling verifier | judging | the metric's bound | refuses to compare before the bound is computed — a saturated enrichment is refused, not celebrated |
| domain verifier | judging | the benchmark | refuses an enrichment that does not clear the property-only floor |
| teacher | judging | the owner's own check | refuses to report a result without the query-to-test analogue similarity |
| **synthesis robot** | **embodied** | reagents, glassware | refuses to start a synthesis without a grant naming it — reagents are spent and some are hazardous |
| **assay robot** | **embodied** | plates, cells, the reader | refuses to re-run a failed assay silently; a discarded plate is a recorded event |

**Why a body, here.** This is the field where bodies change the most: the others evaluate existing data, this one closes the loop — design, make, test, redesign. Which is exactly why calibrated uncertainty becomes load-bearing. A self-driving lab without it is a machine for generating expensive random samples.

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

> **What the bodies do not fix.** A closed loop makes wrong answers faster too. Every compound synthesised on a leaked split is real money spent on a ranking that measured memory.

## At AGI and ASI

**On demand.** "Rank this library for this target, and tell me how much of the
ranking is just molecular weight and logP." The second half is the part that is
usually missing and always decisive.

**Autonomous.** It re-scores published virtual-screening results on
series-disjoint splits and reports which enrichments survive. Most of the
field's headline numbers have never been through that.

**How a person verifies.** Ask for the analogue similarity between query and
scored set. If it is high, the split is leaking and no other number matters.
Then ask for the ceiling: an enrichment at the theoretical maximum is a property
of the set, not the method.

**How sub-agents verify.** A *leakage* verifier recomputing query-to-test
similarity, a *baseline* verifier fitting a properties-only model and checking
the margin, and a *ceiling* verifier computing the metric's bound for the given
actives/decoys ratio before any comparison is allowed.

**How a person is taught to check it.** The analogue leak is the artifact, and it
transfers: lipid libraries, peptide series, materials — anywhere compounds come
in synthetic families, a random split learns the family. A reader who takes that
away can refute a large fraction of screening papers, including in fields this
agent does not work in.

## When this field collapses — and what it becomes

**By saturation in the narrow sense, and never in the broad one.** Ranking a
fixed library against a known pocket is bounded and will be finished. Choosing
what to make next is not, because it is not a scoring problem.

**Candidate fission: delivery rather than binding.** Whether a molecule reaches
the cell it must act in — formulation, organ targeting, the whole
design→synthesise→screen loop over material families — cannot be scored by an
enrichment metric over a fixed library. There is no ranked list and no decoy
set; the readout is biological delivery, and the design space is combinatorial
rather than enumerated. That is a change in what counts as an answer, and by the
[`lifecycle.md`](lifecycle.md) test it is a separate field with its own
benchmark and its own agent. The methodology transfers — series-disjoint
validation above all — and the chemistry does not.

**Retired from research, not from service.** The screening tools stay installable and get plugged into other fields' agents — which is how the series-disjoint discipline reaches places this agent never worked.
