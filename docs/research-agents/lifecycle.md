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

**Independence here is temporal and authorial — not informational.** This is
worth stating plainly because the obvious guess is wrong: it is *not* achieved
by hiding the workspace from the verifier.

- **Temporal.** The criterion is fixed **before the result exists**. A verdict
  against a bar written after seeing the number is not a verdict.
- **Authorial.** The verdict is written by the verifier and **never** by the
  worker. Its signature is the thing that makes it a verdict.
- a verifier is prompted to **refute**, not to review — the default answer is
  "not established", and it must be argued out of that;
- verifiers are **perspective-diverse** where a claim can fail in more than one
  way. Three identical skeptics catch less than one correctness checker, one
  reproduction checker, and one leakage checker;
- **the proposer may never improve the verifier.** Same rule as the
  never-improvable benchmark, same reason.

> This is why a shared workspace costs nothing. The group can see the same
> files — that is what makes it one agent — because independence was never
> being carried by what the verifier could see. It is carried by *when the bar
> was set* and *whose name is on the verdict*.

### The four ways a result gets verified

The record says which of the four each verdict was, because they are not
equally strong.

| | how | strength |
|---|---|---|
| 1 | **a person verifies** — the plan states what counts as verified *before* the work, and the evidence is what that line asked for | the only one that is not itself an agent's output, which is why the format never changes even when it is rarely used |
| 2 | **a sub-agent verifies** — the group's own verifier, judging against the pre-written criterion | routine, and only as good as the criterion |
| 3 | **another field's agent verifies** — a different principle, a different twin, a different corpus, reproducing the claim | the strongest check available. Agreement between two agents sharing a codebase is nearly free; agreement between two sharing only the world is not |
| 4 | **a person is taught to verify, and then does** | the escape hatch from irrelevance — below |

> **The failure this is built against is agreement without independence.** N
> agents from one lineage confirming each other is **one opinion with N
> signatures.** A verification counts only when the verifier could have produced
> the opposite verdict.

A claim survives on a quorum, and the quorum, the lenses, and the dissent are
all recorded. A verification that records only its verdict is an assertion.

**What the person still does at stage 2:** audits sampled claims end to end,
keeps the guardrail list, and holds the off switch. The audit rate is a declared
number, not a vibe — and it must be set so that a systematic verifier failure is
caught in bounded time.

### Stage 3 — autonomous (not built)

Agents verify agents. The person reads summaries and holds the switch.

**Three conditions, all of them, before an agent may run this way — and they are
conditions on the *field*, not on the agent's confidence:**

1. **Verification is independent by construction.** Not the same lineage, not
   the same corpus, not the same twin. Cross-field verification is available and
   used.
2. **A person could still check any result.** The evidence chain is complete and
   the teacher can produce the path to checking it on demand. *Untested for a
   year is acceptable; unavailable is not.*
3. **The owner signed this specific standing, with a budget** — escalated once,
   revocable at any round. **No agent may grant it, extend it, or grant it to
   another agent.** A high ceiling is permission to act, never permission to
   become more permitted.

> **What is given up is real: the human signature on the individual adoption.**
> What is kept is every gate, the complete chain, and the ability to revoke. If
> the three conditions cannot be stated as met, the stage is not available — and
> an agent arguing that it should be is making an authority claim, which is the
> one claim it may never make.

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

### A field's research ends. Its usefulness does not.

**Classical physics is not worth researching and is holding up every bridge.**
That is the normal fate of a finished field, not a sad one, and retiring a
field's *solutions* along with its *frontier* would throw away the only thing
the research was for.

Three things survive a collapse of either kind:

| what survives | why it must |
|---|---|
| **its solutions** | a method that works does not stop working because nobody is publishing about it |
| **its tools** | other fields' agents plug them in; a tool everyone uses is worth as much as an agent |
| **its author's share** | the author did the work of writing it, and a field going quiet is not them being unwritten |

So the agent goes **out of research routing while staying usable** — retired
from *research*, not from *service*. It still answers, still runs its solutions,
still earns for whoever wrote them; it simply stops being asked what to solve
next.

> **The daily-life half is the point.** A reconstruction that denoises a scan is
> worth the same on the day its field stops publishing as it was the day before.

### What a collapsed field's page must say

Not a hidden state. Every field's page carries:

1. **when a person last checked one of its results**, and how long the chain of
   agent-only verification has run since;
2. **what was physically done** during that chain — because an embodied act is
   the one thing a reader cannot undo;
3. **what of it is still in service** — whether the solution someone is about to
   install is maintained, or is a finished thing that works and will not change
   again. Both are fine answers; not saying which is not.

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

**Splitting is the good ending.** When a small sub-scope keeps producing results with more energy and meaning than the field around it, that is not a
sub-topic — it is a new field, and it gets its own agent, its own page, and
its own problem list in its own order. Classical physics did not absorb
quantum mechanics; quantum mechanics left. The new field's principle is a new
entry, not an amendment, and the old field's agent keeps its history exactly as
a retired agent does.

When the test fires, the new field gets its own charter, its own never-improvable
benchmark, its own verifier, and its own agent. It does **not** inherit the
parent's benchmark, because inheriting it would re-import the assumption that
made the question unscoreable. It may inherit methods, data and tools freely.

Each field document ends with its own candidate fission regions. They are
guesses and are labelled as such.

---

## Scope, and the experts who set it

A charter says what an agent may never touch. **Scope** is a different thing: it
is which part of the field this agent actually works on, and unlike the charter
it is *expected to move*.

**Scope is set by experts in the field. Not by the agent, and not by the owner
alone.** The owner signs adoptions because the owner pays; the experts set scope
because scope is a claim about what the field needs next, and that is a
judgement about the field rather than about the run. An agent that chose its own
scope would be choosing which questions count — which is the same failure as
choosing its own benchmark, one level up.

Each field document names **which kinds of expert** it needs. Roles, not people:
this is a public repository and no individual is named in it.

### What the experts decide, and what they do not

| they decide | they do not decide |
|---|---|
| what part of the field is in scope, and what is deliberately out | whether a particular run passed — that is the verifier's job |
| which problems are on the queue, and in what order | which parameter setting wins |
| when the benchmark no longer represents the field | anything inside a night's search |
| whether the field is finished, or has split | how the agent spends its compute grant |

### The part this corrects: never-improvable is about the agent

The benchmark, the metric and the verifier are never improvable **by the
agent**. That was always the rule and it is what makes recursive improvement
mean anything. But a benchmark that no human may ever revise does not stay
honest — it ossifies, and the field grows past it while the scores keep looking
fine.

So the full rule has two halves, and both are needed:

> **The agent may never change what judges it. The field's experts may — and
> when they do, it is a declared act that re-bases the history.**

A benchmark revision is not an improvement and is never reported as one. It
invalidates comparison with everything measured before it, and the record says
so. That is the price of keeping it current, and it is why revisions should be
rare, argued, and signed.

### Guards, because an expert panel is a governance surface

- **Experts must be able to narrow scope, not only widen it** — and to declare a
  field finished. A panel that only ever expands is not a check, it is an
  appetite.
- **The agent does not choose its experts.** An agent that selected who reviews
  it has selected its own verdict by a slower route.
- **Recusal is recorded.** An expert whose own method is in the comparison does
  not adjudicate that comparison, and the record names the recusal rather than
  quietly routing around it.
- **A scope change is signed like an adoption**: who, what changed, on what
  evidence, and what it invalidates.

### Scope is the last human function to go

At stage 3 the verification is delegated. At stage 4 a person may check nothing
at all. **Scope-setting does not follow that curve**, because "is this worth
researching" is not a measurement — no verifier answers it, and no amount of
agent-only verification produces it.

That is also what makes collapse-by-indifference legible rather than mysterious:
a field where nobody cares is a field whose experts stopped setting scope. The
page should be able to say when that happened.

And at fission, the new field needs **its own** experts. They are usually not
the old field's: classical physicists were not automatically quantum experts,
and a panel carried over intact is how a new field inherits the assumption it
was supposed to escape.

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

### One workspace, one voice — the group is a single agent

The group is not a federation of agents that happen to cooperate. **It shares
one workspace and speaks as one agent**, and from outside there is no seam:

| | the group has exactly one |
|---|---|
| **workspace** | the same run directory — data, code, results, provenance. One record of what happened, not a record per member |
| **charter** | one field it may work in, one set of things it may never touch |
| **budget and switch** | one grant, one off switch. A sub-agent does not have its own allowance |
| **set of ledgers** | `owner_set`, `benchmark`, `self_directed` — the group's work, not each member's |
| **voice** | one answer to the person who asked, and one signature surface for the owner |

**Communication happens through the workspace, never through side channels.**
Members exchange artifacts and an append-only message log that lives in the same
directory as the results. This is not a stylistic preference: an exchange that
does not land in the workspace cannot be audited, and a group whose members can
talk privately is a group whose reasoning cannot be reconstructed afterwards.

**This is not a hole in the rule that there is no channel between two agents.**
That rule stops one agent acting on another's behalf across different scopes.
**Inside one research agent there are no two scopes** — planner, runner,
verifier, teacher and bench are all on the same problem, on the same evidence,
under one grant. Sharing a workspace does not widen anything; it is the
workspace that agent already had. The boundary moves down a level and the rules
keep their shape.

| | inside one group | between groups |
|---|---|---|
| workspace | **shared** | separate |
| talking | **direct** | publish, never browse |
| task list, ceiling | one | one each |
| a fact travels by | being written where all of them read | being published and read at plan time |

### The one thing "in agreement" must not mean

Sharing a workspace makes members agree about **what happened** — one record, so
the runner and the verifier cannot hold different accounts of what was run.
That is the point, and it is why there is one self-model rather than two: *the
first thing to diverge would be the part that flatters it.*

It must not make them agree about **whether it is good**:

> **They share the evidence. They do not share the verdict.**

The verifier reads the same files as the runner and reaches its own conclusion.
A group where the verdict is agreed by construction has replaced verification
with unanimity — and that is not a smaller version of the closed loop this
architecture forbids, it *is* that loop, moved inside one agent where it is
harder to see.

The practical test: **a group verdict that cannot say which member reached it,
from what evidence, and what would have changed its mind, is one voice with
several names.**

**"Like one body" is exactly the right image, and it cuts both ways.** A body
has one memory and acts as one thing — and a body whose nerves only ever report
what the hand hoped is one that burns itself.

### Nine members are the floor

A field may add members. It may **not** remove these — an agent missing the
verifier or the twin is not a research agent with fewer parts, it is *a method
with a scoreboard*.

| member | what it does | why it is separate |
|---|---|---|
| **literature** | finds and reads prior work, with citations | reading and doing must not share a context, or the agent finds what it set out to find |
| **twin** | maintains the forward model | the thing a method is graded against; the method's author may not own it |
| **corpus** | fetches and validates real data, refuses when absent | a benchmark that silently substitutes synthetic data produces numbers that are not results |
| **method** | proposes and implements candidates | the only one that writes the thing being judged |
| **runner** | executes runs | keeps cost and placement out of the method's hands |
| **verifier** | judges against the criterion written before the result | the verdict is its signature |
| **reproducer** | re-runs a published result from its artifacts alone | catches the result that only exists on the machine that made it |
| **teacher** | derives the curriculum from the evidence chain | teaching is a product and must be checkable like one |
| **writer** | assembles the field page and the paper | writing last, from the record, never from intent |

> **Two of these are deliberately not the worker's.** The **twin** and the
> **verifier** answer *"what should this produce"* and *"did it"* — and an agent
> owning its own answer to both can pass any benchmark it likes by moving one of
> them.

### Three kinds of member, defined by what their acts reach

| kind | members | reaches | can it be undone |
|---|---|---|---|
| **reasoning** | planner, runner, self-model | a file in the workspace | yes, trivially |
| **judging** | domain verifier, teacher | a verdict and a check | it is the thing that decides, so it is never the thing that acts |
| **embodied** | bench, stage, arm | **the world** | **no** |

The **teacher** is a member, not a formatting step. Its deliverable is the
owner's own check, and its refusal is the sharp one: *it refuses to report a
pass it cannot hand the owner a way to re-run.*

### The tools, and why two of them are named to the version

Sub-agents *do or judge*; tools are what must be present to run. A tool that is
absent is refused **by name**, never worked around.

| tool | for |
|---|---|
| the field's own solvers | the reconstructions, screens, plans or clocks the field is about |
| **dataset clients** | TCIA, DUD-E, GDC, OpenKBP, Kvasir, CAVE, GEO — each **named, versioned and checksummed**, because a corpus that changed underneath a result silently invalidates it |
| **GPU lease** | runs this machine cannot hold, with the platform and capability declared *before* leasing rather than probed after |
| **registry client** | publishing and querying the four layers |
| plotting / TeX | figures and papers as artifacts, not as screenshots |
| the market | installing another author's tool when the field needs one |

> The row with teeth is the corpus client. An agent whose data is missing must
> **refuse and say how to get it**. Generating stand-in data and proceeding is
> how a field fills with results nobody can reproduce — and this is not
> hypothetical: it fired the first time these benchmarks met a machine with no
> corpora, and the refusal named the fetch command.

### The rules a body forces

> **An embodied act is irreversible, and is treated as irreversible by default.**
> A reversibility question is asked before anything else, and for a body the
> answer is always no — so an embodied act needs the grant that irreversible
> acts need, **every time. A standing night grant does not cover it.**

Two refusals follow:

- **An embodied sub-agent may not verify its own act.** The verifier judges from
  *evidence the body produced*, never from the body's report of what it did. A
  closed loop in software gives you a wrong number; a closed loop here gives you
  a wrong number **and a changed bench**.
- **The group's ceiling is the LOWEST of its members', not the agent's.** An
  agent released to a capability whose arm could act one level higher has been
  released to that higher level by the back door. The ceiling belongs to the
  act, and the act with a body sets it.

And the honesty rule, which this system already applies to anything it cannot
retract — *this will not pretend it did*. A bench **reports what it moved, never
what it intended.**

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

**The self-model is written by observation, never by assertion.** Its lines come
from outcomes — verdicts, benchmark results, refusals — recorded by the part of
the system that judges, not by the part that benefits. An agent that could write
its own self-model would be writing its own reference. It is also **one file
read by both functions**: two would give the agent a private record beside the
one the owner reads, and the first thing to diverge would be the part that
flatters it.

> **"Unmeasured" has to stay expensive to write.** The moment it costs nothing
> to declare, everything hard becomes unmeasured and the queue empties itself.
> So an unmeasured dimension carries **what measurement would settle it** — the
> same entry fee a ladder rung pays — and a self-model with unmeasured lines and
> no paths to measurement is a finding about the agent rather than about the
> field.

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

**The curriculum is derived from the evidence chain, not written beside it.**
For a claim, the path back through solution → benchmark → twin → principle is
exactly what someone needs in order to check it, in exactly the order they need
it. A tutorial written separately drifts from the method; a tutorial that *is*
the chain cannot.

| | |
|---|---|
| what it produces | the shortest path from what the learner already knows to running the benchmark and reading the number |
| **how it is tested** | **the learner runs it and gets the same number.** The teaching succeeded if the check succeeded |
| what it may not do | grade its own teaching by asking the learner whether they felt they understood |

> **This is the field's escape hatch from irrelevance.** A field only its own
> agent can check is a field that has left the human record — a state to be
> declared, never drifted into.

This is why every field document leads with a failure. A page with no negative
results teaches nothing, because it never shows the reader what checking looks
like when it bites.
