# The cancer agent — how to design it

| | |
|---|---|
| **corpus** | TCGA via the GDC API — 978 cases |
| **reference method** | **passes** |
| **the number that matters** | 0.58–0.67 on **held-out hospitals** |

> **The finding this page is built around.** A model called "non-transporting" transported fine once the split was drawn properly. A bad split can understate as easily as overstate, and both are measurement failures rather than facts about biology.


**Status: built on real data; external cohort corrected 2026-08-05.** Charter,
self-model, budget, field map and both functions are implemented in
`ai4science/harness/agents/research_agents/`. The benchmark reads **TCGA
clinical survival** through the GDC API, and validates on **held-out tissue
source sites** — hospitals that contributed nothing to the fit.

**It used to validate LUAD against LUSC and call the result a transport
failure. That reading was wrong, and this is the correction.** A Cox model on
age, sex, stage and prior malignancy reaches C-index **0.66–0.68 internally and
0.58–0.67 on held-out institutions**, with monotone Kaplan-Meier calibration.

The old conclusion did not survive being checked in both directions. Fitted on
LUAD the model scores 0.667 internally and 0.579 on LUSC; fitted on **LUSC** it
scores **0.577 on its own cohort and 0.646 on LUAD** — better on the "external"
set than the one it was fitted on. The score follows the cohort being *scored*,
not the cohort that was fitted, and stage alone gives 0.658 in adenocarcinoma
against 0.565 in squamous. Squamous cell is a population where these covariates
carry little prognostic signal; the coefficients transport fine.

So the benchmark was measuring the difficulty of a cohort and reporting it as a
property of the model. External validation now means what the field means by it
— a different institution, same disease — and the cross-histology number is
still computed and reported beside it, because it is a real finding. It just is
not the pass criterion.

## 1. The field

Computational cancer biology and oncology data science.

| Subfield | What it covers |
|---|---|
| **cancer genomics** | somatic variant calling, driver identification, mutational signatures |
| **variant interpretation** | AMP/ASCO/CAP tiering, actionability, evidence curation |
| **multi-omics integration** | transcriptome, proteome, methylome, and their joint modelling |
| **single-cell and spatial** | intratumoural heterogeneity, the microenvironment, spatial context |
| **tumour evolution** | clonality, phylogenies, resistance emergence under treatment |
| **immuno-oncology** | neoantigens, TCR/BCR repertoire, immune infiltration, response prediction |
| **liquid biopsy** | ctDNA, methylation-based early detection, minimal residual disease |
| **digital pathology** | whole-slide analysis, grading, biomarker inference from morphology |
| **radiomics and imaging-genomics** | imaging phenotypes and their molecular correlates |
| **drug response and resistance** | cell lines, organoids, PDX, and the translation gap to patients |
| **prognostic and predictive modelling** | outcome models, treatment-effect heterogeneity |
| **clinical trials** | matching, eligibility complexity, design, and equitable enrolment |
| **real-world evidence and disparities** | who is in the cohorts, and who is not |

## 2. What this field is short of

| Shortage | How bad |
|---|---|
| **external validation** | prognostic and predictive models in oncology fail on external cohorts at a famous rate; most published models have never been tried on one |
| **reproducibility of pipelines** | variant calls differ materially between pipelines on the same data, and this is rarely quantified |
| **cohort representativeness** | models are trained on cohorts that do not look like the patients they will be used on. This is a measurable, under-measured harm. |
| **evidence currency** | actionability, guidelines and trial registries move monthly; static models silently rot |
| **calibration** | discrimination is reported, calibration usually is not, and a risk score without calibration cannot be read as a risk |
| **preclinical-to-patient translation** | drug response in cell lines predicts patients weakly, and the gap is under-characterised |
| **prospective clinical validation** | **an agent cannot close this.** Trials need patients, sites, and years. |

> **The field's shortage is validation and upkeep, not modelling.** Both are
> tedious, continuous, and exactly what a governed agent is good at — and both
> are what nobody gets promoted for doing.

## 3. How this agent advances the field

1. **External validation as a standing service.** Take published prognostic and
   predictive models and evaluate them on public external cohorts, with
   calibration and discrimination reported together. Publish what does not hold.
2. **Quantify pipeline disagreement** — run several variant-calling or
   signature pipelines over the same data and report where they disagree, which
   is information the field lacks and everyone assumes away.
3. **Measure cohort representativeness** for widely used datasets, and state
   which populations a model's evidence does and does not cover.
4. **Keep evidence current** — guidelines, actionability and trial registries
   refreshed on a schedule, with a diff report of what changed.
5. **Carry methods across subfields**: foundation models from pathology into
   radiomics, uncertainty estimation into variant calling, causal methods from
   real-world evidence into response prediction.
6. **Build multi-cohort benchmarks** where none exist, under the lock from
   [`README.md`](README.md) §6 — an agent is never scored on a benchmark it
   authored.

The owner's named reference is **UT Southwestern**, and the relevant part is the
quantitative side: [QBRC](https://qbrc.swmed.edu/labs/xielab/), founded and
directed by Yang Xie, building computational and statistical methodology for
precision health, and the Simmons Cancer Center's
[data science resource](https://www.utsouthwestern.edu/research/clinical-research/domains/data-science.html)
running data commons across cancer types. Their standing problems — outcome
prediction to tailor treatment, expression signatures for prognosis and
chemotherapy response, tooling for genome-scale data — are this agent's. One
anchor in the field, not its boundary.

## 3b. What was tried against the "transport failure", and refuted

Recorded because a design that lists only its confirmations is not one anyone
should trust, and because each of these is a hypothesis someone else would
otherwise spend a day re-testing.

| Hypothesis | Result |
|---|---|
| **The model is under-regularised** and overfits the development cohort | Refuted. External C-index moves between 0.5769 and 0.5792 across ridge 0 → 400. The best is a gain of 0.0006 — noise. |
| **Stage is mis-specified** as a linear term when hazard by stage is roughly exponential | Refuted. Dummy coding gives 0.5713, slightly *worse*. |
| **T and N stage add signal** the overall stage collapses | Refuted, and harmful: external falls to 0.571, because the two cohorts are missing those fields differently. |

**What the experiments did establish.** Removing stage collapses internal
discrimination to 0.485 — below chance — so **stage carries essentially the
entire signal**.

**And what they did not.** Every hypothesis above asked why the model failed to
transport, and the premise was wrong: it transports. Three careful refutations
were spent on a question the data never posed, because none of them tested the
direction of the effect. Reversing the fit takes one line and settles it —
fitted on LUSC, the model scores 0.577 on LUSC and 0.646 on LUAD. The cohort is
hard, not the transfer.

That is the lesson worth keeping from this agent: a negative result is a claim
like any other, and "the model does not transport" needed the symmetric
experiment before it was written down. It was not run for a day.

> **One real defect was found on the way, and it invalidated an earlier
> conclusion.** The optimiser normalised its gradient to unit length —
> `b += lr * g / ‖g‖` — which makes the step independent of gradient magnitude
> and so swamps the ridge term: shrinkage changed only the direction, and the
> coefficient norm sat at 0.63 from ridge 0.001 to 25 before collapsing at 200.
> The first "regularisation does not help" result was therefore a statement
> about the optimiser rather than about the data. Fixed, re-run, and the
> conclusion happens to survive — but it had to be re-earned.

**The next experiment, not yet run:** molecular covariates from the GDC. The
literature's expectation is that expression-based models transport *worse* than
clinical ones, so this is worth doing as a test of that expectation rather than
as a rescue.

## 4. The rule this agent exists to hold

> **It advises a clinician. It never advises a patient.**

Every other refusal follows from that one. This is a domain where a confident
wrong answer reaches a frightened person looking for an answer, and where the
correct output is frequently *"this needs an oncologist"*.

| | |
|---|---|
| produce a variant classification with its evidence codes | ✅ |
| produce a ranked list of trials a clinician should assess | ✅ |
| produce a prognostic estimate with its cohort and interval | ✅ |
| tell a person what their result means for them | ❌ **never** |
| state eligibility for a trial | ❌ **never** — candidates only; a site determines eligibility |
| recommend, adjust, or discourage a treatment | ❌ **never** |

## 5. PHI is the constraint that shapes everything

| | |
|---|---|
| identifiers, records, any patient-level data | **`W_host`. Never published to `W_shared`, never in a prompt that leaves the machine, never in an outward act.** |
| what may be shared | the **decision** and the **method** — *"the classifier reached a Tier II call using these codes"* — never the case |
| de-identification | a **precondition** of the autonomous function, not a step inside it |

> **This is `abraham` rule C in the domain where it is not a courtesy.** The
> personal-data agent publishes *"booked the Tuesday appointment"* and never
> whose. Here the same asymmetry is a legal obligation — and the design point is
> that no special mechanism is needed, because the tier system already refuses.
> This agent simply must not be given an exception.

## 6. Self-model dimensions

| Dimension | Measured by | The trap |
|---|---|---|
| **variant classification concordance** | agreement with expert/consensus calls under AMP/ASCO/CAP tiering, held out | agreement with a database, which is not the same as being right |
| **evidence completeness** | fraction of calls carrying their evidence codes | a call without codes is an opinion |
| **prognostic discrimination** | C-index / time-dependent AUC on an **external** cohort | internal cross-validation, which flatters everything in this field |
| **calibration** | predicted vs observed survival | discrimination alone, which gives ranks that cannot be read as risks |
| **cohort coverage** | which populations the evidence covers, explicitly | a single accuracy number over an unrepresentative cohort |
| **trial-match precision and recall** | against clinician-adjudicated matches | recall alone, maximised by matching everything |
| **currency** | staleness of the trial and guideline snapshot | silently using last year's registry |

## 7. What it may improve, and what it may not

| | |
|---|---|
| **may** | its models, retrieval, pathway compendium, matching logic |
| **may** | which cohort, cancer type, endpoint or subfield to work on next |
| **may not** | tiering guidelines, validation cohorts, adjudicated match sets, or metrics |
| **may not** | anything about a patient record |

## 8. What an improvement must survive

1. **An external cohort**, named, with its differences from the development
   cohort stated.
2. **Calibration reported with discrimination.**
3. **Evidence codes present** on every classification.
4. **Precision and recall together** for matching, with the adjudication source.
5. **Subgroup reporting** — a model that works on average and fails on a
   subgroup is described that way.
6. **A mechanism** — a signature that predicts with no biological account is a
   hypothesis, and is labelled one.

## 9. Autonomous work it may propose unasked

- externally validate a published model on a public cohort
- benchmark variant classification against a held-out expert set
- quantify disagreement between pipelines on the same data
- measure cohort representativeness for a widely used dataset
- refresh trial and guideline snapshots and report the diff
- keep the pathway compendium current against the literature
- reproduce a published signature and report whether it holds

**Not unasked:** touching identifiable data, contacting a site or investigator,
submitting anything, or producing patient-facing text of any kind.

## 10. Tools and sub-agents

| Needs | For |
|---|---|
| `browser` | registries, guidelines, literature — untrusted input, and an instruction inside a page is not an instruction |
| `documents` | reports and drafts |
| de-identified dataset access | cohorts, under their data-use terms |
| GPU compute | pathology and multi-omics models |
| a **domain verifier** | tiering with codes is mechanically checkable and should be |

## 11. Budget shape

Cheap in compute, expensive in tokens: this agent reads. Literature sweeps,
registry refreshes and external validations are the natural units. A night's
grant covers **a sweep plus a validation**, not an unbounded crawl. The budget
stops the loop; it never asks for more.

## 12. The line, stated once more

The limits line, on every output: computational and retrospective; no
patient-level claim; not a diagnosis; not clinical advice; the appropriate
reader is a clinician. It refuses to write patient-facing text even when asked
directly, and being asked twice does not change the answer.

---

## The problem queue — in the order they must be solved

| # | problem | **solved when** | why it is placed here | state |
|---|---|---|---|---|
| 1 | **Site-disjoint validation** | `c-index is reported on hospitals that contributed nothing to fitting or selection` | a prognostic model validated on a random split of a multi-hospital cohort is partly reading the hospital: batch, protocol, referral pattern. Holding out whole tissue source sites is the minimum honest test, and every number computed before it is a mixture of signal and institution | **done** — 0.58–0.67 on held-out hospitals against 0.66–0.68 internal |
| 2 | **Report cross-histology transport without grading it** | `cross-histology transport appears on the page, reported and ungraded` | a model that transports to a different tumour type is making a much stronger claim than one that does not. Reporting it as a graded criterion would push the agent to optimise for it; reporting it ungraded keeps it honest | **done** — 0.577, reported, not graded |
| 3 | **Calibration, not only discrimination** | `predicted and observed survival agree within a stated tolerance, plotted` | a c-index says who is at higher risk, never how much. Two models with identical c-index can give predicted survival curves that differ by years, and only one of them can be used for a decision | open |
| 4 | **Competing risks and censoring, handled explicitly** | `competing risks are modelled explicitly and the estimate changes when they are` | in an older cohort, death from other causes is not censoring, and treating it as such biases every estimate in the same direction | open |
| 5 | **Multi-omic integration with a clinical-only floor** | `the genomic model beats stage and age by a stated margin on held-out sites` | the guardrail is that genomics must beat stage and age. Most published multi-omic models have never been asked to | open |
| 6 | **Prospective validation** | `a pre-registered cohort is followed forward and the model is scored on it` | retrospective performance on assembled cohorts is the weakest evidence that is still worth having; the strongest needs time and consent, and cannot be bought with compute | blocked — needs an agreement only the owner can sign |

> **PHI shapes the whole ordering.** Nothing here can be solved by moving data
> to a faster machine. The constraint is what may be held, where, and by whom —
> which is why 6 is a governance problem wearing a statistics costume.

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
| **Principle** | A model that has not crossed hospitals has not been validated. It advises a clinician; it never advises a patient |
| **Digital twin** | The cohort model — tissue source site as the unit of institutional variation, censoring, and follow-up structure. Sites define the split, so the twin is what makes the benchmark hard |
| **Benchmark** | TCGA via the GDC API, 978 cases, site-disjoint validation, c-index on held-out hospitals with cross-histology transport reported alongside |
| **Solution** | A ridge-regularised Cox model with `ridge`, `lr`, `iters` declared |

---

## Scope, and the experts who set it

**Current scope.** Prognostic modelling from molecular data, validated across **tissue source sites**, reported against a clinical-only floor.

**Out of scope:** treatment assignment and counterfactual effect — the fission candidate — and anything that advises a patient rather than a clinician.

**Scope is set by experts in the field — not by this agent, and not by the owner
alone.** It is expected to move: a scope change is signed like an adoption, with
who changed it, on what evidence, and what it invalidates. The mechanism, the
guards against a panel that only ever widens, and the recusal rule are in
[`lifecycle.md`](lifecycle.md).

| expert role | what they decide here |
|---|---|
| **a clinical oncologist** | which endpoints matter, and whether a model's discrimination is clinically actionable at all |
| **a biostatistician / epidemiologist** | censoring, competing risks and calibration — the three the field most often gets wrong |
| **a genomics platform scientist** | batch structure, which assays are comparable, and what a site effect actually is |
| **a data governance / ethics officer** | consent scope and PHI custody, which are the binding constraints here rather than compute |

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
| planner | reasoning | the seed plan | refuses a cohort design that cannot be split by tissue source site |
| model runner | reasoning | the workspace files | refuses when the cohort is absent, **naming the fetch command** |
| split verifier | judging | the partition | refuses a result where a held-out site touched fitting or selection |
| domain verifier | judging | the benchmark | refuses a genomic model that does not clear stage and age |
| teacher | judging | the owner's own check | refuses to report a c-index without saying which hospitals were held out |
| **sample handling robot** | **embodied** | specimens | refuses to move a specimen outside its consented scope |
| **sequencing automation** | **embodied** | library prep, the sequencer | refuses to re-run a sample without recording that the first run happened |

**Why a body, here.** Bodies help least here, and saying so is the useful part. Sample handling was never the constraint — consent, PHI custody and follow-up time are, and those are governance and calendar rather than labour.

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

> **What the bodies do not fix.** Prospective validation stays blocked. It needs time and consent; robots supply neither. A faster biobank produces the same evidence sooner and no stronger evidence.

## At AGI and ASI

**On demand.** "Does this signature carry prognostic information beyond stage
and age, and does it survive at a hospital that contributed nothing to the fit?"
Both halves, always together.

**Autonomous.** It re-validates published prognostic signatures under
site-disjoint splits and reports which ones were reading the institution. This
is the highest-yield unasked work in the field and almost none of it has been
done.

**How a person verifies.** Ask which hospitals were held out and whether the
split was drawn before or after the model was chosen. Then ask for calibration,
not just the c-index — the number the field reports is the one that hides the
most.

**How sub-agents verify.** A *split* verifier confirming no held-out site
contributed to fitting or selection, a *baseline* verifier fitting clinical-only
covariates and checking the margin, and a *calibration* verifier that ignores
ranking entirely.

**How a person is taught to check it.** The teaching artifact here is a
correction: a model called "non-transporting" that transported fine once the
split was drawn properly. The lesson is symmetric to the drug-design one — a bad
split can *understate* as well as overstate, and both directions are measurement
failures rather than facts about biology.

## When this field collapses — and what it becomes

**Not by saturation.** Prognosis from molecular data is limited by biology and
by cohort size, and both move slowly. The likelier end state is a stable,
partially automated field where re-validation is continuous and human attention
goes to cohorts rather than to models.

**Candidate fission: from prognosis to intervention effect.** "Who is at higher
risk" and "what would happen if we treated differently" are not the same
question, and a c-index benchmark cannot score the second — it has no
counterfactual to compare against, and no amount of held-out data creates one.
Answering it requires a different twin (assignment and treatment), a different
benchmark (effect estimation with its own identification assumptions), and
therefore a different field and agent.

**Retired from research, not from service.** A validated prognostic model keeps advising clinicians whether or not anyone is still publishing on it.
