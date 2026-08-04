# The drug design agent — how to design it

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
