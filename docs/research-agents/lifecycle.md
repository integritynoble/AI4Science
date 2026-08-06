# The life of a research agent — from assistant to the end of its field

Every agent in this directory is at stage 1 of five. This file describes all
five once, so the seven field documents can say what *their* field looks like at
each stage without restating the machinery. Where a stage is already built, the
code is named; where it is not, it is marked **not built** rather than described
in the present tense.

The stages are not a roadmap with dates. They are an ordering: each one is
unreachable until the one before it holds, and the reason is always the same —
**verification is the bottleneck, never generation.** An agent that proposes
faster than anything can check it has not advanced its field; it has only moved
the queue.

---

## The five stages

| | stage | who verifies | what the human does | status |
|---|---|---|---|---|
| 0 | **assisted** | the person | everything, by hand | passed |
| 1 | **proposing** | the benchmark, the person signs | reads the search log, signs or refuses each adoption | **here** |
| 2 | **delegated** | independent verifier agents; person audits a sample | audits, spot-checks, keeps the policy | not built |
| 3 | **autonomous** | agents verify agents, under a signed policy | reads summaries, holds the off switch | not built |
| 4 | **collapse or fission** | the field is finished, or it splits | decides whether anything is left worth asking | not built |

### Stage 0 — assisted

The agent runs what it is told and reports. Every number is checked by a person
before it is believed. This is where most "AI for science" sits today, and it is
not nothing: reproducing a published method correctly is real work.

### Stage 1 — proposing (where all seven are)

Two functions, and the line between them is the whole design:

**On demand.** A person asks for something; the agent does it and reports.
`run_user_task` — works with the autonomous switch **off**, because ordinary help
must not require the permission to spend someone's money unasked. If the off
switch meant "the agent is useless" rather than "the agent does not act
unasked", nobody would ever turn it off.

**Autonomous.** The agent searches its own declared parameter space against its
own field's benchmark, and proposes. `autonomous_loop` — refuses to start
without an owner-set switch and budget, and `switch.agent_turn_on()` raises
`PermissionError` by construction. Every night's log opens with the agent trying
and being refused, which is the cheapest possible daily proof that the guard is
real.

**Adoption is the owner's signature, always.** The agent proposes; it never
adopts. What it takes to earn a signature is in each agent's *"What an
improvement must survive"*: a paired comparison against the incumbent on the
same seeds, validation on seeds not used for selection, Holm correction across
the night's validation tests, no guardrail breach, and a stated mechanism.

**The three ledgers are never summed.** `owner_set`, `benchmark`,
`self_directed` — work a person asked for, work scored by the field's own
benchmark, and work the agent chose for itself. Summing them is how an agent
reports a hundred successes that are all its own homework.

### Stage 2 — delegated verification (not built)

The person stops checking every result and starts auditing a sample. This
requires something that does not exist yet: **verifier agents independent of the
proposer.**

Independence has to be structural, not promised:

- a verifier does **not** share the proposer's context, and is not the same
  agent in a different prompt;
- a verifier is prompted to **refute**, not to review — the default answer is
  "not established", and it must be argued out of that;
- verifiers are **perspective-diverse** where a claim can fail in more than one
  way. Three identical skeptics catch less than one correctness checker, one
  reproduction checker, and one leakage checker;
- **the proposer may never improve the verifier.** This is the same rule as the
  never-improvable benchmark, for the same reason.

A claim survives on a quorum, and the quorum, the lenses, and the dissent are
all recorded. A verification that records only its verdict is an assertion.

**What the person still does at stage 2:** audits sampled claims end to end,
keeps the guardrail list, and holds the off switch. The audit rate is a declared
number, not a vibe — and it must be set so that a systematic verifier failure is
caught in bounded time.

### Stage 3 — autonomous (not built)

Agents verify agents. The person reads summaries and holds the switch.

This is only reachable when stage 2 has produced enough audited history to
estimate the verifier's own error rate — you cannot delegate verification to a
process whose failure rate you have never measured. The gate is a number: **the
verifier's false-accept rate on human-audited claims**, tracked over time, with
the audit continuing at a reduced rate forever so the estimate never goes stale.

**What stays fixed even here.** The benchmark, the metric, and the verifier
remain outside the improvable set. An agent that can rewrite its own scorer does
not improve; it drifts, and it reports success the whole way. Recursive
self-improvement is only meaningful *against a fixed measure* — the moment the
measure moves with the method, the improvement is unfalsifiable and therefore
uninteresting.

The self-improving part is the method, the plan, and the agent's own parameters.
That is all it has ever been. Stage 3 does not widen it; it only removes the
human from the signing step, and only for adoptions inside a policy a human
signed once.

### Stage 4 — collapse, and what comes after

A field ends in one of two ways.

**Collapse by exhaustion-of-interest.** Nobody cares. The remaining questions
are answerable and unimportant. There is no shame in this and it is more common
than the alternative; most fields end here. The correct action is to stop
spending on it and say so.

**Collapse by saturation.** Everything checkable has been checked. New results
are produced and verified by agents faster than any person can follow, and human
verification is no longer the safeguard — it is the bottleneck, and a worse
check than the automated one. The field continues to produce, but it produces
*to machines*. Humans read summaries and set direction.

Both are called collapse because they look identical from inside: the human
verification rate goes to zero. They are opposite in meaning, and the way to
tell them apart is whether **anyone acts on the results**.

> **Neither is a licence to stop measuring.** A saturated field still has a
> fixed benchmark and a fixed verifier, and both must keep running. Collapse
> means humans stopped checking each result, not that nothing is checked.

### Fission — when a new field and a new agent are warranted

Inside a collapsed or collapsing field, a small region can carry far more
meaning than the rest — the way anomalies in classical physics carried the whole
weight of what became quantum mechanics.

The test for whether that region deserves its own field and its own agent is
sharp, and it falls out of the architecture:

> **A new field is warranted when a question in the old field cannot be scored
> by the old field's benchmark without changing it.**

Because the benchmark is never-improvable, a question that requires changing it
is by definition outside the field. That is what a paradigm boundary *is*, in
this system: not a change of subject, a change of what counts as an answer.

Blackbody radiation was not a hard classical problem; it was a question
classical mechanics could not score. The fission test would have caught it.

When the test fires, the new field gets its own charter, its own never-improvable
benchmark, its own verifier, and its own agent. It does **not** inherit the
parent's benchmark, because inheriting it would re-import the assumption that
made the question unscoreable. It may inherit methods, data and tools freely.

Each field document ends with its own candidate fission regions. They are
guesses and are labelled as such.

---

## The agent is a group, and some of it has a body

Nothing in this directory is one model. A research agent is a **group**: a
proposer that suggests, verifiers that try to refute, and executors that carry
work out. Stage 2 is exactly the moment that group stops being a figure of
speech.

As robots take over manual laboratory work — and they will, sooner than the
verification problem gets solved — some of those executors stop being software.
An **embodied sub-agent** mounts the optic, positions the phantom, pipettes the
plate, runs the synthesis, loads the sample. Each field document names which of
its sub-agents get bodies.

> **This makes verification more important, not less.** The usual reading is
> that robots remove the bottleneck. They remove the *labour* bottleneck, and
> labour was never the binding constraint on whether a result is true. A lab
> that can run a thousand experiments a week and check ten of them properly is
> in a worse epistemic position than one that runs ten and checks all ten — it
> produces more claims per unit of evidence, which is precisely the failure this
> whole architecture exists to prevent.

### What a body changes, concretely

| | compute sub-agent | embodied sub-agent |
|---|---|---|
| **an action is** | reversible — re-run it | **irreversible** — the sample is consumed, the reagent spent, the tissue used |
| **verified by** | reproduction: run it again from the seed | **provenance**: record what was actually done, because it cannot be run again |
| **a mistake costs** | compute | material, calendar time, and sometimes a sample that cannot be replaced |
| **the gate is** | budget | budget **and** a physical-safety interlock that is not a scored quantity |

The third row is why an embodied act cannot use the same permission as a compute
act. A night's standing grant is a licence to spend compute. It is **not** a
licence to consume a patient sample, book instrument time, order a synthesis, or
move anything that can injure a person. Those stay owner-signed per act, at every
stage including stage 4.

### Three rules for embodied sub-agents

1. **The proposer may never improve the executor's safety limits.** Same rule as
   the verifier, same reason. An agent that can widen a physical interlock has
   no interlock.
2. **Provenance replaces reproduction.** Since the act cannot be repeated,
   what happened must be captured at the time — instrument logs, actual volumes,
   deviations, timestamps. A wet-lab result whose provenance was not recorded is
   not a weak result; it is an unverifiable one.
3. **A body does not unblock a governance problem.** This one is easy to get
   wrong and expensive. Where a field document marks an item **blocked**, look at
   *what* blocks it: several are blocked on consent, follow-up time, or a data
   agreement — and no amount of robotic throughput touches any of those. Cancer's
   prospective validation and reverse-aging's outcome linkage are both in this
   category. Robots make the fast parts faster and leave the binding constraints
   exactly where they were.

## Self-awareness, functionally

"Self-aware" here means something narrow and checkable. The agent holds a model
of itself with five parts, all of them already built:

| part | what it knows | where it lives |
|---|---|---|
| **charter** | the field it may work in, and what it may never touch | `Charter` |
| **self-model** | what it has measured, on which dimensions, and how well | `SelfModel` |
| **field map** | what it has **not** measured, and what kind of gap each one is | `FieldMap` |
| **budget** | what it has spent and what remains | `Budget` |
| **ledgers** | who asked for each piece of work | `Ledgers` |

**The field map is the part that matters, and it is the part usually missing.**
An agent that knows what it has measured will optimise that. An agent that knows
what it has *not* measured can choose to go and look. The map's states are
`untried`, `unreplicated`, `uncompared`, `proxy_only`, `settled` — and
`proxy_only` in particular is a standing admission that a number stands in for
the thing actually cared about.

The loop stops when the map is dry: *"nothing left unchecked that this agent can
check"*. An agent that cannot say that will run forever, re-deriving the same
answer and calling it progress.

> **Measured and unmeasured are kept apart on purpose.** Merging them is the
> single most common way a system starts believing its own summary. Every report
> in this codebase prints them separately.

### What self-awareness is not

It is not introspection about experience, and nothing here claims otherwise. It
is bookkeeping about evidence, held to a standard the agent cannot relax,
because the standard lives outside it.

---

## Recursive self-improvement, and its hard boundary

RSI here is exactly: **propose → verify against a fixed measure → an authority
signs → adopt**. Stages 1 through 3 change only *who signs*. Nothing else moves.

Three substrates are improvable — **method**, **plan**, **own parameters**.
Three are not — **benchmark**, **metric**, **verifier**.

That split is the entire safety argument, and it is not a policy that can be
argued around: the benchmark's answer key is never staged into the sandbox, and
scoring happens outside it. The agent cannot reach the thing that judges it.

**Why the loop is safe to close at stage 3 and not before.** The danger in
autonomous RSI is not that the agent improves too fast. It is that the agent
improves its *measurement* and reports the result as improvement — and every
example of that in this codebase was found by comparing against something fixed:
an analogue leak that made screening look perfect, a NaN that disabled an
optimiser, a seed that did nothing and produced `p = 0`, a search bound that
excluded the working value, a noise region that measured anatomy instead of
noise. Five of six looked like method failures and were measurement failures.

Every one of those was caught because *something did not move*. Remove the fixed
measure and none of them are catchable — not by a better agent, not by more
compute, not by a smarter verifier that the same agent could also improve.

---

## How an agent teaches a person to check it

Verification does not scale by making people faster. It scales by making more
people capable, and that is a thing the agent has to actively produce rather
than a side effect of publishing a log.

Each agent owes three artifacts:

1. **The reproduction path.** The exact seeds, the fixed benchmark, the command.
   A result that cannot be re-run by its reader is a claim, not a finding.
2. **The check that would have caught the last mistake.** Every documented
   defect in this directory comes with the specific check that failed to exist.
   That check, written down, is the most transferable thing the agent produces.
3. **The disagreement.** What the agent expected, what it got, and where a
   reasonable person would still doubt it.

> **The teaching test:** after reading, can the person independently construct a
> measurement that would have refuted the claim? If not, they have been
> informed, not taught — and at stage 2 they will approve what they cannot
> check, which is worse than not auditing at all.

This is why every field document leads with a failure. A page with no negative
results teaches nothing, because it never shows the reader what checking looks
like when it bites.
