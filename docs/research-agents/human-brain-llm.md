# human brain and language models

**Status: design only — nothing is built.** `scope/human-brain-llm.json` carries
`agent_id: null`. `research_agents.registry` knows seven names and this is not
one of them. The console shows this field as a draft, and that is correct.

## The principle, stated so it can be wrong

> Shared structure between a language model and a brain must be measured
> against what the **stimulus alone** predicts. An encoding score that a
> stimulus-only or size-matched control also reaches is not evidence of shared
> computation.

It can be wrong in the useful direction: if a representation reliably beats the
stimulus-only floor on held-out subjects, across datasets, that is a real
finding. The expected answer, most of the time, is that it does not — and this
field exists to be able to say so.

## Why there is no agent yet

The same reason longevity has none: **the answer key is absent.**

An agent here would need a corpus of human brain recordings time-aligned to
language stimuli, with held-out subjects. `~/.ai4science/data/` currently holds
`cave-hyperspectral`, `dude`, `kvasir-capsule`, `ldct`, `methylation-age`,
`open-kbp` and `tcga-survival`. None of them is a brain recording. There is
nothing on this machine an agent could be scored against.

Declaring the agent anyway would produce a member of the roster that proposes
claims no judge can grade. That is the one failure this programme is built to
prevent: a candidate that improves its score because nothing can contradict it.

## What promotion requires

Three things, in order, and none of them is code:

1. **A corpus on disk** — public naturalistic-stimulus recordings (fMRI, MEG or
   ECoG) with the stimuli in a model-readable form, obtained under a data-use
   agreement the owner holds. The `corpus` sub-agent must refuse when stimulus
   alignment or consent terms are missing.
2. **A held-out benchmark with a judge the proposing role does not own** — a
   `DomainBenchmark` in `runners/domains.py` with subject-disjoint splits, a
   stimulus-only floor fitted by the `floor` role, and an explicitly estimated
   noise ceiling. The answer key must never be staged into the sandbox, exactly
   as the other six benchmarks arrange.
3. **Then, and only then**, a `registry.py` builder and `agent_id` set in the
   scope object.

Step 2 is where this field is easiest to get wrong. An encoding correlation is
trivially obtainable and means very little on its own; a benchmark that reports
one without the floor and the ceiling beside it would manufacture agreement
rather than measure it.

## What the field may not say

The scope object forbids four things, and the first is the one that makes this
field hard to run honestly: **no claim about understanding, consciousness or
experience.** No recording is an answer key for those. A benchmark that scored
them would be scoring a definition.

The others: nothing about a named individual; no score reported without its
floor and ceiling; and no brain-likeness claim resting on a correlation a larger
model also achieves.

## The boundary that would move

If the question becomes causal — whether perturbing a representation changes
the neural response — no correlational recording can score it. That is a
different twin and a different answer key, so the response is **fission into a
new field**, not a widening of this one.

## Roster note

`roster/human-brain-llm.json` adds one non-core member, `floor`, admitted for
rung 2, because the field's whole question is what a representation adds over
the stimulus and no core role owns that baseline. Fitted by `method` it would be
a floor set by the party that has to clear it.

The roster lists **no embodied member and no tool needing an envelope**, and
that absence is deliberate: every act here is on recordings a person already
consented to and already collected. The binding constraint is scanner and
electrode time, which this roster cannot buy and must not pretend to.
