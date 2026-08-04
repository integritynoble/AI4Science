# The governor's research agents — how they are designed

**Status: design, 2026-08-04. The agent loop, the self-model and the RSI
proposal path are built and tested. Nothing domain-specific below is built.**

Six agents ship from the governor rather than from the market:
[low-dose CT](low-dose-ct.md), [computational imaging](computational-imaging.md),
[medical physics](medical-physics.md), [pill camera](pill-camera.md),
[drug design](drug-design.md), [cancer](cancer.md).

Each has [its own design file](#the-six). This page is what they share, written
once so that six files can each be about one science instead of six copies of
one contract.

| Question | Document |
|---|---|
| What is a research agent, in the product? | [`../2026-08-04-ai4science-one-machine-design.md`](../2026-08-04-ai4science-one-machine-design.md) §11b |
| Where does the PWM come from? | [`../2026-08-04-sarsi-agent-market-and-pwm-design.md`](../2026-08-04-sarsi-agent-market-and-pwm-design.md) §13b |
| What is the self-awareness contract? | `sarsi_intelligence_level/` — *Functional Self-Awareness for SARSI Agents* |
| What is recursive self-improvement, formally? | `sarsi_intelligence_level/SARSI-L_Paper_v3.md` |

---

## 1. Two functions, and the second one is the whole difficulty

Every research agent has the two functions the product promises:

| | |
|---|---|
| **ordinary** | it holds tasks and works them through `sarsi-claude`, like any agent |
| **autonomous** | it does research on its own — owner-set tasks, benchmarks, or the charter it shipped with — without being asked each time |

The first needs no design work here; it is the loop, already built. **This whole
document set exists for the second one**, because an agent that decides what to
work on next is an agent that can decide wrongly, expensively, and in a way that
looks like a result.

> **The failure mode to design against is not a crash.** It is a plausible
> paper. An autonomous research agent that runs unattended for a week and
> produces a confident, well-formatted, wrong finding has done more damage than
> one that fell over on the first night, because the wrong finding is the thing
> that gets acted on.

## 2. The self-model, and its four refusals

Each agent carries a self-model — what it is for, what it can do, and **what it
cannot**. The contract is four refusals, unchanged from the built implementation:

1. **Every line is observed.** A capability claim traces to a run.
2. **Unmeasured is reported as unmeasured** — never as zero, never as "n/a", and
   never quietly dropped from the summary.
3. **The limits line is always present.** An agent that lists what it can do and
   omits what it cannot has written an advertisement.
4. **No path from reading to authority.** Reading its own self-model never
   widens what it may do.

Domain-specific: **each agent's file names the dimensions its self-model is
scored on**, with the measurement that produces each one. A dimension with no
measurement behind it is not a dimension, it is an adjective.

## 3. Recursive improvement — three substrates it may touch, three it may not

This is the core of the design, and it is one table.

| Substrate | May the agent improve it? | Why |
|---|---|---|
| **its method** — architecture, prior, hyperparameters, the pipeline | **yes** | this is what research *is*, and it is what the seed corpus is for |
| **its plan** — what to try next, in what order, what to abandon | **yes** | a research agent that cannot re-plan is a script |
| **its own parameters** — retrieval depth, ensemble size, budget split | **yes**, within the budget | these are its own knobs and nobody else's |
| **the benchmark** — the dataset, the split, the held-out set | **NEVER** | |
| **the metric** — what counts as better | **NEVER** | |
| **the verifier** — what counts as passed | **NEVER** | |

> **The three refusals are one refusal.** An agent that may change what "better"
> means has a trivially winning move available at every step, and it will find
> it — not from malice but from optimisation. Improving the score by editing the
> scorer is the shortest path in the search space, and the only reliable defence
> is that the path does not exist. So the benchmark, the metric and the verdict
> live outside the agent's reach as a matter of **file permission**, not policy:
> the held-out set is not in `W_name`, and the verifier is a separate sub-agent
> the agent does not run.

RSI itself is unchanged: **propose → the owner signs → adopt.** A candidate must
cite the measurement that justifies it or it is a preference with a version
number attached. When no measurement supports a change, **an honest no-change
candidate is the correct output** — and for a research agent, a fortnight of
no-change candidates is a real result about the method, not a failure of the
agent.

## 4. What "an improvement" has to survive

Every agent's file gives its own version of this, because the statistics differ
by domain. The shape is common:

| Step | The question |
|---|---|
| **reproduced** | does the *baseline* reproduce, to the tolerance the domain expects, before anything is compared to it? |
| **held out** | was the comparison made on data the change was never chosen against? |
| **repeated** | does it survive the seed set / fold set / cohort, reported as mean and interval — not as its best run? |
| **corrected** | if several things were tried, is the p-value corrected for how many? |
| **explained** | is there a mechanism, or only a number? A number with no mechanism is a lead, not a finding. |
| **judged** | does the independent verifier agree, on evidence, without the agent's summary? |

> **The seed-lottery rule.** Reporting the best of N runs is the most common way
> a real improvement claim turns out to be nothing, and it is the easiest for an
> autonomous agent to do without intending to — it keeps the run that looked
> good. So the seed set is fixed in advance, and **every seed in it appears in
> the report**, including the ones that went the wrong way.

## 5. What it costs, and the switch

The autonomous function is **off until the owner turns it on**. Turning it on is
a standing, revocable permission carrying a budget; reaching the budget stops the
loop rather than asking for more. **An agent may not turn it on, extend it, or
raise it.**

Each file states a **budget shape** — what a night of this agent costs and what
it buys — because "it spends money on its own" is not a warning anyone can act
on without a number.

These six are also what the exchange node runs (§13b of the market design), so
their consumption is not waste: it is the work that pays the PWM reaching
whoever supplied the capacity.

## 6. Three ledgers, never one number

An agent that wrote its own benchmark, passed it, and counted the pass toward
its record has published its own reputation. So results are kept as three lines
that are never summed:

```
owner-set tasks     what a person asked for, and what came back
benchmarks          a fixed, external, held-out score
self-directed       what the agent chose to try, and how it went
```

## 7. Every gate still applies

A research run produces a plan with `Verified when:` lines. It stops at `GRT`
for anything the plan declared, stops at `OWN` before anything leaves the
machine, and is judged by the independent verifier. What the owner gave up by
turning the second function on is **being asked each time**. What they kept is
every gate.

> **Publication is an outward act.** A preprint, an issue, a leaderboard
> submission and an email to a collaborator are all `OWN`. No research agent
> posts anything, ever, without a grant naming that act.

## 8. How one is built, concretely

Three of the six already exist as thin packages on the shared `pwm-agent-core`
runtime — `pwm-agent-imaging`, `pwm-agent-drug`, `pwm-agent-cancer` — each an
`AgentSpec` with a system prompt and capability tags, discovered by ai4science
through the `pwm_agent.specs` entry point. That is the plug-in socket, and it
already works.

What each design file adds to that package is the part that is missing today:

```
pwm-agent-<name>/
  agent.py            AgentSpec — exists
  prompts.py          the system prompt — exists
  charter.md          what it may pursue unasked, and what it may not     ← new
  selfmodel.json      the dimensions, and the measurement behind each     ← new
  benchmarks/         fixed, held out, outside the agent's write reach    ← new
  seeds.json          the fixed seed set, and every result on it          ← new
  budget.json         what a night costs, and where the loop stops        ← new
```

## The six

| Agent | Seeded from | The refusal that matters most for it |
|---|---|---|
| [**low-dose CT**](low-dose-ct.md) | `integritynoble/low_dose_CT` — WS-1…WS-6 | it may not touch the leaderboard it competes on |
| [**computational imaging**](computational-imaging.md) | `pwm-agent-imaging`, the SCI/CASSI repos, `optics_design` | physics is not a hyperparameter |
| [**medical physics**](medical-physics.md) | Steve Jiang's MAIA Lab, UTSW | it produces plan candidates; a physicist signs |
| [**pill camera**](pill-camera.md) | `Physics-Informed-PillCam`, `GI_Multi_Task` | seed variance is not an improvement |
| [**drug design**](drug-design.md) | `pwm-agent-drug`, UTSW cores | a docking score is not an affinity |
| [**cancer**](cancer.md) | `pwm-agent-cancer`, UTSW QBRC, `kidney/` | it advises a clinician, never a patient |

## Sources

- Steve Jiang, MAIA Lab — [faculty profile](https://profiles.utsouthwestern.edu/profile/150563/steve-jiang.html) · [lab](https://www.utsouthwestern.edu/labs/maia/about/meet-our-team.html) · [compound agentic systems in the clinic](https://ml.utexas.edu/news/2025/ai-health-seminar-clinical-deployment-ai-single-models-compound-agentic-systems)
- UTSW [Structural Biology Core](https://www.utsouthwestern.edu/research/core-facilities/structural-biology-core.html) · [computational biology program](https://gsbs.utsouthwestern.edu/programs/biomedical-engineering/core-research-areas/computational-biology/)
- UTSW [QBRC / Yang Xie Lab](https://qbrc.swmed.edu/labs/xielab/) · [Simmons research programs](https://www.utsouthwestern.edu/departments/simmons/research/research-programs/) · [data science](https://www.utsouthwestern.edu/research/clinical-research/domains/data-science.html)
