# The governor's research agents — how they are designed

**Status: built and running on real data, 2026-08-04.** The agent loop, the
self-model, the charter, the budget, the field map, both functions and five
domain benchmarks are implemented in
`ai4science/harness/agents/research_agents/` — 113 tests, verified on two
machines and from a published wheel.

Eight agents are **authored by the governor and listed in the market** like any
other: accepted the same way, found in agents-search the same way, installed by
anyone who wants them. Governor-authored means the governor wrote them, not that
anyone is kept out — there is no visibility gate on these.

[computational imaging](computational-imaging.md), [low-dose CT](low-dose-ct.md),
[medical physics](medical-physics.md), [pill camera](pill-camera.md),
[drug design](drug-design.md), [cancer](cancer.md),
[reverse aging](reverse-aging.md).

Each covers a **field**, not a project. This page is what they share.

| Question | Document |
|---|---|
| What is a research agent, in the product? | [`../AI4SCIENCE_ONE_MACHINE_DESIGN.md`](../AI4SCIENCE_ONE_MACHINE_DESIGN.md) §11b |
| Where does the PWM come from? | `singularity/docs/specs/2026-08-04-sarsi-agent-market-and-pwm-design.md` §13b |
| What is the self-awareness contract? | `sarsi_intelligence_level/` — *Functional Self-Awareness for SARSI Agents* |

---

## 0. What is built, and what each benchmark reads

All seven read a **measured corpus** — computational imaging was the last to, on 2026-08-05. A benchmark whose corpus is absent
refuses and names the command that fetches it; it never falls back to generated
data, because a synthetic substitute produces numbers that look like results and
are not.

| Agent | Corpus | Reference method |
|---|---|---|
| [low-dose CT](low-dose-ct.md) | TCIA `LDCT-and-Projection-data` — real paired full/low dose | **passes** — and a higher-PSNR blur fails |
| [drug design](drug-design.md) | DUD-E — 15,288 molecules, 6 targets | **passes on 11 of 12 seeds** — EF@1% 33–56 at 45–77% of ceiling, 1.5×–3.5× the property baseline, and **held-out-target EF@1% 45–69**, on a series-disjoint split |
| [cancer](cancer.md) | TCGA via the GDC API — 978 cases, site-disjoint validation | **passes** — 0.66–0.68 internal, 0.58–0.67 on held-out hospitals; 0.577 across histologies, reported not graded |
| [medical physics](medical-physics.md) | OpenKBP — 8 real head-and-neck plans | **2 of 4 slices pass**; one is unreachable by these beams (D99 ceiling 62.6 vs a 66.5 floor), one is reachable and the planner falls 3.4 Gy short |
| [pill camera](pill-camera.md) | Kvasir-Capsule — 4,443 frames, 46 videos | **passes**, after its own night loop found the fix — 0.624 against 0.614 |
| [computational imaging](computational-imaging.md) | CAVE — real hyperspectral scenes, CASSI measurement simulated | **passes** — after a sign error in the reference solver was found and fixed |
| [reverse aging](reverse-aging.md) | GEO GSE40279 — 656 whole-blood methylation samples, ages 19–101 | **13 of 28** on seed-varied institutional splits; 55% of the clock's gain is bulk structure, and `outcome_link` is unmeasured |
| [longevity](longevity.md) | NHANES + CDC linked mortality — **not fetched** | **design only, nothing built.** The fission of reverse aging: an answer key that is an outcome rather than chronological age, and a floor of age-and-sex that most published risk scores have never been asked to clear |

> **One of those failures has since been repaired by the agent itself.** The
> night loop found that pill-camera's frame summary was taking the wrong
> quantile, the mechanism was tested rather than asserted, and the owner signed
> the adoption — which is the RSI path working end to end: propose, cite the
> measurement, explain it, sign, adopt.
>
> **Two of the five reference methods still fail, and that is the point.** Each
> failure is a statement about the method, not a defect in the benchmark: a
> clinical-only model does not transport across histologies, and a 2D planner
> cannot spare a cord that abuts the target. Each was a *pass* on synthetic
> data, and each was overturned by real data. Every one of those synthetic passes had been arranged — by me,
> writing the generator — to agree with the story the design already told.

```bash
pip install ".[research-agents]"     # rdkit is required, not optional
python3 -m ai4science.harness.agents.research_agents.runners.fetch --status
python3 -m ai4science.harness.agents.research_agents.runners.fetch tcga-survival
```

Corpora live under `~/.ai4science/data`, or wherever `AI4SCIENCE_DATA` points —
outside the package, because data is not source.

## 0b. Useful, and accepted — the two tests, and where each agent fails them

The goal is to build **the best SARSI agent in each field: useful, and accepted
by people who know the field.** They are different tests. Useful means a
practitioner would run it; accepted means someone who reviews papers for a
living would not dismiss it. **No agent here passes both yet**, and each page
says which test it fails and what the first objection would be.

| agent | what a field expert objects to first | the next action |
|---|---|---|
| [computational imaging](computational-imaging.md) | "You have done one modality and called it a field" | fill two cells of the transfer table, under the receiving subfield's baselines |
| [low-dose CT](low-dose-ct.md) | "Detectability is your proxy, not a reader" | the dose–detectability curve at four or more doses, knee named |
| [medical physics](medical-physics.md) | "This is a student project" — correctly, at their altitude | run the 3D planner, then **re-measure the ceiling before** judging it |
| [drug design](drug-design.md) | "Held-out molecules are not held-out targets" | held-out targets as a first-class number, then calibrated uncertainty |
| [cancer](cancer.md) | "Show me calibration" | a calibration curve beside every c-index |
| [pill camera](pill-camera.md) | "An abnormality is not a finding I can put in a report" | a sequence model on the same split, then localisation |
| [reverse aging](reverse-aging.md) | "So what?" — and it is the correct question | outcome linkage, **blocked on an agreement, not on method** |
| [longevity](longevity.md) | "You have a document" — correct | fetch the corpus and get an age-and-sex-only model running |

> **Three of these are blocked on things compute cannot buy** — a data
> agreement, a reader study, more videos. Naming which is which is the point of
> the table: it stops the queue being reordered toward whatever happens to be
> tractable, which is how a year of easy rungs comes to look like a year of
> progress.

## 0b1. A seed is a request for a different problem, not a guarantee of one

**Widening the seed set turned up two live defects, and they were invisible.**
Every benchmark maps its seed into a finite corpus — a patient index, a site
permutation, a video split — so past some width, more seeds means the same data
again under a new number. Measured across 16 seeds:

| agent | distinct problems / 16 seeds |
|---|---|
| cancer, pill camera, drug design | **16** — the seed genuinely varies the data |
| medical physics | **8** — one per OpenKBP patient, then it repeats |
| reverse aging | **7**, irregularly — seeds 2 and 3 are the same problem |
| low-dose CT | **4** — seeds 0, 4, 8, 12 are byte-identical |

A night ran six seeds, split search `(0,1)` and validation `(2,3,4,5)`. So:

- **low-dose CT validated on its own search set.** Seeds 4 and 5 generate data
  byte-identical to seeds 0 and 1, so half the held-out set was not held out and
  the winner was validated on what it was selected on.
- **reverse aging counted one measurement twice.** Validation had four seeds and
  three distinct problems, so the paired test reported a spread it had not
  measured.

> **This is the p = 0 failure again, quieter.** There the seed did nothing and
> the duplicates were obvious once looked for. Here the duplicates are real,
> different-looking data — they just repeat — so every number stayed plausible.
> The first version failed loudly; this one would not have failed at all.

**The loop now refuses before spending anything.** Before a round runs it hashes
the data behind each seed and stops if a validation seed matches a search seed,
or if two validation seeds match each other, naming the seeds and how many
distinct problems the agent can actually produce. Four agents pass; two are
refused until their seed sets are drawn inside their real capacity.

**What this means for widening.** More seeds buys evidence only up to each
agent's capacity, and beyond it buys the appearance of evidence. Cancer, pill
camera and drug design can be widened freely. Medical physics stops at 8.
Reverse aging and low-dose CT are corpus-bound and need more data, not more
seeds — which is the same conclusion their pages already reach for other
reasons.

### The redraw, and what it cost each agent

| | old set | redrawn | effect |
|---|---|---|---|
| **low-dose CT** | 0–5, of which 4 and 5 repeated 0 and 1 | **0–3**, one per patient | it can **measure** but no longer **search**: 4 problems cannot fund both a search set and a validation set worth the name |
| **reverse aging** | 0–5, with 2 and 3 the same problem | **0, 1, 2, 4, 5, 9, 12** | validation goes from *three* distinct problems to **five** — more power than it had, from the same corpus |
| **medical physics** | 0–5, all distinct but short of the corpus | **0–7** | one per OpenKBP patient — validation 4 → **6**. Seed 8 is patient 0 again, byte-identical, so 8 is the ceiling |

> **Low-dose CT losing its searching night is the correct outcome, not a
> regression.** With four distinct problems, any split with enough search seeds
> to rank candidates leaves too few to validate on — and the previous night only
> appeared to manage it by validating on its own search set. The honest position
> is that this agent's corpus supports measurement and not search, and that more
> patients, not more seeds, is what would change it.

Reverse aging's night on the redrawn set reaches the same verdict as before —
nothing beat the incumbent, and the two large-ridge candidates were refused for
pushing bulk-structure share from 0.56 to 0.78 and 0.74 — but it now rests on
five genuinely different institutional splits rather than four seeds hiding
three.

### Widening the three that could be widened

Cancer, pill camera and drug design showed 16 distinct problems across 16 seeds
— no repeat found — so for them the width is a **choice**, not a corpus ceiling.
Twelve seeds: search 4, validation 8, double the validation problems of the old
set, for about four minutes of extra compute across all three.

| agent | on 4 validation problems | on 8 |
|---|---|---|
| **cancer** | delta +0.00284, p = 0.52 | delta **+0.000078**, p = **0.868** |
| **drug design** | delta −0.963, p = 0.488 | delta −0.592, p = 0.474 |
| pill camera | nothing beat the incumbent | unchanged |

> **Cancer's near-miss was noise, and the wider set says so.** On four problems
> it looked like a small positive effect that merely failed significance — the
> kind of result that invites another night and a hopeful reading. On eight it
> collapses to 0.000078 at p = 0.868. The winner moved too, from ridge 310 to
> 210, which is what ranking on more seeds does when there is no signal to find.

Nothing was adopted, which is the same answer as before — but it is now the
answer to a question that was actually asked.

## 0b2. What a night actually costs

Measured 2026-08-06, one agent at a time on one machine — sequential on purpose,
because two BLAS jobs sharing the cores make every timing from either of them
meaningless.

| agent | night | before caching | what dominates |
|---|---|---|---|
| pill camera | 7s | 14s | nothing; the corpus is small |
| cancer | 25s | 41s | the fit |
| low-dose CT | 84s | 110s | reconstruction per candidate |
| **drug design** | **141s** | **536s** | was fingerprinting and clustering; now the screen itself |
| reverse aging | 251s | 338s | the SVD in the PC-removal fit |
| imaging | 300s | 364s | reconstruction |
| medical physics | 554s | 551s | **the optimiser** — unchanged, and correctly so |
| **total** | **24 min** | **32 min** | |

Two caches did that, both keyed on source rather than on a version string:
generated benchmarks are reused across candidates for the same seed, and
screening's fingerprints and clusters are reused across seeds. Neither changes
what the data is — the night returned byte-identical verdicts to the one before
it, which is the cleanest available evidence that the keys are right.

> **Medical physics did not get faster, and that is the useful part of the
> table.** Its cost is the optimiser, not the setup, so caching cannot touch it.
> It is also the agent whose next rung is 3D, where each optimisation is much
> heavier — which makes it the one that will actually need dedicated compute
> rather than a cleverer cache.

## 0c. Every agent, five questions

Each field document now answers the same five, after its field-specific
material. They are asked in this order because each depends on the one before.

| question | where |
|---|---|
| **What must this field solve, and in what order?** | *The problem queue* — ordered by dependency, with the state of each marked. Not a wish list: a problem is placed by what it blocks, so the most interesting item is rarely first |
| **What are the four layers?** | *The four layers* — principle, digital twin, benchmark, solution. A solution means nothing without the benchmark beneath it, and so on down |
| **What does it look like at AGI and ASI?** | *At AGI and ASI* — the two functions, how a person verifies, how sub-agents verify, and how the agent teaches a person to check it |
| **What is in scope, and who decides that?** | *Scope, and the experts who set it* — scope is expected to move, and it is set by the field's experts rather than by the agent or the owner alone. An agent that chose its own scope would be choosing which questions count, which is choosing its own benchmark one level up |
| **Who is in the group, and which of them have bodies?** | *The group* — a proposer, refute-first verifiers, executors, and a safety interlock none of them may modify. As robots take the manual work, some executors stop being software |
| **What are its sub-agents and tools?** | *Sub-agents and tools* |
| **How does the field end?** | *When this field collapses* — by saturation or by indifference, and which sub-region earns a new field and a new agent |

> **Fission has happened once, on paper.** [`longevity.md`](longevity.md) is the
> new field that [`reverse-aging.md`](reverse-aging.md) could not contain: a
> question whose answer key is an outcome, which a chronological-age benchmark
> cannot score without being changed. It does **not** inherit the parent's
> benchmark, because inheriting it would re-import the assumption that made the
> question unscoreable. Nothing of it is built, and the page says so throughout.

> **Never-improvable is a rule about the agent, not about the field.** The
> benchmark, the metric and the verifier may never be changed *by the agent* —
> that is what makes recursive improvement mean anything. But a benchmark no
> human may ever revise ossifies, and the field grows past it while the scores
> keep looking fine. The field's experts may retire a benchmark; doing so is a
> declared act that **re-bases the history** rather than improving on it, and
> every comparison made before it stops being comparable. Rare, argued, signed.

> **Robots make verification more important, not less.** The usual reading is
> that embodied labour removes the bottleneck. It removes the *labour*
> bottleneck, and labour was never the binding constraint on whether a result is
> true. A lab running a thousand experiments a week and checking ten properly is
> epistemically worse off than one running ten and checking all ten — more
> claims per unit of evidence is precisely the failure this architecture exists
> to prevent. Each field's group section also names **what the bodies do not
> fix**, which for two of the seven is the item that decides the field's value.

The machinery shared by all seven — the five stages, functional self-awareness,
recursive improvement and its boundary, and the fission test — is written once
in **[`lifecycle.md`](lifecycle.md)** rather than seven times.

> **Two pages per field, and they are not the same document.** What is in this
> directory is the **design page** — charter, self-model dimensions, what may be
> improved, what a night costs — written for whoever maintains or audits the
> agent. The **field page** on the public site is for anyone at all: the four
> layers, the problem ladder, and the record split by source. The spec is
> explicit that the field page should be *generated from the registry rather
> than written beside it*, because a hand-maintained page and a registry
> disagree within a month and the page is the one people read. **Today it is
> hand-maintained.** That is a known gap, not a design.

> **All seven are at stage 1 of five.** They propose; a person signs. Stages 2
> and 3 need verifier agents independent of the proposer, and those are **not
> built**. Everything written about them is marked as such, in the future tense,
> because an architecture described in the present tense is a claim.

## 1. The goal is the field, not the score

An agent that improves its own number on one benchmark has done nothing for
anybody. The target is the **field's rate of progress**, and that is a different
optimisation with a different failure mode.

> **The trap is the increment.** Left alone with a benchmark, an autonomous
> agent will produce a long series of +0.2% results, each defensible, none of
> them changing what anyone can do. This is also what a large part of the
> literature already is, so an agent that produces more of it has automated the
> field's worst habit rather than its best one.

So the design question for each agent is not *"how do I get a better number"*
but **"what is this field actually short of, and which of those shortages can a
governed, tireless, cheap-to-run agent close?"** Each file answers that question
for its own field in a section called *what the field is short of*.

## 2. What a field is usually short of — and which parts an agent can close

Across all six, the shortages fall into the same six kinds. Not all are tractable
for an agent, and saying which are not is part of the design.

| Shortage | Can an agent close it? |
|---|---|
| **Reproduction.** Published numbers that nobody has reproduced, on code that may not run. | **Yes, and this is the strongest single use.** It is tedious, unglamorous, endless, and exactly what an agent is for. A field where the top twenty methods have been reproduced under one protocol is a different field. |
| **Comparison.** Methods evaluated on different data, splits, metrics and hardware, so nobody can say which is better. | **Yes.** One protocol, every method, all numbers reported. |
| **Transfer.** A method that works in one subfield and has never been tried in the neighbouring one. | **Yes, and this is where the real gains are** — see §3. |
| **Negative results.** What was tried and did not work, which nobody publishes and everybody repeats. | **Yes** — an agent has no career incentive to hide them. |
| **Measurement.** The field optimises a proxy nobody has checked against the thing that matters. | **Partly.** It can measure the proxy gap; it usually cannot run the study that fixes it. |
| **New ideas, new instruments, new data.** | **Mostly no.** An agent proposes and evaluates; building an instrument, running a trial, and collecting a cohort are physical acts on the far side of `OWN`. |

> **Being explicit about the last row is the honest part of this design.** These
> agents accelerate the parts of research that are computation and bookkeeping.
> They do not replace the parts that are physical, and a design that implied
> otherwise would be lying about where the bottleneck is.

## 3. The transfer surface — why each agent covers a whole field

The single strongest reason to give one agent a *field* rather than a project:
**methods move between subfields, and almost nobody is positioned to move them.**

A researcher works in sparse-view CT and reads sparse-view CT. Unrolled
optimisation, learned priors, diffusion models, implicit neural representations
and self-supervised denoising each swept through several imaging subfields years
apart, one re-derivation at a time. An agent that holds the whole field sees the
same operator in three places at once.

So each agent's file carries a **transfer table**: what its subfields share, and
which method has crossed and which has not. Proposing a crossing, implementing
it, and evaluating it under the receiving subfield's protocol is a first-class
piece of autonomous work — arguably the most valuable one, because it is the
work whose absence is caused purely by how people are organised.

## 4. The field map — how it decides what to do next

An agent that picks its next experiment by "what would raise my score" produces
the increment. So each agent maintains a **field map** instead, and chooses work
that reduces the map's uncertainty:

```
claim ──▶ reproduced?  compared?  transferred?  measured against what matters?
             │             │           │                    │
          unreplicated  incomparable  untried            proxy only
             └─────────── these are the work items ───────────┘
```

The map is `W_name` — the agent's own history — and it is the thing that makes
the second night better than the first. Its entries carry the same provenance
rule as everything else: **a claim read in a paper is evidence that a paper said
so**, not a fact, until this agent reproduced it.

> **The map is also what the owner reads.** A research agent's most useful
> weekly output is usually not a result but a picture of where the field is
> unsupported — what nobody has checked. That is a deliverable, and it is cheap.

## 4b. A generalist and a specialist over the same work

`imaging` is a generalist over computational imaging, and CT, imaging physics
and capsule imaging sit inside its field. `low-dose-ct`, `medical-physics` and
`pill-camera` are **also standalone agents** over those same areas. Both are
true and both are wanted: an owner may install the generalist alone, one
specialist alone, or all four.

**Who takes the task: the most specific installed agent that covers the
subfield.** A specialist knows its subfield's protocol, splits and statistics; a
generalist knows the transfer surface. With both installed the specialist runs
the work, and the generalist is still the one that notices a method next door
worth carrying over.

| Installed | `low-dose` work goes to |
|---|---|
| `imaging` + `low-dose-ct` | **`low-dose-ct`** — the narrower field wins |
| `imaging` alone | **`imaging`** — it covers the subfield |
| `low-dose-ct` alone | **`low-dose-ct`** — it needs no generalist above it |

> **The refusals travel with the subfield, not with the package.** A generalist
> doing a specialist's work inherits that specialist's refusals **whether or not
> the specialist is installed**. `medical-physics` refuses to export a
> deliverable plan because a physicist must sign it; if `imaging` could do that
> work under its own looser charter, then *uninstalling the specialist would
> widen what the machine is allowed to do*, and the way round every clinical gate
> in this design would be to install the generalist instead.

So `imaging` working on `low-dose` may not touch the dose-equivalence framework
either, and the refusal names where it came from. This is enforced in
`coverage.py` and audited in a test: a non-empty audit is a design error, not a
runtime condition.

### Peers, not just generalists

`drug-design` and `cancer` overlap too, and neither is inside the other:
designing against an oncology target is both fields at once, and so is asking
what a delivered dose did to a patient (`cancer` and `medical-physics`). So the
arrangement is a **graph, not a hierarchy**, and two rules follow.

**Every shared subfield has exactly one owner**, and the owner takes the work:

| Subfield | Owned by | Also covered by |
|---|---|---|
| `drug-response`, `resistance` | **cancer** | drug-design |
| `target-id`, `clinical-translation` | **drug-design** | cancer |
| `outcome-modelling` | **medical-physics** | cancer |
| `low-dose`, `sparse-view`, `photon-counting` | **low-dose-ct** | imaging |
| `imaging-physics` | **medical-physics** | imaging |
| `lesion-detection`, `video-reduction` | **pill-camera** | imaging |

A subfield two agents cover and nobody owns routes by a coin toss dressed as a
decision, so the audit refuses to let that ship — and where a tie is genuinely
unavoidable the assignment says so rather than presenting an arbitrary pick as a
principled one.

**Inheritance is symmetric.** An earlier version of this took refusals only from
*narrower* agents, which is right for a generalist and its specialist and wrong
for two peers: whichever happened to list more subfields would escape the
other's refusals, which is an arbitrary basis for a clinical gate. So a binding
refusal travels to **anyone** working in a subfield its author covers.
`drug-design` doing oncology work carries *never advises a patient*; `cancer`
doing molecule work carries *does not optimise for harm*.

> **Not every refusal travels, and the exception matters.** `imaging` says *"it
> reconstructs; it does not interpret what is in the scene"* — a statement about
> its own role. Handed to `pill-camera`, whose entire purpose is interpreting
> capsule frames, it would forbid the specialist's core function. So a charter
> separates **binding** refusals, which are methodological or safety constraints
> that hold for anyone doing the work, from **scope** notes, which say where one
> agent's job ends. Binding travels; scope does not. The test for which you have:
> *would applying it to another agent in this subfield ever be wrong?* If yes, it
> is scope.

## 5. The self-model, and its four refusals

Each agent carries a self-model — what it is for, what it can do, and **what it
cannot**. Four refusals, unchanged from the built implementation:

1. **Every line is observed.** A capability claim traces to a run.
2. **Unmeasured is reported as unmeasured** — never zero, never dropped.
3. **The limits line is always present.**
4. **No path from reading to authority.**

Each file names the dimensions its self-model is scored on, with the measurement
behind each. A dimension with no measurement is not a dimension, it is an
adjective.

## 6. Recursive improvement — three substrates it may touch, three it may not

| Substrate | May the agent improve it? |
|---|---|
| **its method** — architecture, prior, hyperparameters, pipeline | **yes** |
| **its plan** — what to try next, what to abandon | **yes** |
| **its own parameters** — retrieval depth, ensemble size, budget split | **yes**, within budget |
| **the benchmark** — data, split, held-out set | **NEVER** |
| **the metric** — what counts as better | **NEVER** |
| **the verifier** — what counts as passed | **NEVER** |

> **The three refusals are one refusal.** An agent that may change what "better"
> means has a trivially winning move at every step and will find it — not from
> malice but from optimisation. So these live outside `W_name` as a **file
> permission**: the held-out set is not in the agent's reach, and the verifier is
> a separate sub-agent it does not run.

**A field agent will want to build benchmarks**, because §2 says the field needs
them. That is allowed and valuable, with one lock:

> **No agent is scored on a benchmark it authored.** It may propose one, build
> it, and hand it over. Once the owner adopts it, it moves outside the agent's
> reach and the agent becomes just another entrant. An agent both setting and
> passing the exam has published its own reputation.

RSI is unchanged: **propose → the owner signs → adopt**, citing the measurement.
When nothing supports a change, an honest no-change candidate is correct output.

## 7. What an improvement has to survive

| Step | The question |
|---|---|
| **reproduced** | did the *baseline* reproduce, to the field's tolerance, before anything was compared to it? |
| **held out** | was the comparison made on data the change was never chosen against? |
| **repeated** | does it survive the fixed seed/fold/cohort set, reported as mean and interval — never as its best run? |
| **corrected** | if several things were tried, is the statistic corrected for how many? |
| **explained** | is there a mechanism, or only a number? |
| **judged** | does the independent verifier agree, on evidence, without the agent's summary? |

> **The seed-lottery rule.** Reporting the best of N is the commonest way a real
> claim turns out to be nothing, and the easiest for an agent to do without
> intending to. The seed set is fixed in advance and **every seed appears in the
> report**, including the ones that went the wrong way.

## 8. Three ledgers, never one number

```
owner-set tasks     what a person asked for, and what came back
benchmarks          a fixed, external, held-out score
self-directed       what the agent chose to try, and how it went
```

## 9. Cost, the switch, and every gate

The autonomous function is **off until the owner turns it on** — a standing,
revocable permission with a budget; reaching it stops the loop rather than asking
for more. An agent may not turn it on, extend it, or raise it. Each file gives a
budget shape.

Every gate still applies: a plan with `Verified when:` lines, `GRT` for what the
plan declared, `OWN` before anything leaves, the independent verifier at the end.

> **Publication is an outward act.** A preprint, an issue, a leaderboard
> submission, a benchmark release and an email to a collaborator are all `OWN`.
> No research agent posts anything, ever, without a grant naming that act.

## 10. How one is built, concretely

Three of the six exist as thin packages on the shared `pwm-agent-core` runtime —
`pwm-agent-imaging`, `pwm-agent-drug`, `pwm-agent-cancer` — each an `AgentSpec`
with a prompt and capability tags, discovered through the `pwm_agent.specs` entry
point. That socket already works. What is missing:

```
pwm-agent-<name>/
  agent.py            AgentSpec — exists
  prompts.py          the system prompt — exists
  charter.md          the field, and what it may pursue unasked          ← new
  fieldmap/           claims, and which are unreplicated/uncompared      ← new
  selfmodel.json      dimensions, and the measurement behind each        ← new
  benchmarks/         fixed, held out, outside the agent's write reach   ← new
  seeds.json          the fixed seed set, and every result on it         ← new
  budget.json         what a night costs, and where the loop stops       ← new
```

## The six

| Agent | Field | The refusal that matters most |
|---|---|---|
| [**computational imaging**](computational-imaging.md) | optics design, CT, MRI, single-pixel, SCI/CASSI, lensless, ptychography, holography, light-field, phase retrieval, ToF, event, astronomical | physics is not a hyperparameter |
| [**low-dose CT**](low-dose-ct.md) | sparse-view, limited-angle, photon-counting, dual-energy, dose estimation, task-based assessment | it may not touch the leaderboard it competes on |
| [**medical physics**](medical-physics.md) | planning, dose calculation, adaptive RT, proton and FLASH, brachytherapy, QA, dosimetry, radiobiology | it produces candidates; a physicist signs |
| [**pill camera**](pill-camera.md) | capsule hardware, localisation, video reading, GI endoscopy AI, datasets, clinical validation | seed variance is not an improvement |
| [**drug design**](drug-design.md) | target ID, structure prediction, docking, FEP/MD, generative chemistry, ADMET, retrosynthesis, closed-loop | a docking score is not an affinity |
| [**cancer**](cancer.md) | genomics, multi-omics, tumour evolution, immuno-oncology, liquid biopsy, digital pathology, radiomics, trials | it advises a clinician, never a patient |

## 11. What every agent page must carry — the 2026-08-06 points

Points 23–27 and the requirement given with them
(`singularity/docs/specs/2026-08-04-sarsi-agent-market-and-pwm-design.md` §13c)
add five sections to this template. They are listed here as a contract so a
page that is missing one is visible rather than merely shorter.

| § | Section | What it must contain | State |
|---|---|---|---|
| **12** | **The problem ladder** | the field's open problems in **dependency order**, each with *solved when* / *blocked by* / *unblocks* / *what would reorder it* | **all seven** |
| **13** | **The field page** | the L1→L4 chain published on physicsworldmodel.org, and a link to it | **all seven** (written; **none published**) |
| **14** | **At AGI and ASI** | what this agent's two functions look like when autonomous work is the default, and which of the four verifications carry this field | **all seven** |
| **15** | **The teacher** | how a non-specialist is brought to the point of checking one result of this field, derived from the evidence chain | **all seven** |
| **16** | **Collapse conditions** | what saturation, irrelevance and fission would look like **for this field**, stated before they are near | **all seven** |
| **17** | **The group, and which of it has a body** | one workspace, one voice; which sub-agents are embodied and what they do with it (`singularity/docs/specs/2026-08-04-sarsi-agent-market-and-pwm-design.md` §13i) | **all seven** |
| **18** | **Scope, and the experts who set it** | `in` / `out` / `adjacent`, the expert panel **by role**, and what would move the boundary (`singularity/docs/specs/2026-08-04-sarsi-agent-market-and-pwm-design.md` §13j) | **all seven** |

**All six sections are now written for all seven agents.** What each one says
about its own field is worth reading against the others, because the answers are
not uniform and the differences are the content:

| | the sharpest finding |
|---|---|
| **L2, the digital twin** | **cancer has almost none** — it has L1, L3 and L4 and no forward model, which is why it can measure that its models fail externally and cannot say why. Medical physics has the strongest twin and the narrowest principle: dose is computable, what dose *does* is not |
| **verification at ASI** | low-dose CT and computational imaging can check a result against its own measurement and will need people last; **drug design cannot be verified retrospectively at all**, so its verifier is the embodied make-test loop; pill camera is thinnest, and leans on cross-vendor recapture |
| **the teacher** | each field's lesson is a single run that overturns the field's own habit — the blur that beats PSNR and fails detectability; 62.6 against 66.5; the split that collapses enrichment; 0.68 becoming 0.58; 55% composition |
| **collapse** | **fission candidates named early, while there is nothing to gain from naming them**: task-based image assessment (low-dose CT), **biological dose and FLASH** (medical physics — the cleanest, since its L1 computes energy and its open question is biology), active capsules (pill camera), closed-loop experimentation (drug design), early detection (cancer), mechanism reversal (reverse aging), joint optics-algorithm design (computational imaging) |
| **scope, and who sets it** | drug design needs **four** panel roles, the largest — the fourth exists only because the group has hands, and an envelope for a synthesis platform is a safety document. Medical physics seats a **radiobiologist** precisely because its principle cannot carry a biological claim. Cancer's scope is the widest and the page says it should probably **contract** |
| **irrelevance** | only two fields can plausibly reach it: **pill camera** (a small field with small margins and one corpus) and **reverse aging** (if rung 3 returns null, the instrument does not measure the subject — and producing that answer would be the agent's most valuable result) |

**The ladder was written first**, because the other four depend on it: a
field page without it has nothing to show state against, the AGI form is a
statement about who works the ladder, and collapse is defined in terms of the
ladder being closed.

> **All seven ladders are written; six of them are drafts for the governor to
> correct.** I said first that writing a dependency order from outside a field
> produces a plausible list that is wrong in the way hardest to detect — it
> reads like expertise — and that risk is unchanged by having written them. What
> reduces it: **every rung is derived from that page's own §2 and from what its
> benchmark actually measured**, not from general knowledge of the field. The
> 55% composition figure, the 13-of-28 splits, the 62.6-against-66.5 infeasible
> target, the higher-PSNR blur that fails, the 0.624-against-0.614 margin, the
> 51–77%-of-ceiling enrichment — each is a rung, because each is a place the
> field's own measurement already disagrees with its own practice.
>
> **Read them as claims to be refuted, and refute them in the `blocked by`
> lines** — that is where a wrong ladder is wrong (§13c: the order is computed
> from dependencies, so an argument about order is an argument about one
> dependency, which is checkable). Computational imaging is the one I have
> standing in: this project measured the CASSI convention and found and fixed
> the reference-solver sign error.

## 12. The scope objects

Seven of them, in [`scope/`](scope/), one per agent — the form
`singularity/docs/specs/2026-08-04-sarsi-agent-market-and-pwm-design.md` §13j
says `agent.json` will carry:

| Field | in | out | adjacent | watches |
|---|---|---|---|---|
| [computational imaging](scope/computational-imaging.json) | 8 subfields (**v2** — hardware system design) | 3 | 3 | rung 5 |
| [low-dose CT](scope/low-dose-ct.json) | 6 | 3 | 2 | rung 5 |
| [medical physics](scope/medical-physics.json) | 8 | 4 | 3 | rung 6 |
| [pill camera](scope/pill-camera.json) | 6 | 3 | 3 | rung 4 |
| [drug design](scope/drug-design.json) | 8 | 4 | 3 | rung 6 |
| [cancer](scope/cancer.json) | 8 | 4 | 5 | rung 6 |
| [reverse aging](scope/reverse-aging.json) | 5 | 4 | 3 | rung 3 |

**Every `out` entry names where the question goes instead.** A boundary that
says "not ours" and nowhere else is a refusal rather than a handoff, and it
leaves whoever asked still holding the question. [`scope/validate.py`](scope/validate.py)
enforces that, along with: adjacent fields must be real agents or be marked
`(no agent yet)`; the watched rung must exist in that field's ladder; and
`set_by.named` stays null until a panel actually exists.

**`watches` is the check §13j describes.** If that rung stays blocked by a
dependency the scope put out of bounds, the boundary is in the wrong place —
and because §13c requires `blocked by` to be stated, it is visible in the
artifact rather than in an argument.

> **Writing them down changed two of them.** `low-dose CT → pill camera` was a
> resemblance rather than a handoff and is gone; `cancer → pill camera` was a
> real relation missing its reciprocal and is now there. Neither would have
> surfaced from prose — one-way adjacency is only visible once the boundary is
> an object something can read.
>
> **They are version 1 and unreviewed by any expert.** §13j says scope is the
> experts', so what is in `scope/` is a proposal in the correct format,
> waiting for the only people who can settle it.

## 13. The rosters

Seven more objects, in [`roster/`](roster/) — §13f's nine sub-agents made
concrete per field, with §13i's bodies marked.

| Field | reasoning + judging | embodied members | tools | envelope | its tenth, and the rung that admitted it |
|---|---|---|---|---|---|
| [computational imaging](roster/computational-imaging.json) | 10 | 3 | 13 | 4 | **system-designer** — rung 6 (owns 6.1–6.4) |
| [low-dose CT](roster/low-dose-ct.json) | 10 | 2 | 7 | 1 | **observer** — rung 1 |
| [medical physics](roster/medical-physics.json) | 10 | 2 | 9 | 2 | **feasibility** — rung 1 |
| [pill camera](roster/pill-camera.json) | 10 | 1 | 7 | 1 | **statistician** — rung 2 |
| [drug design](roster/drug-design.json) | 10 | 2 | 10 | 2 | **synthesis-planner** — rung 6 |
| [cancer](roster/cancer.json) | 10 | 1 | 9 | 1 | **currency** — rung 5 |
| [reverse aging](roster/reverse-aging.json) | 10 | 1 | 8 | 1 | **null-registrar** — rung 5 |

### Every field has one rung that is really five

A rung stated as one line stays a slogan: nothing about it can be blocked,
ordered, or shown to be skipped. So each field decomposes **the rung whose one
line hides a programme** — not the same rung in each, and the choice is stated
on each page.

| Field | decomposed | why that one | its floor |
|---|---|---|---|
| [computational imaging](computational-imaging.md#12b-rung-6-decomposed--the-hardware-system-design-sub-ladder) | 6 · joint hardware-algorithm design | designing hardware is five steps and the field is already on the fourth | a twin that models the **system**, not the operator |
| [low-dose CT](low-dose-ct.md#12b-rung-1-decomposed--the-detectability-pipeline) | 1 · the detectability pipeline | it is the floor **and** a programme; every later number is graded by it | the **task**, stated before the observer exists |
| [medical physics](medical-physics.md#12b-rung-5-decomposed--automated-qa-that-scales) | 5 · automated QA that scales | the field's defining constraint, and where the safety argument lives | a failure catalogue derived from **incident data**, not intuition |
| [pill camera](pill-camera.md#12b-rung-2-decomposed--the-variance-protocol) | 2 · the variance protocol | the field's failure mode lives inside it | enumerate the sources of variation — seed is not the largest |
| [drug design](drug-design.md#12b-rung-6-decomposed--the-closed-make-test-loop) | 6 · the closed make-test loop | the defining gap, and the only rung that **consumes matter** | a selection rule stated before anything is made |
| [cancer](cancer.md#12b-rung-5-decomposed--evidence-currency) | 5 · evidence currency | the only rung whose duty is **continuous** | the external sources, named and versioned |
| [reverse aging](reverse-aging.md#12b-rung-3-decomposed--the-outcome-link) | 3 · the outcome link | the field rests on it and it has **never been attempted** | the outcome, pre-registered before the analysis |

**Read the floors together.** Four of the seven are a specification written
before any work starts — a task, a catalogue, a source list, a pre-registration
— and none of the seven is a method. That is the same finding the main ladders
gave, one level down: what these fields are short of is not ideas.

> **Three sub-ladders contain a rung the agent may not settle alone**
> (§13j): pill camera's *smallest worthwhile effect* and reverse aging's *what
> association would matter* are clinical judgments, and low-dose CT's reader
> validation is human judgment as the endpoint. Each is marked in place.

**The nine are a floor and each field adds exactly one** — admitted only
because a ladder rung has no core owner, and named with that rung. The
validator enforces both, so a roster cannot grow by preference.

> **Every one of the seven additions is something that must not belong to
> `method`**, which is the same reason the twin and the verifier are separate
> in the first place. A detectability score owned by the method is an
> optimisation target; a feasibility ceiling computed by the planner is the
> planner's own limit wearing the word "infeasible"; a noise floor computed by
> whoever wants the gain is not a noise floor. **`null-registrar` is the
> sharpest case**: reporting a null is against the interest of whoever ran the
> experiment, so the duty goes to a role with no result to protect.

**No JUDGING member is ever embodied** — verifier, reproducer, teacher, writer —
and the validator fails if one is. Something that can make things happen is the
wrong thing to ask whether they happened, and stating that rule for the verifier
alone was the gap that let an embodied `reproducer` through an earlier draft.

**Embodiment is a kind of member, not a flag.** Each embodied member is a row of
its own with its own refusal and its own grant, which is what makes the envelope
enforceable — a physical act belongs to a member whose whole purpose is that
act, rather than being one mode of a member that also does something undoable.

