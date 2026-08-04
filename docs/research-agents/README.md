# The governor's research agents — how they are designed

**Status: design, 2026-08-04. The agent loop, the self-model and the RSI
proposal path are built and tested. Nothing domain-specific below is built.**

Six agents are **authored by the governor and listed in the market** like any
other: accepted the same way, found in agents-search the same way, installed by
anyone who wants them. Governor-authored means the governor wrote them, not that
anyone is kept out — there is no visibility gate on these.

[computational imaging](computational-imaging.md), [low-dose CT](low-dose-ct.md),
[medical physics](medical-physics.md), [pill camera](pill-camera.md),
[drug design](drug-design.md), [cancer](cancer.md).

Each covers a **field**, not a project. This page is what they share.

| Question | Document |
|---|---|
| What is a research agent, in the product? | [`../2026-08-04-ai4science-one-machine-design.md`](../2026-08-04-ai4science-one-machine-design.md) §11b |
| Where does the PWM come from? | [`../2026-08-04-sarsi-agent-market-and-pwm-design.md`](../2026-08-04-sarsi-agent-market-and-pwm-design.md) §13b |
| What is the self-awareness contract? | `sarsi_intelligence_level/` — *Functional Self-Awareness for SARSI Agents* |

---

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
