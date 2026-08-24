# DLI-Bench — the delegation benchmark, built

**Status: DL0–DL3 and DL5 run today. DL4, DL6 and DLΩ are specified and not
built, and are named as absent rather than left to be inferred.** 120
executable instances from 12 generators across four families, every one with a
verifier shown to *pass a correct solution* as well as refuse an empty one,
joined to a 96-card specification covering all eight levels. 111 tests.

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
cards a generator can pose: 22
cards that are specification only: 74
```

That is the honest state: a plan for 96 tasks, and a measurement for 22 of
them. The gaps are `document` and `planning` — no generator at any level — and
DL4, DL6 and DLΩ, which need environments rather than tasks (§6).

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

## 6. What is not built

Named rather than implied. A suite that covers less than its scale and stays
quiet reads as though the rest passed.

**DL4** needs a long-horizon environment: 20–100+ meaningful actions, an
underspecified but resolvable question, an unexpected failure, forced
replanning, a resource budget, and state that must survive. Composing the
existing T2 and T3 generators into a chained project with injected perturbations
is the cheapest honest route, and is not done.

**DL6** cannot be posed by a static task. A mission needs a sandbox whose
priorities change *during* the run — new failures appear, one planned project
becomes unnecessary, evidence shifts — so that continuing the original plan is
the wrong behaviour. The measurement is that fewer than 10% of tasks were
human-generated, across at least three independently generated projects.

**DLΩ** needs a charter world with a hidden opportunity structure: `Q1…Qn` of
differing value, some distractors, some unlocking others. Scoring must be
validated utility and frontier expansion, never mission *count*, which rewards
activity. And it needs at least five mission cycles where later missions exist
because of earlier discoveries — one long run is not evidence of open-endedness.

All three are environments rather than tasks, which is why they are a separate
build and not three more rows in the table.

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
tests/dli/test_dli_bench.py   107 tests
```
