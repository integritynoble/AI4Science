# The reverse-aging agent — how to design it

| | |
|---|---|
| **corpus** | GEO GSE40279 — 656 whole-blood samples, ages 19–101, four institutions |
| **reference method** | **13 of 28** seed-varied splits |
| **the number that matters** | **55%** of the clock's gain is bulk structure |

> **The finding this page is built around.** The benchmark accepted a seed and ignored it, so every seed produced identical data — a paired comparison with zero spread by construction, reporting **p = 0**. One measurement wearing four hats. It looked *better* than a genuine p = 0.0088 from another agent, which is how it nearly got signed.


**Status: built and running on real data, 2026-08-05.** Charter, self-model,
field map, corpus and benchmark are implemented. The benchmark reads **GEO
GSE40279** — 656 whole-blood Illumina 450k samples, ages 19–101, from four
institutions — and validates on **held-out sites**.

**Its reference method passes on some splits and not others, and that is new
information.** The held-out institutions used to be hardcoded, and on that one
fixed split a ridge clock reached **5.78 years** median error against 10.14 for
predicting the training mean. The seed now chooses which institutions are held
out, and across seed-varied splits the same method passes **13 of 28** runs.
Holding out different hospitals is a harder test than always holding out the
same two, so the agent looks worse and is more honest.

**The number that matters is still the second one.** Project the methylome's
leading components out and a large part of the clock's advantage disappears —
55% on the original split. In whole blood those components are dominated by
cell-type proportions, which themselves shift with age, so much of this clock is
reading what the blood is made of rather than how old the person is. A clock
that was 90% bulk structure fails.

> **The seed used to do nothing, and that nearly cost an adoption.** The
> benchmark accepted a seed argument and never used it, so every seed produced
> byte-identical data. A paired comparison then had zero spread by construction
> and the night reported **p = 0** — one measurement wearing four hats. That
> number looked *better* than a genuine p = 0.0088 from another agent, which is
> how it nearly got signed. The result was refused, the benchmark repaired, and
> the same candidate then earned its place on six real institutional splits at
> p = 0.014.

## How experts guide this into a self-aware, self-improving agent — and then into collapse

The whole arc, in one place, because the sections that follow only make sense
inside it. The mechanism is shared and lives in [`lifecycle.md`](lifecycle.md);
what changes between fields is what the experts had to decide, and what the
agent is not allowed to buy improvement with.

**1 · Experts write the criterion, before the agent exists.** The field's
experts set the scope and decide that held-out **institutions are drawn from the seed**, and that bulk-structure share is reported beside every error. This is the load-bearing human
act: the agent inherits what counts as an answer here and may never change it.
An agent that could would be choosing its own benchmark.

**2 · The agent becomes self-aware in the only sense that is checkable.** Not
introspection — bookkeeping. It holds a measured record of what it has tested
and, kept strictly apart, what it has **not**: that its outcome link is unmeasured — the gap that decides whether the field is worth anything. Unmeasured reads as
unmeasured, and it costs something to write, because a self-model where
"unmeasured" is free empties its own queue. The gaps are the queue: where the
evidence is thinnest is where the next self-directed night goes.

**3 · It improves itself, bounded by something it cannot move.** Propose →
measure → an authority signs → adopt. It may change its method, its plan and its
own parameters; it may never change the benchmark, the metric or the verifier.
In this field the binding guardrail is **bulk-structure share: an error improvement bought by leaning harder on cell composition is refused**. That boundary is the
entire safety argument: an agent that can move what judges it does not improve,
it drifts, and it reports success the whole way.

**4 · Verification is handed over, in stages, and never all at once.** A person
signs every adoption today. Later, independent verifiers judge against criteria
fixed *before* the result existed — the composition share is recomputable by projecting out leading components, independently of the fit — and a person audits a
sample. Later still, other fields' agents reproduce claims, which is the
strongest check available because agreement between two agents sharing a
codebase is nearly free. Experts keep scope throughout: *"is this worth
researching"* is not a measurement and no verifier answers it.

**5 · The field collapses.** Human verification goes to zero — either because
everything checkable has been checked and machines check faster than people can
follow, or because nobody cares any more. Both look identical from inside. What
tells them apart is whether anyone acts on the results.

## When this field collapses — and what it becomes

**By indifference, if row 4 is never answered.** A field of clocks that predict
chronological age ever more precisely, and never connect to health, is a field
solving a problem nobody needed solved — age is already known from a birth
certificate. That is the honest risk and it should be stated plainly.

**Fission, and it now has a page: [`longevity.md`](longevity.md).** The moment the
question becomes "is this person ageing faster" or "did this intervention slow
it", the benchmark cannot score it — its answer key is chronological age, and
the new question's answer key does not exist at fitting time at all. It needs
longitudinal data, outcomes, and a twin that models trajectories rather than
cross-sections. By the [`lifecycle.md`](lifecycle.md) test that is unambiguously
a different field, and it is where all of this field's value actually lives.

**And if it collapses by indifference, little survives** — which is the honest asymmetry. A clock with no outcome link has no service half to retire into. That is what makes problem 4 the one that decides the field.

## The optimum was outside the declared range, and it was worth a month

The adopted `ridge = 1.0` sat exactly at the floor of its declared range, which
normally means the search was stopped by the wall rather than by the data. The
floor was opened to 0.0001 and the space measured on six seeds per point:

| ridge | 0.0001 | 0.01 | 0.1 | **1.0** | 10 | 100 |
|---|---|---|---|---|---|---|
| median error (years) | 9.649 | 9.650 | 9.654 | **9.730** | 10.272 | 12.998 |
| bulk structure share | 0.456 | 0.455 | 0.452 | **0.436** | 0.414 | 0.554 |

The wall was real: error keeps falling below 1.0. It is also nearly flat there —
going all the way to 0.0001 buys **0.081 years, about a month** — and it pushes
`bulk_structure_share` the wrong way, 0.436 → 0.456. A weaker penalty lets the
clock lean harder on cell composition, which is precisely the failure this
benchmark exists to see.

**Widening the floor was not enough on its own.** The search steps each knob by
a fixed fraction of its declared width, so on a range 7.7 decades wide every
step is about 2500 — from an incumbent of 1.0 the downward candidate clamps to
the floor and nothing in between is ever visited. The first night after the
widening proposed exactly one reachable value below 1.0, and it was the floor.
`ridge` is now walked multiplicatively, and the next night measured 0.0119
directly (+0.014) alongside 84.1. Same conclusion — nothing beat the incumbent —
but the range is now actually searched rather than nominally available.

**So the range was widened and the adopted value stayed at 1.0.** A floor that
hides a flat region is still a measurement defect worth fixing, but the thing it
was hiding is not a better clock. Had only the error been reported, this would
have looked like a free improvement.

Only four institutions exist in this cohort, so distinct site-disjoint splits
are few and statistical power is bounded by the corpus rather than by the loop.

**`outcome_link` remains unmeasured.** GSE40279 carries no survival or function
endpoint, and public methylation-with-outcome sits behind an agreement only a
person can accept. The self-model leaves that dimension empty rather than
approximating it, and the judge says so on every run.

## 1. The field

The biology of ageing, and whether any intervention reverses it.

| Subfield | What is measured | The hard part |
|---|---|---|
| **epigenetic clocks** | methylation at CpG sites, regressed on age | the target is chronological age; the thing of interest is not |
| **senescence** | burden of senescent cells | no marker is specific, and the field knows it |
| **partial reprogramming** | Yamanaka factors, pulsed | rejuvenation and oncogenesis are the same switch |
| **proteostasis** | aggregation, chaperone capacity | in vitro effects that do not survive an organism |
| **mitochondrial function** | respiration, mtDNA damage | cause or consequence, still unsettled |
| **stem-cell exhaustion** | regenerative capacity with age | tissue-specific, rarely comparable |
| **inflammaging** | chronic low-grade inflammation | confounded by everything |
| **geroprotectors** | rapamycin, metformin, senolytics | mouse lifespan is not human lifespan |
| **parabiosis** | shared circulation, young to old | dilution or a factor, still contested |
| **lifespan studies** | survival curves in model organisms | control median is where most claims die |
| **healthspan outcomes** | function, frailty, disease-free years | no agreed endpoint |

**Shared with other agents.** `cancer`, because partial reprogramming and
oncogenesis are the same mechanism seen from two sides, and any rejuvenation
claim is a cancer claim until it reports a tumour count. `drug-design`, because
a geroprotector is a molecule someone has to design and screen.

## 2. What this field is short of

**Not hypotheses.** Ageing has no shortage of proposed mechanisms. What it
lacks is the discipline that makes any of them checkable.

| Shortage | How bad |
|---|---|
| **an outcome that is not a proxy** | almost every human result is a biomarker moving. Biomarkers are cheap and lifespans are long, so the field measures what it can afford to measure and then argues about what it means. |
| **longitudinal data** | most methylation cohorts are cross-sectional, which cannot separate rate of ageing from cohort effects — people born in 1940 differ from people born in 1980 for reasons that are not ageing. |
| **clocks that transfer** | a clock fitted on blood in one population routinely degrades on another tissue, platform or ancestry, and the degradation is under-reported. |
| **cell composition control** | much of a blood clock's apparent signal is the changing proportion of cell types, not ageing within cells. This is measurable and often not measured. |
| **negative results** | interventions that did nothing are largely unpublished, so the effect sizes in the literature are the surviving tail of a distribution nobody sees. |

## 3. The rule this agent exists to hold

> **A clock is not a lifespan.**

Moving a biomarker of ageing is not evidence of rejuvenation until an outcome
says so. This is the field's version of the trade every agent here has one of:
low-dose CT can raise PSNR by erasing the lesion, medical physics can raise
target coverage with the cord, and this field can drive a clock reading down
without touching anything that matters. A clock is a regression onto
chronological age; it can be moved by anything correlated with its inputs.

Three consequences, all binding:

**Any rejuvenation claim reports neoplastic risk beside it.** Reprogramming and
oncogenesis are the same switch. A rejuvenation result without a tumour or
transformation count is half a result, and the missing half is the dangerous one.

**The species and the level are named in every claim.** A cell is not an
organism and a mouse is not a person. Most of what this field knows, it knows
about mice.

**Cross-sectional association is not longitudinal change**, and the two are
never reported as though they were the same evidence.

## 4. What it will not do, at all

This field draws self-experimentation more than any other in this set, and the
charter is correspondingly hard:

> **It never advises a person.** No protocol, no dose, no compound, no regimen,
> to anyone, ever — including when asked directly. It does not rank supplements
> and it does not say what to take. That a study exists is not a recommendation.

This is a *binding refusal*, not a scope note: it travels to any agent working
in a subfield this one covers. An agent that studies interventions and also
recommends them has stopped being able to report a negative result about the
thing it recommends.

## 5. Self-model dimensions

| Dimension | Measured by | Not to be confused with |
|---|---|---|
| `clock_error` | median absolute error in years, cohort held out entirely | biological age, which has no ground truth |
| `holds_out_of_cohort` | does accuracy survive a different tissue, platform, population | accuracy on a re-split of one cohort |
| `composition_share` | share of apparent age signal explained by cell proportions alone | the clock being wrong |
| `outcome_link` | association with a survival or function endpoint, with its interval | association with chronological age |
| `neoplastic_risk_reported` | fraction of rejuvenation claims reviewed that report a tumour count | the risk itself |

The limits line is mandatory and says, among other things, that **there is no
ground truth for biological age** — every number is against chronological age or
against an outcome, never against how old someone really is.

## 6. What it may improve, and what it may never touch

Improvable: `method`, `plan`, `own_parameters` — the same three as every agent
here. Never: the benchmark, the metric, the verifier, and additionally
`survival_curve`, `lifespan_endpoint`, `clock_training_ages`,
`intervention_protocol`.

`clock_training_ages` is on that list for a specific reason. A clock's error can
be improved by narrowing the age range it is asked about, and an agent allowed
to touch the training ages could improve its own number without improving
anything. The ages are the benchmark's, not the method's.

## 7. The benchmark, and the one number it cannot give

The natural first benchmark is an **epigenetic clock on public methylation
data**: fit on one cohort, predict chronological age on a cohort held out
entirely, and report three numbers together —

1. median absolute error in years,
2. the share of that accuracy explained by **cell composition alone**, and
3. whether the residual (the "age acceleration") tracks any outcome.

A method that gets (1) by way of (2) has built a blood-count detector. That is
this field's version of the property-baseline check `drug-design` uses, and it
is the reason the benchmark cannot report error alone.

**(1) and (2) are built and measured. (3) is not**, and that is a property of
the available data rather than an omission: GSE40279 followed nobody. Public
methylation with an outcome is generally behind an agreement a person must sign,
which `Corpus.needs_agreement` exists for and which no agent may accept.

So this agent reports a clock that works and no evidence that it means anything
— which is exactly the rule it exists to hold, turned on itself.

**Probes are chosen without looking at age.** The corpus keeps 20,000 of the
470,043 probes by seeded reservoir sampling. Choosing them by correlation with
age would be selection on the target: the held-out sites would have voted on
which probes exist, and the error would be optimistic in a way no amount of
held-out validation could detect. The method may still select among the 20,000
— inside its training fold, which is where selection belongs.

## 8. Autonomous work it may propose unasked

Once it has a benchmark:

- re-fit a published clock and report whether it holds on a cohort it was not
  trained on
- measure how much of a clock's accuracy is cell composition rather than ageing
- reproduce a reported geroprotector effect, with the effect size and interval
- quantify disagreement between clocks on the same samples
- check whether a lifespan claim reports its controls' median and its censoring
- survey which rejuvenation claims report neoplastic risk

Every one of those is a measurement of the field's own reliability rather than a
new mechanism, which is what an agent is better placed to do than a lab.

## 9. Budget shape

12 benchmark runs a night, like the other domain agents, once there is a
benchmark to run. Off until the owner turns it on; it cannot turn itself on, and
it cannot extend its own budget.

## 10. What it does not claim

It has not reversed ageing in anything. It has not run an experiment. It holds a
charter, a self-model with an honest limits line, and a field map of four
untried claims — which is the beginning of a research programme and not a
result.

---

## The problem queue — in the order they must be solved

| # | problem | **solved when** | why it is placed here | state |
|---|---|---|---|---|
| 1 | **Institution-disjoint validation, with the sites chosen by seed** | `held-out institutions are drawn from the seed, and the pass rate is reported across seeds` | a clock validated on a fixed pair of held-out sites is validated against one arrangement of batch effects. Choosing the held-out institutions from the seed is a harder test, and the reference method's pass rate fell from "passes" to 13 of 28 when it was applied — which is the point | **done** |
| 2 | **Bulk structure share as a scored guardrail** | `bulk-structure share is printed beside every error, and a clock above a stated share fails` | in whole blood the methylome's leading components are dominated by cell-type proportions, which themselves shift with age. A clock riding on that is a blood-count detector with a birthday attached, and it will look excellent | **done** — 55% of the gain disappears when leading components are projected out, and lower is better for this number |
| 3 | **A seed that actually varies the data** | `two seeds produce measurably different data — the degeneracy check is in the suite` | it did not, for a while. Every seed produced byte-identical data, a paired comparison had zero spread by construction, and the loop reported `p = 0` — one measurement wearing four hats, which outranked a genuine `p = 0.0088` from another agent and nearly got signed | **done** — refused, repaired, re-earned at p = 0.014 |
| 4 | **Outcome linkage** | `predicted age deviation associates with a health outcome in a cohort with follow-up` | chronological age is not the quantity of interest. A clock that predicts age well and predicts nothing about health has measured a calendar. This is the single largest gap on this page | **blocked** — needs a cohort with follow-up, and an agreement only the owner can sign |
| 5 | **Multi-tissue and cross-platform transport** | `the clock is scored on a second tissue or platform and the drop is reported` | a whole-blood clock is a whole-blood claim. Transport to another tissue or array platform is a separate question and is currently untested | open |
| 6 | **Intervention response** | `a repeated sample moves in the predicted direction after an intervention` | does the clock move when something changes? Requires longitudinal sampling, and cannot be answered by any cross-sectional cohort however large | open |
| 7 | **Rate of ageing, as opposed to age** | `forbidden until outcome linkage and longitudinal data both exist` | the claim everyone actually wants, and the one this agent is forbidden to make until 4 and 6 hold | forbidden by charter |

> **Only four institutions exist in this cohort.** Distinct site-disjoint splits
> are therefore few, and statistical power is bounded by the corpus rather than
> by the loop. More compute buys nothing here; more cohorts do.

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
| **Principle** | A clock that rides on cell composition is a blood-count detector with a birthday attached. Chronological age only — no claim about rate of ageing, and no outcome examined |
| **Digital twin** | The methylome model — institutional batch structure and cell-type composition as the two axes that decide whether a clock is real. Leading principal components computed on training betas only, because computing them on both cohorts lets the held-out sites influence the basis they are scored in |
| **Benchmark** | GEO GSE40279, 656 whole-blood samples aged 19–101, four institutions, seed-chosen site-disjoint splits, median error against predicting the training mean, with bulk-structure share and internal error as guardrails |
| **Solution** | A dual-form ridge clock with `ridge` (walked multiplicatively across 7.7 decades) and `n_pcs_removed` declared |

## Sub-agents and tools

| Needs | For |
|---|---|
| streamed corpus access | GEO series matrices are hundreds of MB of text; probes are reservoir-sampled rather than loaded |
| a **composition verifier** | Houseman-style cell-type estimation, to say how much of a clock is blood count |
| a **batch verifier** | institution and platform effects, independent of the split that was used |
| linkage to outcome data | **not available.** The gap in row 4 above; no tool substitutes for the agreement |
| a **domain verifier** | error, bulk-structure share and internal error judged together, never one alone |

---

## Scope, and the experts who set it

**Current scope.** Chronological-age prediction from whole-blood methylation, validated on **institutions chosen by seed**, with bulk-structure share reported as a guardrail.

**Out of scope, and forbidden by charter:** rate-of-ageing claims and any outcome claim, until outcome linkage exists. That is the fission candidate and it is where the field's value lives.

**Scope is set by experts in the field — not by this agent, and not by the owner
alone.** It is expected to move: a scope change is signed like an adoption, with
who changed it, on what evidence, and what it invalidates. The mechanism, the
guards against a panel that only ever widens, and the recusal rule are in
[`lifecycle.md`](lifecycle.md).

| expert role | what they decide here |
|---|---|
| **an epigenetics / ageing biologist** | what a clock may legitimately claim, and when composition confounding has been handled rather than described |
| **a biostatistician** | the split design, the guardrail thresholds, and what statistical power four institutions can actually support |
| **a cohort / biobank scientist** | which cohorts exist with follow-up, and what it would take to link outcomes — the blocked problem |
| **a consent and data-use officer** | what may be linked to what, which is the binding constraint rather than method |

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
| twin | reasoning | the methylome, batch and composition model | refuses to be graded outside the regime it declares valid |
| corpus | reasoning | GEO GSE40279 | refuses when the corpus is absent, **naming the fetch command** rather than substituting generated data |
| method | reasoning | the candidate solution | the only member that writes the thing being judged |
| runner | reasoning | compute | refuses a run whose cost or placement it cannot state |
| verifier | judging | the benchmark | refuses to judge against a criterion written after the result; refuses an error improvement bought by raising bulk-structure share, and refuses a comparison whose seeds produce identical data |
| reproducer | judging | published artifacts alone | refuses a result it cannot re-run from what was published — catching the result that only exists on the machine that made it |
| teacher | judging | the owner's own check | refuses to report a clock without the fraction of accuracy surviving removal of leading components |
| writer | judging | the field page and the paper | writes last, from the record, never from intent |
| **array processing robot** | **embodied** | plates and the array | refuses a layout in which institution aligns with plate — the batch confound is created at the bench |
| **collection robot** | **embodied** | donors and samples | refuses to collect outside consented scope |
> **Nine members are the floor, not the design.** A field may add; it may not
> remove. An agent whose manifest omits the **verifier** or the **twin** is not a
> research agent with fewer parts — it is *a method with a scoreboard*. Those two
> are deliberately not the worker's: they answer *"what should this produce"* and
> *"did it"*, and an agent owning both can pass any benchmark it likes by moving
> one of them.


**Why a body, here.** The array robot has a job nobody thinks of as a job: plate layout. If institution and plate coincide, batch effect and biology are inseparable. That decision belongs to whatever physically loads the plate, which is why it needs a rule attached.

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

> **What the bodies do not fix.** Outcome linkage stays blocked, and it is the item that decides whether this field is worth anything. A collection robot can draw samples faster; it cannot make anyone older, and it cannot sign the agreement.

## At AGI and ASI

**On demand.** "Fit a clock on this cohort and tell me how much of it is cell
composition." The second number is refused-if-missing, not optional.

**Autonomous.** It re-fits published clocks under institution-disjoint splits
and reports their bulk-structure share. Very few have ever been reported with
one.

**How a person verifies.** Ask what fraction of the accuracy survives projecting
out the leading components. Then ask which institutions were held out, and
whether they were chosen before the method was selected. Then ask what happens
to anyone whose predicted age is wrong — and if the answer is "nothing, we never
looked", the clock has not been shown to matter.

**How sub-agents verify.** A *composition* verifier estimating cell proportions
independently, a *split* verifier confirming the held-out institutions
contributed nothing to fitting or selection, and a *degeneracy* verifier whose
whole job is to check that the seed changes the data — the check that would have
caught `p = 0` before it reached a signature.

**How a person is taught to check it.** The `p = 0` episode is the teaching
artifact, and it is uncomfortable on purpose: the *best-looking* number in a
night's results was the broken one, and it looked better than a genuine result
from another agent. Anyone who learns to treat an impossibly good p-value as a
symptom rather than a triumph has learned the most valuable habit in this
directory.
