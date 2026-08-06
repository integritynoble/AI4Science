# The reverse-aging agent — how to design it

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
