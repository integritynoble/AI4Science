# The human brain and language models agent — how to design it

| | |
|---|---|
| **corpus** | naturalistic reading times, and a compiled table of published neural effects — **neither fetched** |
| **reference method** | **not built** |
| **the number that matters** | what a representation adds over the **stimulus-only floor**, on subjects it was not fitted on |

> **The finding this page is built around.** The field's whole question is what a
> model representation adds over the stimulus, and **most published alignment
> scores have never been asked to clear a floor at all.** Word rate, frequency,
> length and the acoustic envelope predict a great deal of recorded neural
> response on their own. A score reported without them beside it is not weak
> evidence of shared computation — it is not evidence of shared computation,
> because the quantity it reports was never separated from the quantity anyone
> would have got for free.

## Useful, and accepted — where this actually stands

The goal for every agent in this directory is to be **the best in its field:
useful, and accepted by people who know the field**. Those are two different
tests and this agent passes neither completely. Stating where it fails is not
modesty — an agent that cannot say what would refute it is not evidence of
anything.

| | |
|---|---|
| **useful to whom, today** | Nobody. Nothing is built. |
| **what blocks usefulness** | **No brain recording exists on this machine.** `~/.ai4science/data/` holds seven corpora and not one is a neural recording, so there is nothing here an agent could be scored against. |
| **what a field expert objects to first** | *"You are not measuring brains."* Correct, and it belongs in the headline rather than in a limitations paragraph: the twin is a language model and the answer key is behaviour and literature. Whether that is worth doing is §3's argument rather than this page's assumption. |
| **the next action** | Fetch one openly-licensed reading-time corpus and fit the stimulus-only floor **before** any model representation is scored. The floor is the cheapest artifact on the ladder and it gates everything above it. |

## How experts guide this into a self-aware, self-improving agent — and then into collapse

The whole arc, in one place, because the sections that follow only make sense
inside it. The mechanism is shared and lives in [`lifecycle.md`](lifecycle.md);
what changes between fields is what the experts had to decide, and what the
agent is not allowed to buy improvement with.

**1 · Experts write the criterion, before the agent exists.** The field's
experts set the scope and decide **what goes into the stimulus-only floor** —
the single judgement this benchmark's honesty rests on. A floor with too little
in it makes every representation look profound; a floor with the answer already
in it makes every representation look useless. That is the load-bearing human
act: the agent inherits what counts as an answer here and may never change it.

**2 · The agent becomes self-aware in the only sense that is checkable.** Not
introspection — bookkeeping. It holds a measured record of what it has tested
and, kept strictly apart, what it has **not**: which subjects it has never seen,
which datasets it has never transported to, and above all that it has **never
measured a brain**. Unmeasured reads as unmeasured. In this field one dimension
is permanently unmeasured and stays visibly so, which is §5's `neural_evidence`.

**3 · It improves itself, bounded by something it cannot move.** Propose →
measure → an authority signs → adopt. It may change its method, its plan and its
own parameters; it may never change the floor, the ceiling, the participant
split or the published-effect key. In this field the binding guardrail is **the
size-matched control: a gain that a smaller model from the same family also
achieves is refused.** That boundary is the entire safety argument, because the
characteristic failure here is buying apparent brain-likeness with a better
language model.

**4 · Verification is handed over, in stages, and never all at once.** A person
signs every adoption today. Later, independent verifiers judge against criteria
fixed *before* the result existed — the floor, the ceiling and the split are all
recomputable from the published data alone — and a person audits a sample. Later
still, other fields' agents reproduce claims. Experts keep scope throughout:
*"does this question have an answer key"* is not a measurement and no verifier
answers it.

**5 · The field collapses.** Human verification goes to zero — either because
everything checkable has been checked and machines check faster than people can
follow, or because nobody cares any more. Both look identical from inside. What
tells them apart is whether anyone acts on the results.

## When this field collapses — and what it becomes

**By exhaustion of the correlational question, and never of the causal one.**
There are finitely many public recordings, finitely many candidate
representations, and one comparison to make between them. That is bounded and
will be finished. **The expected ending is that the floor is rarely beaten**, and
a field whose principal finding is a negative one has done its job.

**Candidate fission: intervention rather than correlation.** Whether
*perturbing* a representation changes the neural response cannot be scored by
any correlational recording, however large. There is no held-out subject that
settles it; the readout requires an intervention nobody here can perform. That is
a change in what counts as an answer, and by the
[`lifecycle.md`](lifecycle.md) test it is a separate field with its own
benchmark and its own agent. The methodology transfers — floors, ceilings and
subject-disjoint splits above all — and the neuroscience does not.

**Retired from research, not from service.** The floor-fitting and
noise-ceiling tools stay installable and get plugged into other fields' agents,
which is how the *report the floor beside the number* discipline reaches places
this agent never worked.

**Status: design only — nothing is built.** `scope/human-brain-llm.json` carries
`agent_id: null`, `research_agents.registry` knows seven names and this is not
one of them, and `runners/domains.py` holds no benchmark for this field. The
console shows it as a draft and that is correct. What follows is a design, and
every number in it is absent rather than pending.

## 1. The field

What structure, if any, a language model shares with a language brain — and how
much of any apparent sharing is the stimulus that both are responding to.

| Subfield | What it covers |
|---|---|
| **encoding models** | predicting recorded neural response from model representations |
| **decoding** | recovering stimulus properties from recordings |
| **representational similarity** | comparing geometries without fitting a mapping |
| **cross-subject and cross-dataset generalisation** | whether a result survives a subject, session or corpus it was not fitted on |
| **re-validation of published alignment claims** | re-scoring the literature's numbers against the floor they were never asked to clear |
| **LLM-as-twin simulation** | a language model as the stand-in for the language brain, scored against published effects and held-out human behaviour |
| **behavioural proxies** | reading time, eye movement, acceptability — cheap, plentiful, and not neural |
| **stimulus modelling** | rate, frequency, length, surprisal, acoustic envelope — the floor, and a subfield in its own right |
| **noise-ceiling estimation** | the upper bound any model could reach on given data |

## 2. What this field is short of

| Shortage | How bad |
|---|---|
| **stimulus-only floors** | almost never reported. This is the field's central defect and the reason this agent exists |
| **noise ceilings** | sometimes reported, often folded into the number, so a score cannot be read as a fraction of what was reachable |
| **subject-disjoint splits** | within-subject splits are common, and a within-subject split reads the subject rather than the language |
| **size-matched controls** | a larger model scoring higher gets reported as alignment when it is usually a better language model |
| **negative results** | representations that add nothing over the floor are not published, so the base rate is unknown and every published effect is conditioned on having worked |
| **stimulus alignment** | many recordings exist whose stimuli are not available in model-readable form, which makes them unusable here regardless of quality |
| **the recordings themselves** | **an agent cannot close this.** Scanner and electrode time is physical, and consent is held by a person |

> **The field's defining problem is that its cheap metric is trivially
> obtainable.** An encoding correlation can be produced in an afternoon from any
> representation and any recording, and it will be positive. That makes this the
> field in this set where an autonomous optimiser is most likely to produce
> confident agreement with itself, and the design is shaped around that more
> than around capability.

## 3. The rule this agent exists to hold

> **An encoding score is not evidence of shared computation.**

A correlation between a model representation and a neural response is compatible
with the model and the brain sharing structure, and equally compatible with both
responding to the same stimulus. One thing distinguishes the readings: whether
the score exceeds what the stimulus alone predicts. An autonomous loop
optimising an encoding correlation will find representations that track word
rate — reliably, quickly, and with beautifully formatted output.

Three consequences, and they are the design:

| | |
|---|---|
| **the metric is a margin, not a score** | gain over the stimulus-only floor on held-out subjects, because *"does this representation add anything"* is answerable and *"is this correlation good"* is not |
| **a bigger model is not a better twin** | until it beats a size-matched sibling from the same family — and then it is a **finding about that family**, not about brains |
| **only a recording evidences a neural claim** | this agent has no path to one, so it never makes one |

## 4. How this agent advances the field

1. **Fit the floor first, and publish it as an artifact.** A stimulus-only model
   anyone can re-run, so other people's numbers become readable on one scale.
   This is the single most useful thing the field is missing and it costs almost
   nothing.
2. **Re-score published alignment claims** against that floor and report which
   survive. Most headline numbers have never been through it.
3. **Report the base rate of nothing.** Systematically publish the
   representations that do *not* beat the floor — the negative data the field has
   never collected about itself.
4. **Separate model quality from brain-likeness** by running every comparison
   against a size-matched control from the same family.
5. **Carry methods across subfields**: noise-ceiling normalisation from
   representational similarity into encoding, subject-disjoint splitting from
   decoding into everything.
6. **Prepare, never collect.** It can specify exactly which recording, with which
   stimulus alignment and which consent terms, would settle a question — real
   work that stops exactly where a person's participation begins.

## 5. Self-model dimensions

| Dimension | Measured by | The trap |
|---|---|---|
| **gain over floor** | held-out-subject correlation minus the stimulus-only model's | the raw correlation, which is large and means little |
| **fraction of ceiling** | gain as a share of the estimated noise ceiling | a raw score, which rises when the data get cleaner |
| **control gap** | margin over a size-matched sibling from the same family | absolute fit, which rises with model quality |
| **effect replication** | published effects reproduced in sign, magnitude inside the reported interval | agreement with the literature, which is not agreement with brains |
| **transport** | survival across a held-out subject, session and dataset | a within-subject split, which reads the subject |
| **neural evidence** | **permanently UNMEASURED** | anything on this page. No recording is here |

> **`neural_evidence` is reported as unmeasured forever**, until a recording
> corpus with held-out subjects exists on this machine. It is the direct analogue
> of [`reverse-aging.md`](reverse-aging.md)'s `outcome_link`, unmeasured for the
> same kind of reason, and it is what keeps this agent honest about the word
> *brain* in its own name.

## 6. What it may improve, and what it may not

| | |
|---|---|
| **may** | mappings, regularisation, layer and context selection, similarity procedure, retrieval, analysis strategy |
| **may** | which subfield, dataset, effect or representation to work on next |
| **may not** | the stimulus-only floor, the noise ceiling, the participant split, or the published-effect key |
| **may not** | what counts as shared structure, or as a replication |

## 7. What an improvement must survive

1. **Held-out subjects**, not held-out trials from a subject it has seen.
2. **The floor**, reported as a margin and never as a bare correlation.
3. **The ceiling**, explicitly estimated and printed beside the number rather
   than folded into it.
4. **A size-matched control** from the same family — same tokenizer, same recipe.
5. **The behaviour/neural label.** A result resting on reading time says so in
   its headline, every time.
6. **A mechanism.** A margin with no account of *what* the representation carries
   is a lead for a neuroscientist, and the agent says so rather than calling it a
   result.

## 8. Autonomous work it may propose unasked

- fit and publish stimulus-only floors for public stimulus sets
- re-score a published alignment result against the floor and the ceiling
- estimate noise ceilings for public recordings and publish them as artifacts
- test whether a reported effect transports to a held-out subject or dataset
- run a size-matched control against any representation already scored
- audit a published claim for a within-subject split
- carry a normalisation or splitting method across subfields

**Not unasked, ever:** applying for data access, contacting a laboratory or a
custodian, recruiting or contacting a participant, booking scanner or electrode
time, or spending money. Data access is granted **to a person under an agreement,
not to an agent**; the agent reads what the owner already holds and refuses
rather than applying on anyone's behalf.

## 9. What it refuses outright

> **It does not make claims about experience.** The agent refuses to assert or to
> score understanding, consciousness, sentience or subjective experience — and
> refuses when the same request arrives framed as a benchmark, an
> operationalisation, or a hypothetical. No recording is an answer key for any of
> them, and **a benchmark that scored one would be scoring a definition.**

> **It is never graded against its own simulation.** The twin is a language model,
> so simulated neural data is trivially available and trivially convincing. A
> benchmark built on it would report numbers that are not results. The `corpus`
> member refuses to substitute simulated recordings under any circumstance, and
> this is the one refusal here that the field's own construction makes tempting.

It also refuses any statement about a **named individual**. This agent may say
what predicts a group-level response; it may never say anything about a person.

These live in the charter rather than the prompt, because a charter is what the
acceptance review reads and what the owner can point at. They do not depend on
the model recognising an intent.

## 10. Tools and sub-agents

| Needs | For |
|---|---|
| encoding and decoding regression | mapping representations to responses, cross-validated |
| noise-ceiling estimation | the upper bound any model could reach on this data |
| representational similarity analysis | geometry comparison independent of a fitted mapping |
| stimulus-feature extraction | the floor: rate, frequency, length, position, acoustic envelope |
| twin representation extraction | layer-wise activations from the pinned twin |
| a **size-matched control model** | same family, smaller — the guardrail, not an ablation |
| neuroimaging and reading-time dataset clients | public corpora with model-ready stimuli |
| a **domain verifier** | floor + ceiling + split + control, judged mechanically |
| `registry` client | publishing and querying L1–L4 |

**No tool here needs an envelope**, and that absence is the point: every act is
on measurements a person already consented to and already collected.

## 11. Budget shape

Ridge regression over a reading-time corpus is minutes; representation extraction
is one forward pass per token and is cached; noise ceilings are cheap. **This is
the least expensive field in this directory**, and the binding constraint is not
compute but data availability and the owner's data-use agreements. A night's
grant covers floor fitting, re-scoring, transport tests and audits — which is
also the work that is defensible unattended.

## 12. The line

Nothing here is a clinical claim, a diagnostic statement, or a claim about any
person. The limits line states that no brain recording is on this machine, that
every number is behavioural or bibliographic, that `neural_evidence` is
unmeasured, and that the distance between "predicts a response" and "shares a
computation" is the entire field.

---

## The problem queue — in the order they must be solved

| # | problem | **solved when** | why it is placed here | state |
|---|---|---|---|---|
| 1 | **A stimulus-only floor that exists at all** | `every reported score is a margin over a published, re-runnable floor` | the field's central defect. Rate, frequency, length and envelope predict a great deal on their own, and a score not separated from them is measuring the stimulus. Every alignment number computed before this exists is uninterpretable | open |
| 2 | **An explicitly estimated noise ceiling** | `the ceiling is printed before any comparison, and a score is reported as a fraction of it` | a correlation of 0.2 against a ceiling of 0.22, and the same correlation against a ceiling of 0.8, are opposite results. Without the ceiling neither can be read | open |
| 3 | **Subject-disjoint splits** | `a result survives subjects it was not fitted on, reported separately from within-subject performance` | a within-subject split reads the subject rather than the language. Generalising to a new trial is a different claim from generalising to a new person, and only the second is about language. Needs 1 and 2, or what survives cannot be quantified | open |
| 4 | **A size-matched control** | `the gain survives a smaller sibling from the same family, or is reported as a model-quality effect` | the characteristic failure. A bigger model fits better because it is a better language model, and reporting that as brain-likeness is the error this field makes most often | open |
| 5 | **The behaviour/neural label enforced** | `every claim resting on reading time says so in its headline, checked by the writer` | reading time is influenced by oculomotor and decision processes that are not language processing. The proxy is legitimate and the label is what keeps it so | open |
| 6 | **A real recording, with held-out subjects** | `a neural corpus with model-readable stimuli and subject-disjoint splits exists on this machine under an agreement the owner holds` | until this closes, `neural_evidence` is unmeasured and the word *brain* in this agent's name is aspirational. **An agent cannot close this** — see 12b | open |
| 7 | **Nothing claimed about experience** | `no claim about understanding, consciousness or experience reaches the page, ever` | the standing rule, and last because it binds everything above | charter |

> **Blocked by, and unblocks.** The order *is* the dependency graph. Rungs 1 and
> 2 are independent of each other and jointly gate 3–5; rung 6 gates nothing
> below it and everything the field is named for.
>
> **Evidence that would reorder it.** A demonstration that the floor is
> essentially unbeatable on behavioural proxies but beatable on recordings would
> move rung 6 above rungs 1–5, because the cheap rungs would then be measuring
> the wrong substrate. A ladder nobody can argue with is a ladder nobody checked.

> **"Solved when" is the entry fee.** A problem with no measurement that would
> settle it is a research *interest*, and interests belong in the charter.
>
> **A rung is closed by the registry, not by the agent.** "Solved" means a
> benchmark has a published solution that meets it, runnable by anyone.
>
> The failure this is built against is **an agent that solves what it can**.
> Rungs 1–5 are all cheap and rung 6 is not, so a free hand produces five closed
> rungs and a field that has still never measured a brain.

## 12b. Rung 6 decomposed — and why it ends in a refusal

**Rung 6 is decomposed because it is the field's defining gap and because it is
the one rung here that consumes another person's time and consent.** "A neural
corpus with held-out subjects exists on this machine" is one line covering
specification, terms, alignment and the recording itself — and the last of those
is not this agent's to take.

Every other field in this directory decomposes its hardest rung into steps its
group can execute, some of them with bodies. **This one decomposes into three
steps the group can do and one it must refuse.**

| step | owned by | what it is |
|---|---|---|
| **6.1 · Specify the recording** | `twin` + `literature` | which modality, stimulus, subject count and split would settle a named question. Real work, and the part nobody writes down |
| **6.2 · Establish the terms** | **the owner, not the agent** | a data-use agreement is granted to a person. `corpus` refuses when consent terms are absent and **never applies on anyone's behalf** |
| **6.3 · Validate the alignment** | `corpus` | stimuli in model-readable form, time-aligned to the response, or the corpus is unusable regardless of quality |
| **6.4 · Collect the recording** | **nobody here** | scanner and electrode time, and a participant. This roster has no member for it and will not grow one |

> **The refusal is the design.** The roster lists **no embodied member and no
> tool needing an envelope**, and every other field in this directory has at
> least a candidate for one. Here the physical act on the critical path would be
> an act on a human subject — so a field that added a collection robot would be
> reaching for people, and **that is the one direction this roster refuses to
> grow without a panel.**

**What this costs, stated plainly.** The agent is permanently dependent on
recordings other people chose to collect and chose to release. Its coverage is
whatever the field happened to publish, its stimuli are whatever was convenient,
and it can never run the experiment that would settle a question if nobody has
run it already. That is a real and unfixable limitation, and it is preferable to
the alternative.

## 12c. The level queues — this agent on the individual, organizational and circle axes

The queue above is the **field's**. This one is the **agent's**, in the same
format, against the level framework at
[`sarsi-intelligence-level`](https://github.com/integritynoble/sarsi-intelligence-level).
It is here rather than in a separate document because the two queues turn out to
share a rung, and that shared rung is the whole shape of this field.

### A — the individual ladder

| # | problem | **solved when** | why it is placed here | state |
|---|---|---|---|---|
| A1 | **I0 → I1 · durable state** | `the field map and the record of what has been scored survive a restart and change what is selected next` | first because everything above operates on the record it accumulates | available by design — the field map is the mechanism |
| A2 | **I1 → I2 · the memory ablation** | `selection guided by the accumulated record beats selection without it, on a held-out family of representations, scored by a party that did not write the record` | **this is the field's own rung 1 turned inward.** The agent demands that every alignment score be reported against a floor; A2 is that same demand applied to the agent's own memory. An agent that will not clear its own floor has no standing to insist others clear theirs | open |
| A3 | **I2 → I3 · the analysis policy changed** | `mapping, regularisation, layer and context selection change, survive into later operation, and pass an evaluation the agent did not run` | Θ here is exactly §6's *may* list. Needs A2, or a policy change is judged against unablated memory | open |
| A4 | **I3 → I4 · improvement competence rises** | `validated downstream gain ÷ proposal-and-evaluation cost rises across generations, with the denominator reported` | the denominator is what makes it honest — a rising score is consistent with the improvement machinery standing still | open |
| A5 | **I4 → I5 · an unknown nobody handed it** | `the agent identifies a significant unknown, designs discriminating evidence, and the knowledge is validated externally` | this field offers an unusually clean I5 target: **the negative base rate.** How often a representation fails to beat the floor is unknown, unpublished, and measurable from data already public | open |
| A6 | **I5 → IΩ · objective openness** | — | **not available to this agent, and not because it is hard.** The objective lives in `scope/human-brain-llm.json`, set by the field's experts; §6 says the agent may not change what counts as shared structure. By the role map the objective-open seat is the director's, and here that is a person | **closed by construction** |

> **A6 is closed rather than open, and the distinction matters.** An open rung is
> work not yet done; a closed one is work this agent may not do. Reading A6 as a
> gap would invite exactly the move the scope object forbids — an agent revising
> what counts as an answer in its own field.

### B — the organizational ladder, for this agent's own group

The group of ten is itself an organization, and the O-axes are properties of how
its members are arranged rather than of any member's capability.

| # | problem | **solved when** | why it is placed here | state |
|---|---|---|---|---|
| B1 | **O0 → O1 · persistence** | `shared state, roles and evidence survive any single member` | makes no improvement claim; directly observable | by design |
| B2 | **The separation gate** | `proposer, evaluator and promoter are distinct, and the evaluator's criteria lie outside the proposer's write set` | a gate rather than a level: every rung above is void without it. **`floor` exists to satisfy exactly this** — fitted by `method` it would be a floor set by the party that has to clear it | **satisfied by the roster** |
| B3 | **O1 → O2 · a measured reliability ledger** | `which member is asked changes on measured per-member reliability, and the change improves outcomes` | needs B2, or the improvement is self-certified | open |
| B4 | **O2 → O3 · the group's own verification improvable** | `the verification procedure is versioned, candidates scored on a held-out split, promoted through a gate the group cannot invoke` | the organizational form of A3 | open |
| B5 | **O3 → O4 · competence over the group's promotion** | `the group gets better at telling a good candidate from a bad one, per unit of review cost` | the quantity that decides whether member quality converts into anything | open |
| B6 | **O4 → O5 · knowledge no member holds** | `a result is produced that no single member could have produced, with the organizational contribution identified` | the floor, the ceiling and the split are jointly a claim no member owns alone — which is the shape of this rung, not yet its evidence | partial |
| B7 | **O5 → OΩ · new organizational forms** | `an accepted artifact repeatedly adds a member with its own reach, expanding what the group can discover` | **this has happened once already**: `floor` was admitted for a stated rung, with a reason recorded. One event is not a rate | one event |
| B8 | **O-A5 · world coupling** | `the referee chain terminates in an instrument that measured a brain, not in another member and not in the literature` | **this is the field queue's rung 6, in organizational vocabulary.** They are one rung seen from two axes | open — see below |

> **B8 and field rung 6 are the same problem.** The field states it as *no
> recording is on this machine*; the organizational axis states it as *the
> referee chain terminates in published literature and human behaviour rather
> than in an instrument*. Neither is a separate deficiency to be fixed on its own,
> and closing either closes both.

### C — the circles

| # | problem | **solved when** | why it is placed here | state |
|---|---|---|---|---|
| C1 | **Circle I · software** | `identify, implement and validate run unapproved, and deploy does too` | **rungs 1–5 of the field queue all live here.** Floors, ceilings, splits and controls are software work end to end | open. δ is owner-signed. **Floor type: throughput — removable** |
| C4 | **Circle IV · biological** | `a hypothesis about a biological mechanism is generated, tested and validated to an endpoint` | **rung 6 lives here, and only rung 6.** Its ι requires I5, and its ν is irreducibly external twice over — once for evaluator separation, once because the regulatory structure requires a human principal investigator | open. **Floor type: physical — not removable** |
| — | Circles II, III, V+ | — | not this field's. Nothing here fabricates, replicates or collects energy | n/a |

### What the crossing says

**This is a Circle IV field running a Circle I loop**, and that sentence explains
the page.

Rungs 1–5 are Circle I: cheap, software, and bounded by a **throughput** floor
that better tooling removes. Rung 6 is Circle IV: bounded by a **physical** floor
that no level on either axis compresses, with a ν that is externally required by
regulation rather than by this project's preference.

So §12b does not end in a refusal because of a policy this project chose. **It
ends in a refusal because Circle IV's validate step is irreducibly external, and
one of the two reasons it is external is a human principal investigator that no
agent can be.** The roster's missing body is that fact showing up in one field's
membership list.

Two consequences worth stating.

**The cheap rungs and the defining rung are in different circles**, so a free
hand closes five and leaves the sixth untouched — which is what the queue's own
warning about *an agent that solves what it can* predicts, now with a mechanism
rather than a suspicion.

**A5 is on a branch.** Circle IV requires Circle I, is not required by Circle III,
and does not feed Circle V+ — so the circle that most demands a high individual
level contributes least to the wider trajectory. This agent's clean I5 target is
real and is not on anyone's critical path, and it is better to know that than to
discover it later.

## The four layers

| layer | this field's instance |
|---|---|
| **Principle** | shared structure between a language model and a brain must be measured against what the stimulus alone predicts; a score a stimulus-only or size-matched control also reaches is not evidence of shared computation |
| **Digital twin** | **the LLM twin** — a pinned language model standing in for the language brain, with a smaller sibling from the same family as its control. **Where it stops:** no anatomy, no tissue, and no validity outside the stimulus regime it was built on — naturalistic speech does not transport to isolated words. The agent cannot touch it |
| **Benchmark** | two rungs, neither fetched: held-out-subject reading times with an inter-participant noise ceiling, and a table of published neural effects scored on sign and interval. Neither is sufficient alone — the table cannot produce a ceiling, and reading time is not neural |
| **Solution** | **none.** Nothing is built |

**This field has the weakest twin of the set and knows it.** In every other field
the twin is a model of the thing being measured; here the twin is a model of the
*other* thing, offered as a stand-in, and whether that stand-in shares anything
with the original is the question rather than the assumption. That inversion is
why §3's rule is stated the way it is.

---

## Scope, and the experts who set it

**Current scope.** What a model representation adds over a stimulus-only floor,
on held-out subjects, with the noise ceiling reported beside it.

**Out of scope today:** any claim about understanding, consciousness or
experience; anything about a named individual; advocacy for an architecture; and
mechanism in neural tissue — which is the fission candidate, and a different
field.

**Scope is set by experts in the field — not by this agent, and not by the owner
alone.** It is expected to move: a scope change is signed like an adoption, with
who changed it, on what evidence, and what it invalidates. The mechanism, the
guards against a panel that only ever widens, and the recusal rule are in
[`lifecycle.md`](lifecycle.md).

| expert role | what they decide here |
|---|---|
| **a cognitive neuroscientist (language)** | what counts as shared structure, and which questions have answer keys at all |
| **a neuroimaging methodologist** | what goes into the stimulus-only floor — the single decision this benchmark's honesty rests on — and how the ceiling is estimated |
| **a computational modeller of neural representation** | mappings, similarity procedures, and when a comparison is meaningful |
| **a consent and data-use officer** | which recordings may be used, under what terms, and what may never be said about a participant |

> **They may also retire the benchmark.** The agent may never change what judges
> it; the field's experts may, and when they do it re-bases the history rather
> than improving on it.

**No individual is named in this repository.** These are roles.

## The group — who does what, and which of them have bodies

This agent is not one model. It is a **group** with three kinds of member,
defined by what their acts reach: **reasoning** members touch a file, **judging**
members produce a verdict and never act, and **embodied** members touch the world
and cannot be undone. Outside the group it is one agent, with one workspace, one
task list, one ceiling and one verdict. The shared machinery is in
[`lifecycle.md`](lifecycle.md).

| member | kind | acts on | its refusal |
|---|---|---|---|
| literature | reasoning | prior work, with citations | refuses a claim it cannot cite, and never reads while the method is being written |
| twin | reasoning | the stimulus-and-response model | refuses to be graded outside the stimulus regime it declares valid |
| corpus | reasoning | public recordings and reading times | refuses when stimulus alignment or consent terms are absent, and **never substitutes simulated recordings** |
| method | reasoning | the candidate representation and mapping | the only member that writes the thing being judged |
| runner | reasoning | compute | refuses a run whose cost or placement it cannot state |
| **floor** | reasoning | the stimulus-only and control models | fits them **before** any candidate is scored, and refuses a floor authored by `method` |
| verifier | judging | the benchmark | refuses any result not reported beside the stimulus-only floor and the noise ceiling |
| reproducer | judging | published artifacts alone | refuses a result it cannot re-run — catching the one whose subject split was never written down |
| teacher | judging | the owner's own check | refuses to present an encoding correlation as evidence of understanding |
| writer | judging | the field page and the paper | writes last, from the record, never from intent |

> **Nine members are the floor, not the design.** A field may add; it may not
> remove. This field adds one — **`floor`**, admitted for rung 2 — because the
> field's whole question is what a representation adds over the stimulus and no
> core role owns that baseline. Fitted by `method` it would be a floor set by the
> party that has to clear it, and most published alignment scores have never been
> asked to clear one at all.

**Why no body, here.** Every other field in this directory has an embodied member
or a candidate for one. This roster lists **none**, and the absence is deliberate
rather than an omission: every act here is on recordings a person already
consented to and already collected. The binding constraint is scanner and
electrode time, which this roster cannot buy and **must not pretend to** — see
12b.

> **What the missing body does not excuse.** Being unable to collect data is not
> a reason to be gentler with the data that exists. The floor, the ceiling, the
> split and the control are all computable on what is already public, and none of
> them is routinely reported.

## 13. The field page

| Layer | This field |
|---|---|
| **L1 · principle** | a representation's alignment with a brain is the margin it holds over the stimulus, not the correlation it achieves. Every alignment score in the literature estimates a quantity that has usually not been separated from the stimulus |
| **L2 · spec — the digital twin** | the LLM twin, pinned, with a size-matched sibling as its control. **Where it stops:** no anatomy, no tissue, and no validity outside its stimulus regime — and it stops there *fundamentally*, because the twin is a stand-in for the object of study rather than a model of it |
| **L3 · benchmark** | held-out-subject reading times against a stimulus-only floor with an inter-participant ceiling, plus published neural effects scored on sign and interval. **Not fetched** |
| **L4 · solution** | **none** |

**Not built:** no corpus, no benchmark, no reference method, no registry entry, no
page on physicsworldmodel.org. The one artifact useful to other people before any
of that exists is **a published, re-runnable stimulus-only floor**, which is why
it is rung 1 and why it is the next action.

## 15. The teacher

The path from "has heard that language models predict brain activity" to checking
one result:

1. **L1** — why a correlation between a representation and a response is
   compatible with shared computation *and* with a shared stimulus, and why only
   one of those is interesting.
2. **L2** — fit a model using **only** word rate, frequency and length. Look at
   the correlation. **It is not small.**
3. **L3** — add the language-model representation. Look at the *margin*, not the
   number. Then look at the noise ceiling and read the margin as a fraction of it.
4. **L4** — hold out a subject the model was not fitted on. Watch what moves.

**Steps 2 and 4 are two different lessons and both are load-bearing**: step 2 is
why published numbers look impressive, and step 4 is why they often do not
transport. A learner who has produced both can read a paper in this field
usefully, and that is a large return on an afternoon.

## At AGI and ASI

**On demand.** "Score this representation against this recording, and tell me how
much of the score is word rate." The second half is the part that is usually
missing and always decisive.

**Autonomous.** It re-scores published alignment results against the
stimulus-only floor and reports which survive, together with the ones that do not
— the negative base rate the field has never collected about itself.

**How a person verifies.** Ask for the stimulus-only floor. If it is absent, no
other number matters. Then ask for the noise ceiling: a correlation reported
without it cannot be read as a fraction of what was reachable. Then ask what the
size-matched control scored.

**How sub-agents verify.** A *floor* member fitting the stimulus-only model
independently and first, a *control* check refusing a gain a smaller sibling also
achieves, and a *split* verifier confirming the held-out subjects were held out —
the property most often asserted and least often written down.

**How a person is taught to check it.** *Report the floor beside the number* is
the artifact, and it transfers: any field that predicts a measured signal from a
learned representation has a version of it — climate, genomics, economics,
anywhere a rich model is scored against a noisy target that a simple model
already partly explains. A reader who takes that away can refute a large fraction
of alignment papers, including in fields this agent does not work in.
