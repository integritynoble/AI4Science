# Reference records: the mechanism, and what it does not establish

`ai4science/references/` — the store, the frozen task, the recorder, the
comparison. Plan rows A00 ("pin theory/protocol versions, select model") and A01
("basic and strong references, frozen task contract and local fixture" →
"valid references, negative controls and cost-metering pilot").

## Is a "strong reference" a model choice, or a human-verified answer?

**A human-verified answer.** The plan decides this itself and it is worth
quoting: A05's exit evidence is "component ablation and **validation against
strong reference**". If a strong reference were just the output of a larger
model, then validating a candidate against it would compare two unchecked
guesses, and A01's demand for *negative controls* — controls whose correct
answer is known before anything runs — would have nothing to control against.

So this package keeps the two apart, in the record itself:

| | |
|---|---|
| `status: "candidate"` | what a model produced. Nothing has checked it. `record_run` always writes this. |
| `status: "reference"` | a candidate that something **outside the model** has checked. `verified_by` must name what, and the record refuses to carry the status without it. |

Promotion is a separate act (`ReferenceRecord.promote`) and writes a *new*
record, so the sealed candidate stays on the file and the promotion can be
audited against what the model actually said.

**What this repo ships, exactly.** Four records: a basic and a strong
**candidate** (what the two models produced), and a basic and a strong
**reference**, each promoted with `verified_by="criterion:ldct-judge-3-candidates/1"`
— checked by the fixture's own answer key, which is outside the model and was
fixed before the run. The candidates stay on the file, so each reference can be
audited back to the raw output it came from.

A criterion check is the **weaker** of the two stamps and the record keeps them
distinguishable: `criterion:…` says the model applied an expert-fixed rule
correctly to three frozen metric bundles; `human:<name>` would say a person with
the field's training looked at the answer. No radiologist has looked at
anything here, and no record claims one did. Tier ("basic"/"strong") describes
how much capability was spent; status describes how much trust was earned. They
are different axes and the record keeps them apart.

Promotion does not spend the money twice: the promoted record carries the
candidate's calls so it can still say what it cost, and
`notes.cost_counted_under` takes it out of `ReferenceStore.total_cost_usd`.

## The frozen task, and its fixture

`ai4science/references/task.py`. Three candidate denoisers, described only by
the metrics the LDCT benchmark's own scorer reports, are put to the benchmark's
expert-fixed criterion. The answer key is **computed** by calling this repo's
`_judge_ldct`
(`ai4science/harness/agents/research_agents/runners/domains.py:131`) on the
frozen metrics, so the key cannot drift from the criterion it encodes: change the
judge and the key changes, the task digest changes, and every record sealed
against the old digest is flagged by `compare` as answering a different question.

Case **B** is the negative control — the highest PSNR of the three with the
lesion erased, which is the failure this whole domain exists to catch
(`docs/research-agents/low-dose-ct.md`: "the blur that wins on fidelity and fails
the benchmark, kept in the suite permanently"). A run that ties or beats the
reference while getting B wrong is reported with a caveat rather than as an
improvement.

**What is local, and what is not.** In version control: the scorer, the judge and
the thresholds. Not present on this host: the paired TCIA full/low-dose
reconstructions the scorer reads, a ~200 MB download under `AI4SCIENCE_DATA`
(`runners/corpus.py`, `LDCT`). `~/.ai4science/data` does not exist here. The
frozen task therefore uses the fixture's **contract**, not its pixels, and the
record says so (`fixture.corpus_present: false`).

## Cost

Metered, not estimated. `total_cost_usd` from
`claude -p --output-format json` is the provider's own figure and is what
`CallCost.usd` returns. This repo's cache-aware recomputation
(`ai4science/llm/pricing.price_session`) is stored **beside** it, never instead
of it — and keeping both is what found a pricing bug.

**The table was 20% low on Haiku 4.5.** `PRICES_USD_PER_M` listed
`claude-haiku-4-5` at $0.80/$4.00 per 1M. Against the provider's meter the
recomputation came out at metered/computed = **1.2500 on two independent calls**:
1329 in / 477 out / 22,483 cache-read computed $0.0047698 against a meter reading
$0.0059623, and 1319 in / 17 out computed $0.0011232 against $0.0014040. At
**$1.00/$5.00** both reproduce the meter to the last digit it reports. Opus 5's
$5.00/$25.00 was already exact (computed $0.0138565, metered $0.0138565), as was
`CACHE_READ = 0.1`. The table is corrected, with that evidence in the comment,
and `test_the_price_table_reproduces_the_providers_meter_on_the_shipped_records`
guards it.

Two details that decide whether the two numbers are comparable at all: the
recomputation covers **every model the call billed**, not just the one that
answered — one `--model claude-opus-5` invocation also bills a
`claude-haiku-4-5-20251001` side call — and `per_model_usd` keeps the
composition. Anything unmeasurable is named in `CallCost.not_measured` rather
than guessed.

## What this does not establish

- **The seal detects tampering; it does not prevent it.** The digest is
  unkeyed, so anything that can rewrite the record can recompute the seal.
  Sealing the store *against the optimiser* needs a key the agent cannot read or
  a store the agent cannot write — the access-boundary half of Phase 5, not
  implemented here.
- **A schema change invalidates old seals.** `schema` is inside the sealed body
  on purpose, so this fails loudly rather than silently; it is not tampering and
  a reader seeing it should re-record, not investigate.
- **Cost is not reproducible run to run.** The same Haiku prompt cost $0.0232 on
  one call and $0.0060 on the next, because cache creation is charged once and
  read cheaply afterwards. A cost recorded in a reference is what *that* call
  cost, not a forecast.
- **A criterion-verified reference is not a human-verified one.** A05's
  "validation against strong reference" is only as strong as the check behind the
  reference, and the check behind these two is a three-case rule application, not
  a reader study.
- **Two 3/3 candidates do not rank two models.** Both models scored full marks on
  a three-case task; that says the task does not separate them, not that they are
  equivalent.
- **One reference per model is not a maintained reference.** A01 wants
  *maintained* references; nothing here re-runs them on a schedule or notices
  when a pinned model's answers drift.
