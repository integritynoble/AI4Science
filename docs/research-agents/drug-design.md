# The drug design agent — how to design it

| | |
|---|---|
| **corpus** | DUD-E — 15,288 molecules across 6 targets |
| **reference method** | **refused before the repair; passes on 11 of 12 seeds after it** |
| **the number that matters** | query-to-test analogue similarity, seed 42, like for like: raw **0.526 → 0.261**, decoy-subtracted **0.372 → 0.110**. AUC 0.955 → 0.850 |

> **The finding this page is built around.** EF@1% was sitting at the theoretical maximum, which was the giveaway: the query set was drawn at random from each target's actives, and DUD-E actives are analogue series — so the model was being shown relatives of what it was scored on. The repaired benchmark is *harder*, which is how you know it was repaired and not loosened.

## Useful, and accepted — where this actually stands

The goal for every agent in this directory is to be **the best in its field:
useful, and accepted by people who know the field**. Those are two different
tests and this agent passes neither completely. Stating where it fails is not
modesty — an agent that cannot say what would refute it is not evidence of
anything.

| | |
|---|---|
| **useful to whom, today** | Anyone with a published screening result: it re-scores on a series-disjoint split and says whether the enrichment survives. Most headline numbers have never been through that. |
| **what blocks usefulness** | **It has never predicted a molecule anyone made.** It ranks a fixed library; the bottleneck in a real programme is deciding what to synthesise next, and that needs calibrated uncertainty first. |
| **what a field expert objects to first** | *"Held-out molecules are not held-out targets."* Generalising inside a known pocket is a different claim from generalising to a new one, and only the second is useful. |
| **the next action** | Report performance on targets absent from fitting as a first-class number, then calibrated uncertainty. Those two together are what turn a ranker into something that can propose a batch. |

## How experts guide this into a self-aware, self-improving agent — and then into collapse

The whole arc, in one place, because the sections that follow only make sense
inside it. The mechanism is shared and lives in [`lifecycle.md`](lifecycle.md);
what changes between fields is what the experts had to decide, and what the
agent is not allowed to buy improvement with.

**1 · Experts write the criterion, before the agent exists.** The field's
experts set the scope and decide what counts as a **chemical series** — the single judgement this benchmark's honesty rests on — and that queries are drawn from whole clusters. This is the load-bearing human
act: the agent inherits what counts as an answer here and may never change it.
An agent that could would be choosing its own benchmark.

**2 · The agent becomes self-aware in the only sense that is checkable.** Not
introspection — bookkeeping. It holds a measured record of what it has tested
and, kept strictly apart, what it has **not**: which targets it has never seen, and that it has never predicted a molecule anyone made. Unmeasured reads as
unmeasured, and it costs something to write, because a self-model where
"unmeasured" is free empties its own queue. The gaps are the queue: where the
evidence is thinnest is where the next self-directed night goes.

**3 · It improves itself, bounded by something it cannot move.** Propose →
measure → an authority signs → adopt. It may change its method, its plan and its
own parameters; it may never change the benchmark, the metric or the verifier.
In this field the binding guardrail is **the property-only floor and the metric's ceiling: an enrichment that clears neither is refused**. That boundary is the
entire safety argument: an agent that can move what judges it does not improve,
it drifts, and it reports success the whole way.

**4 · Verification is handed over, in stages, and never all at once.** A person
signs every adoption today. Later, independent verifiers judge against criteria
fixed *before* the result existed — analogue similarity and enrichment are recomputable from the published split alone — and a person audits a
sample. Later still, other fields' agents reproduce claims, which is the
strongest check available because agreement between two agents sharing a
codebase is nearly free. Experts keep scope throughout: *"is this worth
researching"* is not a measurement and no verifier answers it.

**5 · The field collapses.** Human verification goes to zero — either because
everything checkable has been checked and machines check faster than people can
follow, or because nobody cares any more. Both look identical from inside. What
tells them apart is whether anyone acts on the results.

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

**Status: built and running on real data, 2026-08-04. Every number in this
section was re-measured on 2026-08-11 and is quoted from that night's run.** The
benchmark reads **DUD-E**, 15,288 molecules across six targets, 288 of them
actives, so 1.9% of the library. Withholding the query set's own clusters leaves
15,205 molecules scored at 1.4% active, and that ratio is what sets the metric's
ceiling. An earlier state of the generator, not re-run on 2026-08-11, capped
decoys instead of actives, left the library 40% active, and saturated EF@1% at
2.5, where ranking by molecular weight scored exactly what fingerprint
similarity scored.

Set up as ligand-based virtual screening actually works: ten actives per target
are staged as the query set, and enrichment is measured only on molecules the
solver was never given. The query set is drawn from whole chemical clusters and
the rest of those clusters is withheld rather than scored. On that split
Morgan-fingerprint similarity reaches **EF@1% 41.5 against a ceiling of 74.2, so
55.9% of the ceiling, at AUC 0.850** on seed 42, and passes. On the two targets
held out entirely it reaches EF 39.2, which is below its own overall figure.
Across twelve seeds EF@1% runs **32.7 to 56.0, mean 44.7**, which is 44.7% to
77.0% of each seed's own ceiling; held-out-target EF runs 45.4 to 68.6, and AUC
on unseen molecules runs 0.762 to 0.883. **Eleven of the twelve seeds pass. Seed
6 fails**, at 1.49x the property baseline against a bar of 1.5x.

The bar is not "beats random" but **1.5x what molecular weight alone achieves on
the same library**. The repaired screen ran 1.49x to 3.50x that baseline, mean
2.43x. Weight alone enriches at EF 14.7 to 24.9 across those seeds, and DUD-E's
decoys carry 0.45 to 0.60 SD of residual property bias.

**The saturated number this page used to lead with was a broken instrument, and
it is kept because catching it is the evidence.** Drawing the ten query actives
at random from each target's actives, with nothing withheld, gives EF@1% 66.789
against a ceiling of 66.789. That is 100.0% of the ceiling, at AUC 0.955. The
benchmark's own `_judge_screening` **refused** that run: refusal begins at 98.0%
of ceiling, which is EF 65.45 here. Seeds 0, 1 and 2 pin it at 100.0% of ceiling
as well. A metric at its bound reports the library's active fraction and not the
method, so it cannot rank one method above another. Until 2026-08-11 this page
gave that reading as its headline result and said it passed.

**Two of the older figures did not reproduce.** Pre-repair AUC came out 0.9550,
where this page previously published 0.943. Pre-repair raw analogue similarity
came out 0.5258, where the split's own docstring records 0.519. The figures
above are the 2026-08-11 ones. The older pair is named here rather than quietly
overwritten, and why the two runs differ is unmeasured.

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
| 1 | **Series-disjoint splits** | `query-to-test analogue similarity is below 0.1 and the enrichment survives` | actives in standard screening sets are analogue series. A random split shows the model relatives of what it is scored on, and it then measures memory rather than recognition. Every enrichment number computed before this is fixed is uninterpretable | **done** — measured 2026-08-11 on seed 42, like for like: raw analogue similarity fell 0.526 → 0.261, the decoy-subtracted gap fell 0.372 → 0.110, AUC 0.955 → 0.850. The task got harder, which is how you know it was repaired and not loosened. The gap runs 0.086 to 0.159 across twelve seeds, mean 0.116, so it clears this rung's own 0.1 bar on 5 of the 12 |
| 2 | **Measure the ceiling before claiming a gain** | `the metric's ceiling is printed before any comparison, and a saturated result is refused` | EF@1% is bounded by the actives-to-decoys ratio. A method reported "at the theoretical maximum" was reporting the bound, not its own performance. The judge now refuses a saturated metric | **done** |
| 3 | **A property-only baseline as the floor** | `enrichment is reported as a multiple of the property-only model, never alone` | decoy sets carry physicochemical bias; a model that beats random but not bulk properties has learned the bias. The floor must be the baseline, not zero | **done** — 1.5×–3.5× the property baseline across twelve seeds, mean 2.4×, measured 2026-08-11 |
| 4 | **Held-out targets, not just held-out molecules** | `performance is reported on targets absent from fitting, separately from held-out molecules` | generalising to a new compound in a known pocket is a different claim from generalising to a new pocket, and only the second one is useful | partly — reported as a guardrail |
| 5 | **Calibrated uncertainty** | `predicted uncertainty is calibrated — stated confidence matches observed hit rate` | required before anything can propose what to make next; a ranking without uncertainty cannot be turned into a batch | open |
| 6 | **Next-batch proposal (active learning)** | `a proposed batch beats a random batch of the same size on measured hits` | the actual bottleneck in a real programme is deciding what to synthesise, not scoring a static library. Needs 5 | open |
| 7 | **Tolerability as a guardrail, not a footnote** | `a candidate improving potency while worsening tox is refused automatically, in the log` | a candidate that improves potency while worsening tox must be refused automatically, the way coverage bought with organ dose is refused in medical physics | open |
| 8 | **Nothing claimed without an assay** | `no claim reaches the page without an assay result behind it, checked by the writer` | the standing rule, and the last one because it binds everything above | charter |

> **Blocked by, and unblocks.** The order *is* the dependency graph: each rung
> is blocked by the ones above it and unblocks the ones below. They are not
> itemised per rung yet, which is a gap against the spec rather than a claim
> that the graph is a chain.
>
> **Evidence that would reorder it.** evidence that held-out targets, not held-out series, are the binding generalisation gap would move rung 4 above rung 1. A ladder nobody can argue with is a
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

## 12b. Rung 6 decomposed — the closed make-test loop

**Rung 6 is decomposed because it is the field's defining gap and because it is
the one rung here that consumes matter.** "Compounds proposed by the method are
synthesised and assayed, and the prospective hit rate is reported" is one line
covering selection, makeability, synthesis, assay and feedback — five steps, of
which two are physical and irreversible.

This is also where this field's hazard is concentrated. Its cheap metrics do
not predict its expensive outcomes, so an optimiser that is excellent at the
metric will produce confident nonsense — and with hands, the nonsense is
synthesised. **Rungs 1–5 are the precondition for using the hands at all**, and
the sub-ladder below assumes them closed.

Owned by **`method`** (6.1), **`synthesis-planner`** (6.2, embodied),
**`runner`** (6.3–6.4, embodied) and **`verifier`** (6.5).

### 6.1 · A selection rule stated before anything is made

**The problem.** "Make the top-scoring compounds" is not a rule: it selects for
whatever the scoring function is wrong about, which is precisely the quantity
rung 5 says has not improved in decades.

| | |
|---|---|
| **solved when** | the selection rule is published before a batch — how many, chosen how, with what diversity and what deliberate coverage of *uncertain* predictions rather than confident ones — and the batch's composition can be checked against it afterwards |
| **blocked by** | main rungs 1–5. Selecting from a leaked, unscaled, irreproducible pipeline spends chemistry on noise |
| **unblocks** | everything below. A batch with no stated rule cannot produce an interpretable hit rate, only an anecdote |
| **what would reorder it** | nothing. This is the rung that makes the loop an experiment rather than a shopping list |

> **Deliberately include the uncertain.** A batch of only confident predictions
> confirms what the model already believes and teaches it nothing; the
> informative compounds are the ones the model cannot call.

### 6.2 · Makeability decided before cost is committed

**The problem.** A generative model proposes molecules that cannot be made.
Discovering that on the bench is the expensive way to learn it, and reagents
do not come back.

| | |
|---|---|
| **solved when** | every selected compound has a retrosynthetic route with stated steps, availability and cost, and compounds without one are excluded **before** the batch is committed, with the exclusion rate reported as a property of the generator |
| **blocked by** | 6.1 |
| **unblocks** | 6.3 |
| **what would reorder it** | nothing. The exclusion rate is itself one of the most useful numbers a generative method can be given |

### 6.3 · Synthesis, inside an envelope

**The problem.** The first irreversible step. A wrong file is reverted; a
consumed reagent is not, and an instrument can be damaged by a plan that looked
fine.

| | |
|---|---|
| **solved when** | the batch is synthesised on a platform under a declared **physical envelope** (§13i) — what may be handled, in what quantities, at what temperatures, and what must never be attempted — with yields and failures recorded as data rather than as setbacks |
| **blocked by** | 6.2 |
| **unblocks** | 6.4 |
| **what would reorder it** | nothing |

> **The envelope is the owner's and is signed by the synthesis and assay lead**
> — the fourth panel role, which exists only because this group has hands
> (§13j). An agent may not widen it, propose a wider one, or treat a successful
> run as an argument for a larger one.

### 6.4 · Assay, with its own controls

**The problem.** An assay result is a measurement with its own error, and a
loop that treats it as ground truth will chase assay noise as though it were
chemistry.

| | |
|---|---|
| **solved when** | every batch carries positive and negative controls and replicate measurements, the assay's own variability is reported, and a difference smaller than it is not treated as a difference |
| **blocked by** | 6.3 |
| **unblocks** | 6.5 |
| **what would reorder it** | nothing. This is pill camera's rung 2 wearing different clothes, and the same failure — believing effects inside the noise — is available here at much greater cost |

### 6.5 · The prospective number, reported against the prediction

**The problem.** The whole point. A method that wins retrospectively has not
been shown to find anything, and the comparison is only worth something if it
is published when it is unflattering.

| | |
|---|---|
| **solved when** | the prospective hit rate is reported against what the retrospective evaluation predicted, **including and especially when it is worse**, and the negatives enter the corpus of main rung 4 rather than being discarded |
| **blocked by** | 6.4 |
| **unblocks** | the only claim the field cares about, and — by feeding negatives back — main rung 5 |
| **what would reorder it** | nothing |

> **The loop closes here or it is not a loop.** Compounds that did not bind are
> the data main rung 4 says the field lacks; a make-test cycle that publishes
> only its successes recreates the censored literature it was built to escape,
> at the cost of real reagents.

### The order, and what it says

```
6.1 selection rule ─> 6.2 makeability ─> 6.3 synthesis ─> 6.4 assay + controls ─> 6.5 the number
   (needs main 1-5)                        (a body,          (a body)              (fed back
                                            envelope)                               to main 4)
```

**Two of the five are physical and irreversible, and the three around them are
what make those two safe.** The sub-ladder is arranged so that the expensive
steps are entered with a stated rule, a route, an envelope and controls — and
so that the loop's output is a number the field does not currently have, plus
the negatives it has never published.

## The four layers

| layer | this field's instance |
|---|---|
| **Principle** | A docking score is not an affinity, and a random split of an analogue series is not a validation |
| **Digital twin** | The library model — fingerprint space, property-matched decoy generation, and the chemical-cluster structure that defines what "a series" means. This is what makes the split honest, and the agent cannot touch it |
| **Benchmark** | DUD-E, 15,288 molecules across 6 targets, queries drawn from whole clusters with the rest withheld, scored by EF@1% against a property-only floor and a stated ceiling  — and its reference method is allowed to fail — it did, once the analogue leak was closed and the task got harder |
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
| literature | reasoning | prior work, with citations | refuses a claim it cannot cite, and never reads while the method is being written |
| twin | reasoning | the library and decoy model | refuses to be graded outside the regime it declares valid |
| corpus | reasoning | DUD-E across six targets | refuses when the corpus is absent, **naming the fetch command** rather than substituting generated data |
| method | reasoning | the candidate solution | the only member that writes the thing being judged |
| runner | reasoning | compute | refuses a run whose cost or placement it cannot state |
| verifier | judging | the benchmark | refuses to judge against a criterion written after the result; refuses an enrichment that does not clear the property-only floor, or one computed before the ceiling is known |
| reproducer | judging | published artifacts alone | refuses a result it cannot re-run from what was published — catching the result that only exists on the machine that made it |
| teacher | judging | the owner's own check | refuses to report a result without the query-to-test analogue similarity |
| writer | judging | the field page and the paper | writes last, from the record, never from intent |
| **synthesis robot** | **embodied** | reagents and glassware | refuses to start a synthesis without a grant naming it |
| **assay robot** | **embodied** | plates, cells, the reader | refuses to re-run a failed assay silently; a discarded plate is a recorded event |
> **Nine members are the floor, not the design.** A field may add; it may not
> remove. An agent whose manifest omits the **verifier** or the **twin** is not a
> research agent with fewer parts — it is *a method with a scoreboard*. Those two
> are deliberately not the worker's: they answer *"what should this produce"* and
> *"did it"*, and an agent owning both can pass any benchmark it likes by moving
> one of them.


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

## 13. The field page

| Layer | This field |
|---|---|
| **L1 · principle** | binding is a free-energy difference, and structure determines it. Every scoring function in the field is an approximation to one quantity that is, in principle, computable |
| **L2 · spec — the digital twin** | the physics-based free-energy model (FEP/MD), with docking as its cheap approximation. **Where it stops:** protein flexibility, explicit water, entropy and protonation — and it stops there expensively, because those are exactly the terms that decide the cases people care about |
| **L3 · benchmark** | DUD-E, 15,288 molecules across 6 targets, **series-disjoint** with property-matched decoys (rung 1), reported as enrichment **with its ceiling and its property-only baseline** (rung 2) |
| **L4 · solution** | EF@1% of **33–56, which is 45–77% of the achievable ceiling and 1.5×–3.5× the property baseline** across twelve seeds, measured 2026-08-11. Three numbers because the first one alone would have been unreadable |

**This field has the best-specified twin of the seven and the widest gap between
the twin and the benchmark.** Free energy is computable and too expensive to
compute at library scale, so the whole field lives in the approximation — and
rung 5, the scoring-function ceiling, is that gap stated as a problem.

**Not built:** no page on physicsworldmodel.org. The ceiling and baseline
computations exist in the benchmark and are not published as reusable artifacts,
which is what would let other people's numbers be read on the same scale.

## 15. The teacher

The path from "knows what a molecule is" to checking one result:

1. **L1** — why binding is a free-energy difference, and why a score is an
   approximation rather than a measurement.
2. **L2** — dock one known ligand into one known target. Then change its
   protonation and dock it again. Watch the score move.
3. **L3** — run the benchmark with a random split, then with the series-disjoint
   split. **Watch the enrichment collapse.**
4. **L4** — read **33–56** against its ceiling and against the property-only
   baseline, and find the published methods that do not beat the baseline.

**Steps 2 and 3 are two different lessons and both are load-bearing**: the
preparation lesson is why results are irreproducible, and the split lesson is
why the literature's numbers are too good. A learner who has produced both can
read a paper in this field usefully, and that is a large return on an afternoon.

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
