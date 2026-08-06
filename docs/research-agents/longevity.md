# The longevity agent — how to design it

| | |
|---|---|
| **corpus** | NHANES with the CDC public-use **linked mortality file** — clinical and laboratory markers with real follow-up |
| **reference method** | **not built** |
| **the number that matters** | whatever it adds over **age and sex**, which is the whole question |

> **The finding this page is built around — and it is about the system, not the
> biology.** This agent exists because [`reverse-aging.md`](reverse-aging.md)
> could not answer its own most important question. That agent's benchmark has
> chronological age as its answer key, so "is this person ageing faster" and
> "did this intervention help" are unscoreable in it — not hard, *unscoreable*,
> because settling them would require changing the answer key, and the answer
> key is the one thing that may not change. By the test in
> [`lifecycle.md`](lifecycle.md) that makes this a **different field**, and
> fission is the good ending rather than a failure.

## How experts guide this into a self-aware, self-improving agent — and then into collapse

The whole arc, in one place, because the sections that follow only make sense
inside it. The mechanism is shared and lives in [`lifecycle.md`](lifecycle.md);
what changes between fields is what the experts had to decide, and what the
agent is not allowed to buy improvement with.

**1 · Experts write the criterion, before the agent exists.** The field's
experts set the scope and decide that **age and sex are the floor**, not covariates, and that validation is across survey cycles. This is the load-bearing human
act: the agent inherits what counts as an answer here and may never change it.
An agent that could would be choosing its own benchmark.

**2 · The agent becomes self-aware in the only sense that is checkable.** Not
introspection — bookkeeping. It holds a measured record of what it has tested
and, kept strictly apart, what it has **not**: that nothing is built yet, which is itself the honest first entry in its self-model. Unmeasured reads as
unmeasured, and it costs something to write, because a self-model where
"unmeasured" is free empties its own queue. The gaps are the queue: where the
evidence is thinnest is where the next self-directed night goes.

**3 · It improves itself, bounded by something it cannot move.** Propose →
measure → an authority signs → adopt. It may change its method, its plan and its
own parameters; it may never change the benchmark, the metric or the verifier.
In this field the binding guardrail is **the age-and-sex floor: a mortality model that does not clear it has predicted that older people die sooner**. That boundary is the
entire safety argument: an agent that can move what judges it does not improve,
it drifts, and it reports success the whole way.

**4 · Verification is handed over, in stages, and never all at once.** A person
signs every adoption today. Later, independent verifiers judge against criteria
fixed *before* the result existed — discrimination and calibration are recomputable from predictions and follow-up by anyone holding both — and a person audits a
sample. Later still, other fields' agents reproduce claims, which is the
strongest check available because agreement between two agents sharing a
codebase is nearly free. Experts keep scope throughout: *"is this worth
researching"* is not a measurement and no verifier answers it.

**5 · The field collapses.** Human verification goes to zero — either because
everything checkable has been checked and machines check faster than people can
follow, or because nobody cares any more. Both look identical from inside. What
tells them apart is whether anyone acts on the results.

## How this field ends

**By saturation, slowly, or not at all.** Follow-up time is the binding
constraint and it cannot be compressed, so this field moves at the speed of
cohorts rather than compute.

**Retired from research, not from service.** A validated risk model keeps being
useful to clinicians and actuaries long after the frontier closes.

**Candidate fission: mechanism rather than prediction.** The moment the question
becomes *why* a marker predicts — and whether changing it changes the outcome —
no observational benchmark can score it. That needs an interventional design,
which is a different twin, a different answer key, and therefore a different
field again.

**Status: design. Nothing is built.** No corpus fetcher, no benchmark, no
reference method, and it is not in the agent registry. Everything below is
written in the conditional because that is what it is. An architecture
described in the present tense is a claim.

---

## Why it is a separate agent and not a bigger reverse-aging

Reverse aging predicts a number already on a birth certificate. Its honest risk,
stated on its own page, is collapse by indifference: *a field of clocks that
predict chronological age ever more precisely and never connect to health is
solving a problem nobody needed solved.*

The escape is not a better clock. It is a different answer key.

| | reverse aging | longevity |
|---|---|---|
| **answer key** | chronological age, known at fitting time | an **outcome**, which does not exist at fitting time and must be waited for |
| **twin** | the methylome — batch and cell composition | the cohort in time — competing risks, censoring, survey design |
| **what beating the baseline means** | beating the training mean age | beating **age and sex**, which is a far harder floor |
| **failure it exists to catch** | a clock reading blood composition | a model reading *frailty already visible to a clinician* and calling it prediction |

Neither inherits the other's benchmark. It may freely inherit methods, data
handling and tools — and it should inherit the composition guardrail, because
the same confound appears wherever bulk biology stands in for a person.

## Scope, and the experts who set it

**Current scope.** Prediction of mortality and healthspan from clinical,
laboratory and questionnaire markers in a cohort with real follow-up, validated
across survey cycles that the model was not fitted on.

**Out of scope, and deliberately.** Any recommendation to an individual, any
intervention claim, and any supplement, protocol or product. This agent may say
what predicts; it may never say what to do about it. That line is not a
limitation to be relaxed later — it is what keeps the field from becoming
marketing.

| expert role | what they decide here |
|---|---|
| **an epidemiologist** | the survey design, weighting, and what a cycle-disjoint split can and cannot support |
| **a biostatistician of survival data** | competing risks, censoring, and calibration — the three this field most often gets wrong |
| **a geriatrician or clinician** | what healthspan means operationally, and whether a marker is prediction or is simply visible frailty |
| **a consent and data-use officer** | what linkage is permitted, which is the binding constraint rather than method |

**No expert is currently assigned.** These are roles, not people, and this
repository names no individual.

## The problem ladder

Ordered by dependency. **The order is the topological order of what blocks
what**, with cost breaking ties.

| # | problem | **solved when** | why it is placed here | state |
|---|---|---|---|---|
| 1 | **A corpus with real follow-up** | `mortality-linked records load, with follow-up time and status per person, from a source anyone can fetch` | everything here is unanswerable without an outcome. This is the exact thing reverse aging is blocked on, and it is rung 1 because nothing above it can be measured | open |
| 2 | **Age and sex as the floor, not a covariate** | `every reported metric appears beside the same metric from an age-and-sex-only model` | a mortality model that does not beat age and sex has predicted that older people die sooner. Most published risk scores are never asked this | open |
| 3 | **Cycle-disjoint validation** | `performance is reported on survey cycles that contributed nothing to fitting or selection` | assay methods, protocols and populations drift between cycles; a random split reads the era | open |
| 4 | **Competing risks and censoring, explicitly** | `the estimate changes when competing risks are modelled, and the change is reported` | in an older cohort, death from another cause is not censoring, and treating it as such biases every estimate the same way | open |
| 5 | **Calibration, not discrimination alone** | `predicted and observed survival agree within a stated tolerance, plotted, not summarised` | a c-index ranks; it never says how much. A decision needs the magnitude | open |
| 6 | **Healthspan, not just lifespan** | `a disability or morbidity endpoint is predicted and reported separately from death` | living longer and living well are different outcomes, and conflating them is how this field flatters itself | open |
| 7 | **Marker sets that add over a blood panel** | `a candidate marker set beats a standard clinical panel on held-out cycles, or is reported as not adding` | the commercial claim in this field is that a new measurement adds information. It is rarely tested against the cheap one | open |
| 8 | **Intervention response** | `a repeated measure moves in the predicted direction after a change, in a design that could have shown it did not` | the question everyone wants and the one that needs longitudinal data plus a design that can be wrong | blocked |

> **Blocked by, and unblocks.** The order *is* the dependency graph: each rung
> is blocked by the ones above it and unblocks the ones below. They are not
> itemised per rung yet, which is a gap against the spec rather than a claim
> that the graph is a chain.
>
> **Evidence that would reorder it.** a cohort where age and sex are unavailable would move rung 3 above rung 2; evidence that cycle drift is negligible would demote rung 3. A ladder nobody can argue with is a
> ladder nobody checked.

> **"Solved when" is the entry fee.** A problem with no measurement that would
> settle it is a research interest, and interests belong in the charter.
>
> **A rung is closed by the registry, not by the agent.** "Solved" means a
> benchmark has a published solution that meets it, runnable by anyone. The
> agent may propose that a rung is closed; the closing is an artifact.
>
> **Evidence that would reorder it.** A cohort where age and sex are unavailable
> would move rung 3 above rung 2; evidence that cycle drift is negligible would
> demote rung 3.
>
> **The failure this ladder is built against is starting at rung 7.** Marker
> panels are the fundable, publishable, sellable rung, and every one of them is
> uninterpretable until rungs 2 and 3 hold.

## The four layers

| layer | this field's instance |
|---|---|
| **Principle** | Predicting death is easy and mostly redundant. The only interesting quantity is what a marker adds **over age and sex** — stated so it can be wrong, and it can: a marker set that adds nothing fails |
| **Digital twin** | The cohort in time: enrolment, survey weighting, follow-up, censoring and competing risks. It stops being valid outside the sampled population — a national survey does not transport to a clinic, and the twin says so |
| **Benchmark** | NHANES with the linked mortality file, cycle-disjoint splits, discrimination **and** calibration, against an age-and-sex floor, with a reference method that is **allowed to fail** |
| **Solution** | A survival model over clinical and laboratory markers, with its shrinkage and marker set as the declared knobs |

> **A reference method that cannot fail is not a benchmark.** This one should be
> expected to fail rung 2 on its first honest attempt, because beating age and
> sex is genuinely hard, and a first-try pass would be evidence the floor was
> set too low.

## The group

The nine-member floor applies here as everywhere. The **twin** and the
**verifier** are not the worker's, for the usual reason.

| member | kind | acts on | its refusal |
|---|---|---|---|
| literature | reasoning | prior work, with citations | refuses a claim it cannot cite, and never reads while the method is being written |
| twin | reasoning | the cohort-in-time model | refuses to be graded on a population outside the survey's sampling frame |
| corpus | reasoning | NHANES + linked mortality | refuses when the linkage is absent, **naming the fetch command**, and never substitutes simulated follow-up |
| method | reasoning | the survival model | the only member that writes the thing being judged |
| runner | reasoning | compute | refuses a run whose cost or placement it cannot state |
| verifier | judging | the benchmark | refuses any result not reported beside the age-and-sex floor |
| reproducer | judging | published artifacts alone | refuses a result it cannot re-run from what was published |
| teacher | judging | the owner's own check | refuses to report a hazard ratio without the absolute risk difference beside it |
| writer | judging | the field page and the paper | writes last, from the record, never from intent |
| **collection robot** | **embodied** | donors and samples | refuses to collect outside consented scope |

> **Nine members are the floor, not the design.** A field may add; it may not
> remove. An agent whose manifest omits the **verifier** or the **twin** is not a
> research agent with fewer parts — it is *a method with a scoreboard*.

> **What a body does not fix, and here it is the whole field.** Longevity is
> gated on *follow-up time*. A robot can draw and process samples faster; it
> cannot make anyone older, and it cannot shorten a cohort's follow-up by a
> single day. This is the clearest case in the programme of a field where
> throughput is not the constraint.

## At AGI and ASI

**On demand.** "Does this marker set add anything over age and sex in a cohort
it was not fitted on?" The expected answer, most of the time, is *no* — and an
agent that cannot deliver that answer comfortably is not useful here.

**Autonomous.** Re-validating published longevity and biological-age scores
against an age-and-sex floor on cycle-disjoint splits. Very few have been.

**How a person verifies.** Ask for the age-and-sex-only model's number. If it is
absent, nothing else on the page can be interpreted. Then ask for calibration,
then ask which cycles were held out and whether they were chosen before the
model was.

**How sub-agents would verify.** A *floor* verifier fitting age and sex
independently; a *split* verifier confirming cycle disjointness; a *survival*
verifier re-deriving the estimate under competing risks; and a *leakage*
verifier checking that no post-outcome variable entered the features — the
characteristic fatal error in outcome modelling.

**How it teaches.** The curriculum is the evidence chain. The transferable
lesson is the one this field most needs: **a hazard ratio without an absolute
risk difference is unreadable**, and a model that beats nothing but chance is
routinely reported as though it beat medicine.
