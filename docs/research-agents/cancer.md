# The cancer agent — how to design it

**Status: built and running on real data, 2026-08-04.** Charter, self-model,
budget, field map and both functions are implemented in
`ai4science/harness/agents/research_agents/`. The benchmark reads **TCGA
clinical survival** through the GDC API — 491 TCGA-LUAD cases to develop on,
487 TCGA-LUSC as an external cohort.

**Its reference method fails, and that is the result.** A Cox model on age,
sex, stage and prior malignancy reaches C-index **0.668 internally and 0.577
externally**: it discriminates on its own cohort and does not transport across
histologies. Calibration is measured by Kaplan-Meier at a fixed horizon and is
monotone. Adding T and N stage was tried and made the external number *worse*
(0.571), because the two cohorts are missing those fields differently.

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

## 3b. What was tried against the transport failure, and refuted

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
entire signal**, and it is stage's prognostic weight that fails to transport.
Adenocarcinoma and squamous cell have different stage-specific survival. That is
biology, not a specification defect, and no amount of shrinkage or recoding
reaches it.

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
