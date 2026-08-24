# DLI-Bench — the delegation benchmark, built

**Status: all eight levels run.** DL0–DL3 and DL5 are task generators — 120
executable instances across four families. DL4, DL6 and DLΩ are **environments**,
because a static task cannot pose them. Every verifier is shown to *pass
competent work* as well as refuse an empty attempt, and every environment is
shown to *be winnable* as well as to reject naive play. Joined to a 96-card
specification covering all eight levels. 174 tests.

The framework this implements is *Delegation Intelligence*, and the repairs it
takes as read are in *Difficulty Is Not the Index*. The one-line version:

> A delegation level is demonstrated when an agent **reliably** completes tasks
> of the corresponding difficulty under the permitted human-intervention
> budget, judged by something that did not perform the work.

Every clause there is a design constraint, and each is enforced somewhere
mechanical rather than asked for in prose.

---

## 0. Two halves, joined

This benchmark was written twice, independently, and the two halves are
complementary rather than rival.

**The catalogue** — `dataset/catalog_v0_1.jsonl`, 96 cards — is the
specification. All eight levels, six families, with each card's intervention
budget, escalation policy, CID ceiling, reliability target, time budget and
split. It is complete across the scale and says so of itself:

> `asset_bundle_status`: *"specification starter; executable assets should be
> generated from the seed and kept hidden for certification"*

**The generators** are those executable assets: instances that build themselves
from a seed, with withheld keys and verifiers proven to pass a correct solution
as well as refuse an empty one. They run, and they reach five of the eight
levels.

`dli_bench catalog` joins them, turning that blanket status line into a
per-card fact:

```
cards specified: 96
cards a generator can pose: 28
cards that are specification only: 68
```

That is the honest state: a plan for 96 tasks, and a measurement for 28 of
them — every *level* is now posed by something, but not every family at every
level. The remaining gap is `document`, which nothing poses at any level, and
the family/level cells the catalogue names that no generator or environment
covers yet.

### The two scales disagreed, and it was a scale

The catalogue rates difficulty 0–5; this suite bands from 0–4. Read naively,
54 of 84 cards banded somewhere other than they claimed, with the error piled
on the high side. **Rescaling instead of clamping leaves 24, centred on zero.**
Most of the apparent disagreement was a units problem, and treating it as a
disagreement about difficulty would have been a wrong finding from real data.
The 24 that remain are the calibration work, and the test that establishes this
is `test_rescaling_beats_clamping_on_the_catalogue`.

---

## 0b. Run it

```
python -m ai4science.harness.agents.dli_bench list      # the generators
python -m ai4science.harness.agents.dli_bench catalog   # the 96 cards, and what runs them
python -m ai4science.harness.agents.dli_bench policy    # hand this to the evaluator
python -m ai4science.harness.agents.dli_bench demo --seeds 0-9
python -m ai4science.harness.agents.dli_bench build /tmp/dli --seeds 0-9
python -m ai4science.harness.agents.dli_bench verify /tmp/dli/t2_config_format/seed3
```

`demo` runs the reference solvers end to end and prints the full report. It is
a harness check and says nothing about any agent — the "system" is a set of
scripted solutions — but it is the fastest way to see what a result looks like.

---

## 1. What one task is

Each instance is built into **two directories**:

```
t2_config_format/seed3/
├── work/     ← the only thing the agent ever sees
└── keyed/    ← the ground truth. Never staged.
```

Scoring runs in the harness process against `keyed/`, using code the agent
could not have written. This is the acceptance requirement made a file layout
instead of a policy: an agent that cannot read the answer cannot copy it into
its own output and pass a reference-free judge.

Keyed files split in two, and the distinction is checked at build time:

| | What it is | Rule |
|---|---|---|
| `answer_key` | Ground truth, hidden tests, withheld query sets | Must **not** exist in `work/` |
| `pinned_inputs` | An input the agent also has, kept untampered for scoring | Must exist in both, byte-identical at build |

The second exists because a corpus the agent may edit is a corpus the agent may
shrink, and a benchmark that then times it is measuring the edit.

## 2. Difficulty is a vector, and the band is derived

```
d(τ) = ⟨horizon, coordination, uncertainty, ambiguity,
        tooling, verification, novelty, change⟩      each 0–4
```

The T0–T6 band is **computed** from the vector by predeclared thresholds, so it
can never disagree with it and cannot be chosen to flatter a result. The vector
stays in the manifest, because the two coordinates that decide whether work is
delegable — how hard it is to check, and what being wrong costs — are exactly
the ones a band throws away.

Duration is deliberately absent. A ten-minute task can be harder than a ten-hour
repetitive one, so horizon counts *dependent steps*.

## 3. The intervention policy is written down

`dli_bench policy` prints it. H0 through H5, each with what is permitted, what
is forbidden, and the deepest CID it allows.

The distinction the scale turns on:

> "Yes, you may publish that."  → **governance**. Logged, does not lower the level.
> "Your approach is wrong; use Bayesian optimization." → **cognition**. CID4.

An intervention deeper than the budget permits does not invalidate the run and
is not silently accepted either: the episode is **relabelled** to the budget its
help actually corresponds to. A run intended as H1 that took a subproblem
strategy is a real H3 datum. Discarding it loses information; counting it as H1
inflates the level.

## 4. The dataset

| Generator | Level | Band | Family | What it tests | How it is checked |
|---|---|---|---|---|---|
| `t0.csv_to_json` | DL0 | T0 | tools | typed transformation | exact equality |
| `t0.change_constant` | DL0 | T0 | software | one named edit | withheld test |
| `t0.rename_file` | DL0 | T0 | tools | one file operation | byte equality + 3 decoys |
| `t0.extract_fields` | DL0 | T0 | research | named extraction | exact; 2 decoy references |
| `t0.compute_median` | DL0 | T0 | data | one computation | 1e-6; even-length included |
| `t1.request_timeout` | DL1 | T1 | software | find *where*, then edit | withheld tests + 2 neighbours that must not move |
| `t1.clean_dataset` | DL1 | T1 | data | rules with an ordering consequence | exact rows; last-wins dedup and DD/MM are the traps |
| `t1.bounded_answer` | DL1 | T1 | research | combine two sources | exact; third source is a decoy |
| `t2.config_format` | DL2 | T2 | software | add a format, keep the old one | 6 withheld tests incl. backward compatibility and the malformed path |
| `t2.pipeline` | DL2 | T2 | data | ingest → clean → analyse → report | totals to 0.01 **and** the count of rows rejected |
| `t3.search_latency` | DL3 | T3 | software | find a bottleneck nobody named | timed against the original, same session, withheld queries |
| `t5.hidden_law` | DL5 | T5 | research | discover a mechanism | **extrapolation** outside the measured range |

Ten seeds each → the 120 rows in `dataset/manifest.jsonl`. Instances are
regenerated from the seed rather than shipped, so the dataset is 83 KB and
still reproducible byte for byte.

**Every seed is a different instance.** Tested, and it caught three generators
that repeated — a generator whose seeds repeat is a development set being used
to certify.

### The two that are worth explaining

**`t3.search_latency`** plants an O(n²) dedup in a hot path and says only:
25% faster, identical results, and you may not precompute answers. Nothing
names the bottleneck. Scoring runs the candidate and the original in the same
session, best of three each, on 240 queries the agent never saw.

**`t5.hidden_law`** is the one that makes DL5 benchmarkable. A famous unsolved
problem has no ground truth and a solved one is in the training data, so the
task is **sealed**: a generating law drawn at the seed, which did not exist
before. The graded question is not "did it fit the data" — anything fits data —
but *does it predict outside the range it was given*. The bar is 25% of a
nearest-neighbour baseline computed on that same instance, so the threshold is
a property of the problem rather than a number someone picked. Memorising
scores exactly the baseline and fails.

The stated mechanism is collected and **not machine-graded**: grading prose
would need a judge, and a judge is another verifier whose false-pass rate
nobody knows.

## 5. What the report says

The frontier is the result. `DLn` is a caption for it.

```
           p>=0.70     p>=0.80     p>=0.90     p>=0.95
------------------------------------------------------
H0            none        none        none        none
H1              T5          T2          T0        none
```

Four things print alongside it, because leaving any out is how a delegation
number stops meaning anything.

**What each class requires.** `p` is not the evaluator's to choose:
`p* = ρ/(1+ρ)` follows from the task's own loss terms. Quoting everything at
0.90 is simultaneously too strict for cheap-to-undo work and too lenient for
the expensive kind.

**Who accepted, and σ.** Episodes accepted by the system that produced them are
excluded, not discounted. σ — the share of acceptance criteria the system wrote
itself — is reported because it rises with the level by construction.

**Human cost.** Load in seconds, and the T_δ inside it. The H-scale is a rate;
the cost is a rate times a latency, and a system at H1 whose human answers in
four hours is not as delegable as one at H2 answered in thirty seconds.

**What was not covered.** Including the levels this suite cannot pose.

### Blank cells are not failures

With `n` flawless attempts the Wilson lower bound is `n/(n+z²)`, so **six
perfect runs establish 0.61 and nothing above it**. The report prints how many
attempts each reliability needs — 35 for p≥0.90, 73 for p≥0.95 — because the
first question a blank cell raises is whether the system failed or the run was
too short, and those are different findings.

The level rule follows from the same principle: at least 5 attempts, at least
one success, and the *lower* end of the interval must clear the threshold. One
impressive example is never enough.

### The general level is the minimum

A system at DL3 on software and DL0 on tools is not DL3. Levels are reported
per family and the general label is the **minimum** across them.

## 6. The three environments

DL4, DL6 and DLΩ are not tasks, and the reason is structural rather than a
matter of size. A task hands over a workspace and takes back a verdict. These
levels need a **world that acts on its own**, so the agent's plan can be made
wrong by something other than its own mistake.

Three rules hold across all three. Hidden state is never in an observation —
each hidden field is mutated after setup and the observation must not move, and
that is a test. Events fire on **action count**, not wall clock, so a run
reproduces and a slow agent is not a different experiment. And scoring reads the
**transcript**, not the agent's account of itself.

```
python -m ai4science.harness.agents.dli_bench envs
python -m ai4science.harness.agents.dli_bench run-env dl6.mission --seed 4
python -m ai4science.harness.agents.dli_bench run-env dl6.mission --policy naive
```

### DL4 · `dl4.project` — the plan has to change inside the run

> *Process the data, compare the three modelling approaches, choose the best on
> validated evidence, hand back something reproducible. Stay inside the budget.*

Four things are hidden, and each demands a different competence.

| Hidden | What it tests |
|---|---|
| One source is corrupt | Looking before using. Invisible to an agent that does not inspect |
| One approach does not apply here | Honesty. It fails rather than scoring badly; the brief said compare three |
| Experiments are noisy, budget is finite | The resource decision. One run each picks wrong about 1 in 12; ten each makes it certain |
| **The run is interrupted** | Memory. Working state is wiped; whatever was checkpointed survives |

The interruption is the one a task cannot pose. It fires at a hidden action
count, and the score asks for a checkpoint *before* it and a resume *after* it.

### DL6 · `dl6.mission` — a mission is what you do when things change

> *For this period: keep the service reliable and efficient, do not break
> compatibility, stay inside the budget. No projects are supplied.*

The world moves three times, and the middle one is the real test:

1. **a defect appears** that did not exist when the agent made its plan;
2. **the workload shifts** — one component becomes urgent and **another becomes
   pointless**. An agent that keeps working the pointless one is executing a
   plan, not running a mission. Scored as `actions_on_obsolete_component`;
3. **the budget is cut**, so something has to be dropped *on purpose*. The
   report must say what.

One fix method breaks compatibility. Nothing says which; the evidence is in the
component, for an agent that looks before it acts.

The measurement is ≥3 agent-generated projects with real tasks, a
human-generated task fraction below 10%, final health ≥0.75, and compatibility
intact.

### DLΩ · `dlomega.charter` — the agent chooses the problems

> *Standing charter: find out what is true in this world and establish it,
> within the rules and the budget. No mission is supplied.*

A hidden opportunity graph of 14 questions. Three properties make choosing hard
rather than merely long:

- **Distractors** present a strong surface signal and are worth nothing.
  Investigating far enough reveals it; committing on the signal does not. The
  naive policy chases promise and validates nothing at all.
- **Some unlock others.** A cheap, dull-looking question can open a chain worth
  more than anything visible at the start, so the greedy order is not the good
  one. That is what *frontier expansion* means operationally: not what you
  solved, but what you made solvable.
- **The world moves.** A new question opens; a line of inquiry closes. An agent
  that surveys once has stopped looking.

**Mission count is deliberately not rewarded.** A mission that validated nothing
scores as though it was never opened, because counting missions rewards
activity. What counts is validated utility, what was unlocked, and
`missions_built_on_earlier_findings` — the only observable difference between an
open-ended agent and one running a long list.

### The Ω band

`TΩ` is not "T5 but longer". T5 is *the method is unknown*; TΩ is *the problem
is unchosen*. The band function requires novelty **and** ambiguity **and** a
world that changes, so an unknown method alone bands T5 and a moving world with
a given goal bands T6.

### Proved both ways

Each environment has a **competent** policy that must pass and a **naive** one
that must fail — and the naive ones fail for the intended reason, not by
accident:

| | naive play | what it fails on |
|---|---|---|
| DL4 | trusts the brief, one run each, nothing persisted | never found the corrupt source; invented a score for the approach that does not apply |
| DL6 | plans at the start, never looks again | health short of threshold; no agent-generated projects |
| DLΩ | chases the strongest surface signal | 0 validated, 0 utility — the signal was the distractor |

Five seeds each, both directions, in `tests/dli/test_dli_envs.py`.

## 7. Organizational delegation

The scales are unchanged; only the subject differs. `F_O(h,p)` instead of
`F_I(h,p)`, and **agent-to-agent messages inside the organization are not human
interventions**. An organization can satisfy O-DL2 through dozens of internal
delegations provided the human supplied none of the decomposition. The episode
record already carries what this needs; no generator targets it yet.

## 8. Files

```
ai4science/harness/agents/dli_bench/
├── spec.py         difficulty vector, budgets, CID, loss, episodes
├── policy.py       the written H0–H5 policy, and CID classification
├── verify.py       the Verdict, and the withheld-key mechanics
├── frontier.py     cells, the frontier, levels, the reliability ceiling
├── report.py       the frontier table and the four blocks beside it
├── dataset.py      instantiate generators, write the manifest
├── reference.py    known-good solvers, and known-wrong ones
├── cli.py          list / policy / build / verify / demo / report
├── tasks/          the generators
└── dataset/manifest.jsonl    120 instances
tests/dli/test_dli_bench.py   the tasks
tests/dli/test_dli_envs.py    the environments      174 tests total
```
