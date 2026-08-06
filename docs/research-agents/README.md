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
| What is a research agent, in the product? | [`../2026-08-04-ai4science-one-machine-design.md`](../2026-08-04-ai4science-one-machine-design.md) §11b |
| Where does the PWM come from? | [`../2026-08-04-sarsi-agent-market-and-pwm-design.md`](../2026-08-04-sarsi-agent-market-and-pwm-design.md) §13b |
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
| [drug design](drug-design.md) | DUD-E — 15,288 molecules, 6 targets | **passes** — EF@1% 41–56 at 51–77% of ceiling, 2.4–2.9× the property baseline, on a series-disjoint split |
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
