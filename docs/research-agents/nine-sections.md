# The nine sections of a field research agent

A field research agent is published as one page. The page draws on nine
sections, so that an agent in one field can be read by someone from another.
This file gives each section in full: where it came from, what it holds, the
rules it obeys, how it changes as the agent climbs the stages of
[`lifecycle.md`](lifecycle.md), and a filled example from the computational
imaging agent.

The nine are the original design of the AI4Science spec of 15 August 2026
(§6, the three focuses, and §7.4, the nine sections). Later rulings changed how
they are shown, not what they are; the history is at the end.

| # | Section | In one line |
|---|---|---|
| 01 | Problems | the field's problems, one by one, until it collapses |
| 02 | Tools, solutions, sub-agents | what a user comes to the agent to get |
| 03 | Self-awareness and self-improvement | what the agent knows about its own standing, and how it improves within its charter |
| 04 | Subfields | the agent's scope |
| 05 | Self-model | measured, not claimed: its stage, its profile by contract, the four numbers; the unmeasured listed apart |
| 06 | Principles | the physics the field reduces to, where a claim reaches beyond the data |
| 07 | Digital twin | the forward model, and how far it is trusted |
| 08 | Benchmarks | **required**: each frozen contract, its floor, and who verifies it |
| 09 | Solutions | methods that clear a contract, each bound to the contract version |

---

## The rules for all nine

1. **A pool, not a form.** An agent shows the sections it has, and never an
   empty one. An agent that has all nine shows all nine.
2. **Section 08 is the only one every agent must have.** An agent without a
   frozen benchmark has nothing that judges it, so it has no page.
3. **Sections 06 to 09 are the four artifacts of the procedure** (principle,
   twin, benchmark, solution). A principle or a twin whose trigger did not fire
   is correctly absent: its absence is a finding, not a gap.
4. **Section 05 is the one to read first.** It says how far the rest may be
   trusted.
5. **Each section has its own page.** The agent's page lists the sections it
   has and links to them; the filled pages live at
   `docs/agents/<agent>/1-problems.md` … `9-solutions.md` in the Singularity
   repository.
6. **Sections 01 to 03 are the agent's three focuses** (spec §6): solve the
   field's problems one by one until it collapses; give the field its best
   tools, solutions and sub-agents, for the user; be self-aware and recursively
   self-improving. Sections 04 to 09 describe the field and the agent's
   standing in it.

---

## 01 · Problems

**Original words (spec §6 and §7.4):** "the field's problems, one by one, until
it collapses", which the agent solves "itself automatically", one problem at a
time.

**What it holds.** An ordered queue of the field's problems. Each problem
carries a measurable **`solved when`**: the measurement that would settle it.
A rung without one is a research interest, not a problem.

**Rules.**
- The order is the agent's plan of work; it works the queue itself, as
  autonomous work, distinct from section 02, which is provision for a user.
- Each problem is posed so that an answer can be exhibited (steps S0 and S1 of
  the procedure): who would accept an answer, and what object they would
  accept.
- Problems an agent cannot close by itself (for example studies that need
  human readers) are named and left to people, not dropped.
- The field collapses when its queue empties. An agent that reports a queue
  close to empty has stopped reading its field.

**Example (computational imaging).** 1. Evaluation lives inside the method's
own assumption, `solved when` a standing protocol reports every result under a
perturbed operator. 2. The mask convention is unstated (continuous versus
binary masks move CASSI results by about 7 dB), `solved when` every reproduced
result carries its convention. 3. PSNR is the reported metric, `solved when` a
task metric appears beside fidelity on every result. 4. Hallucination under
generative priors is unmeasured. 5. Reproduction is rare.

---

## 02 · Tools, solutions and sub-agents

**Original words:** "the field's best tools, solutions and sub-agents, this is
for the user usage".

**What it holds.** What a user can run: the field's tools, the ready solutions,
and the agent's sub-agents.

**Rules.**
- This section is for the user; section 01 is the agent's own work. Keeping
  them apart is part of the design.
- A research agent is a **group** agent. From outside it is one agent on the
  roster, a field and never a person; from inside it has members, and those
  members are its sub-agents (spec §6, A6; [`lifecycle.md`](lifecycle.md),
  "The agent is a group").
- A tool is listed with what it gives the user, and the version that was
  checked.

**Example (computational imaging).** Forward-operator library (calibrated
operators with provenance); reconstruction runners (the compared methods under
one protocol); task-metric harness; perturbation harness (operator error
injected on purpose); hallucination detector (structure absent from the
measurement).

---

## 03 · Self-awareness and self-improvement

**Original words:** "be self-aware, and recursively self-improving".

**What it holds.** Two things.

*Self-awareness:* what the agent knows about its own standing, in five parts
(see [`lifecycle.md`](lifecycle.md), "Self-awareness, functionally"):

| part | what the agent knows |
|---|---|
| charter | the field it may work in, and what it may never touch |
| self-model | what it has measured about itself, on which dimensions, and how well (shown in section 05) |
| field map | what it has **not** measured, and what would settle each gap |
| budget | what it has spent and what remains |
| ledgers | who asked for each piece of work |

*Self-improvement:* its open weak spots, taken from real failures, and the
record of repairs (step S7).

**Rules.**
- Self-awareness here is narrow and checkable: bookkeeping about evidence,
  held to a standard the agent cannot relax because the standard lives outside
  it. It is not introspection about experience.
- **May improve:** its own methods, retrieval, reproduction efficiency, field
  map, and procedures it has repeated often enough to consolidate.
- **May never touch:** the evaluation protocol, the held-out sets, the
  verifier, and its own verdict. A restraint keyed on a value the restrained
  party controls restrains nothing.
- An improvement counts only when the hidden score goes up, nothing regresses,
  and it is reproduced.
- Self-awareness is functional, not introspective: see
  [`lifecycle.md`](lifecycle.md), "Self-awareness, functionally" and
  "Recursive self-improvement, and its hard boundary".

**Example (computational imaging).** The held-out operator set and the
evaluation protocol are outside its write set; a sign error in its own
reference solver, found by its benchmark, is in its repair record.

---

## 04 · Subfields

**Original words:** "subfield", with `drug-design.md` named as the reference
structure.

**What it holds.** The field decomposed, with what is at stake in each part:
the parts the agent covers and the parts it does not.

**Rules.**
- The decomposition is the agent's scope. A claim outside it is outside the
  charter, and the agent declines rather than attempts.
- Scope is set with the field's experts ([`lifecycle.md`](lifecycle.md),
  "Scope, and the experts who set it").
- When a question appears that the agent's contract cannot score without being
  changed, a new subfield splits off as a new agent with its own contract: the
  fission of stage 4.

**Example (computational imaging), 10 subfields.** Snapshot spectral (CASSI);
compressive sensing; phase retrieval; coded aperture and lensless; plug-and-play
and unrolling; diffusion priors; implicit neural representations;
self-supervised recovery; forward-operator calibration; task-based evaluation.

---

## 05 · Self-model

**Original words:** "self-model dimensions", with `drug-design.md` named as the
reference structure.

**What it holds.** Measured, not claimed: the dimensions of its own state the
agent must represent to act honestly, its **stage** on each contract it holds,
its overall stage, and the four numbers: the verifier's false-accept rate, the
share of invalid results among those accepted, the valid yield, and the cost.
What is not yet measured is listed apart, each line with the measurement that
would settle it. Section 05 is the measured record inside the agent's
self-awareness (section 03).

**Rules.**
- Each dimension exists because a specific claim becomes dishonest without it.
- The stage is stated per contract (the agent's work under one frozen contract);
  the agent's overall stage is the lowest among its core contracts.
- The self-model is written by observation, never by assertion: its lines come
  from verdicts, benchmark results and refusals, recorded by the part of the
  system that judges, not by the agent.
- Numbers that have not been measured are written as `unknown`, never
  estimated, and kept apart from the measured ones. "Unmeasured" must stay
  expensive to write: each such line names what would settle it.

**Example (computational imaging).** Operator confidence (how well the forward
model is known, and by what calibration); prior strength (how much of the
output came from the measurement and how much from the prior); convention state
(mask type, normalisation, split); reproduction status per method; transfer
boundary (which subfields a method has been shown in); claim status, from
UNREPLICATED to SETTLED.

---

## 06 · Principles

**Original words:** "principles".

**What it holds.** The physics the field reduces to, and the rule that follows
from it. Present only where a claim reaches beyond the scored data (steps S4 and
S5); then the principle is checked against the universal conditions (units,
causality, conservation, thermodynamics, quantum consistency, well-posedness,
falsifiability) before it can carry a claim.

**Rules.** The principle is not a description of the field; it is what every
claim must reduce to. A claim that stays inside the scored data needs no
principle, and the section is then correctly absent.

**Example (computational imaging).** "A known forward operator plus a learned
prior; a measurement is invertible because the operator is known." The
operator is known only to the accuracy it was calibrated.

---

## 07 · Digital twin

**Original words:** "digital twin".

**What it holds.** The forward model: what can be simulated, how far it is
trusted (its honesty tier), and where it stops being trusted. Present only where
scoring needs a model.

**Rules.** A result produced inside the twin and evaluated inside the same twin
has been graded on its own assumption. The twin generates hypotheses; its
output is evidence about the twin until something outside it agrees. Where the
twin is the only evaluation available, that is reported with the result.

**Example (computational imaging).** The forward operator `y = Ax + n` is the
twin, and it already exists, which is unusual. It is trusted only to its
calibration, so every result also reports performance under a perturbed
operator.

---

## 08 · Benchmarks (required)

**Original words:** "benchmarks".

**What it holds.** Each **frozen contract**: its data, split and leakage unit,
metric formula, floor (the strongest trivial explanation), threshold fixed
before any score, refutation condition, its hash and version, and **who
verifies it**.

**Rules.**
- Required: an agent without one has nothing that judges it (steps S2 and S3).
- A benchmark is a test condition, not a verdict. No result is reportable
  without the verifier's identity, its false-pass rate or an explicit
  `unknown`, and the floor it was compared against.
- A changed contract is a new version with a new hash; an agent keeps holding
  the old version until it signs the new one.
- Who verifies each contract is what sets the agent's stage on it (section 05):
  the author at stage 1, an independent verifier at stage 2, a verifier with a
  measured false-accept rate at stage 3.

**Example (computational imaging).** Simulated-measurement suites and CASSI
data sets, which share the forward model with the methods, so a method's
assumption is also its exam; the agent therefore records the mask convention,
the split, the floor and the accepting party with every result.

---

## 09 · Solutions

**Original words:** "solutions".

**What it holds.** The methods that clear a contract, versioned, each bound to
the contract version it was scored under (step S6), and each with the condition
under which it was shown to work.

**Rules.** A solution reported without its condition is a claim about a
benchmark, not about the field. A row is not a settled claim unless its
replication status says so.

**Example (computational imaging).** Plug-and-play and unrolled solvers (strong
and general; convergence guarantees weaken as the denoiser strengthens);
diffusion priors (best quality; hallucination risk unmeasured); implicit neural
representations (sparse and irregular sampling); self-supervised denoising (when
no ground truth exists).

---

## The sections and the stages

The nine sections say what an agent **has**; the stage says how far it can be
**trusted**. The stage is not a tenth section: it is written in section 05, for
each contract listed in section 08.

| Stage ([`lifecycle.md`](lifecycle.md)) | The agent's page |
|---|---|
| 0 · assisted | No page yet: without a frozen contract (section 08) nothing judges the agent |
| 1 · proposing | The first page: 08 with contracts verified by their author, and 05 at stage 1; usually 01, 02, 04 and 09; 06 and 07 only where their triggers fired. An agent can have all nine sections at stage 1 |
| 2 · delegated | 08 names an independent verifier for each contract and the audit rate; 05 begins to show measured numbers; 03 fills with weak spots found by audits |
| 3 · autonomous | 05 adds the verifier's measured false-accept rate with its confidence bound, and the signed policy; 09 shows the best solutions under the frozen contracts |
| 4 · collapse | 01's main problem is marked answered; 09 becomes a routine service; the page shows which other fields it feeds |
| 4 · fission | 04 splits: the new subfield becomes a new agent with its own page, starting at stage 1 |

Two consequences. A full page is not a trusted page: nine sections at stage 1
is a broad agent checked only by its author. And climbing changes the contents
of sections 03, 05 and 08, not the number of sections.

---

## History

| Date (2026) | Change |
|---|---|
| 15 August | The AI4Science spec sets the three focuses (§6) and the nine sections, each with its own page (§7.4). Sections may start empty and be filled later. |
| 15 September | Recorded as the nine-section research-agent contract. |
| 27 September | "The nine sections are still there", but they are a pool, not a form: an agent shows only the sections it has and never an empty one; a benchmark stays required. |
| 16–17 October | The nine sections are confirmed as the original ones of 15 August, with each agent's filled pages kept per agent; an attempt to map them onto other parts was withdrawn. |
| 18 November | "An agent may show all nine when it has all nine." |
| 19 November | The One Method paper (draft v1.33, section 5, "What a field agent's page holds") states the nine sections in this form, with section 08 required and section 05 holding the stage. Section 03 is named "Self-awareness and self-improvement". |

## Sources

- AI4Science spec, 15 August 2026, §6 and §7.4
  (`singularity/docs/specs/2026-08-15-ai4science-spec.md`).
- Filled sections of the computational imaging agent
  (`singularity/docs/agents/computational-imaging/1-problems.md` …
  `9-solutions.md`).
- [`lifecycle.md`](lifecycle.md): the five stages, the agent as a group,
  self-awareness, recursive self-improvement.
- [`drug-design.md`](drug-design.md): the reference structure named by the spec
  for sections 04 and 05.
