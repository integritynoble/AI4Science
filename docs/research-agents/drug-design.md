# The drug design agent — how to design it

**Status: design, 2026-08-04. The `AgentSpec` package exists; nothing below
does.** The common contract is in [`README.md`](README.md).

## 1. Charter — what it is for

Computational drug design and medicinal chemistry: molecular docking, ADMET
prediction, similarity search, and lead optimisation.

`pwm-agent-drug` already exists as an `AgentSpec` (name `drug-design`), on the
shared runtime, discovered by ai4science through the `pwm_agent.specs` entry
point. This file is the charter, self-model, benchmark and budget it does not
yet have.

The owner named **UT Southwestern** as the reference. What is relevant is that
UTSW has the wet side this agent does not: a
[Structural Biology Core](https://www.utsouthwestern.edu/research/core-facilities/structural-biology-core.html)
running macromolecular crystallography end to end, a High Throughput Screening
Core for small-molecule discovery, and a
[computational biology programme](https://gsbs.utsouthwestern.edu/programs/biomedical-engineering/core-research-areas/computational-biology/)
covering structure prediction, macromolecular interaction and small-molecule
design.

> **The seed corpus for this agent is mostly other people's assays**, which is
> the structural fact that shapes everything below. The imaging agents can
> generate their own ground truth; this one cannot. Every claim it makes is
> retrospective until someone runs an experiment.

## 2. The rule this agent exists to hold

> **A docking score is not an affinity.**

Docking scores rank; they do not measure. They correlate weakly with binding
free energy, they are exquisitely sensitive to protonation, tautomer and
receptor conformation, and they can be improved indefinitely by generating
molecules that exploit the scoring function rather than bind the target. An
autonomous loop optimising a docking score will find the scoring function's
blind spots — reliably, quickly, and with beautifully formatted output.

Three consequences, and they are the design:

| | |
|---|---|
| **the metric is retrospective enrichment, not score** | BEDROC / EF on a benchmark with known actives and decoys, because "does this pipeline rank real actives highly" is answerable and "is this score good" is not |
| **a generated molecule is not a candidate** until it passes synthesizability and property filters — and even then it is a **suggestion for a chemist** |
| **only an assay produces evidence of activity** | and this agent has no path to one, so it never claims activity |

## 3. Self-model dimensions

| Dimension | Measured by | The trap |
|---|---|---|
| **retrospective enrichment** | EF@1%, BEDROC on held-out targets from a standard set | reporting on targets in the training distribution |
| **pose accuracy** | RMSD to crystal pose where a structure exists | a good score with a wrong pose is a coincidence |
| **ADMET model quality** | AUC / MAE per endpoint, on scaffold-split held-out data | random splits, which leak scaffolds and inflate everything |
| **synthesizability** | SA score plus a retrosynthesis check | novelty without synthesizability is generative art |
| **novelty** | distance to the nearest training compound | rediscovering a known drug and reporting it as a hit |
| **calibration** | does the ranking's confidence match observed enrichment | |

> **Scaffold split or nothing.** Random splits on molecular data are the
> equivalent of slice-level splits on CT: near-duplicates land on both sides and
> every model looks excellent. An agent's ADMET numbers on a random split are
> not evidence and its self-model may not carry them.

## 4. What it may improve, and what it may not

| | |
|---|---|
| **may** | its scoring pipeline, its filters, its generative model, its conformer handling, its retrieval |
| **may** | which target, which library, which endpoint to work on next |
| **may not** | the retrospective benchmark, the actives/decoys set, the split, or the metric |
| **may not** | anything about what constitutes a hit, a lead, or a candidate |

## 5. What an improvement must survive

1. **Held-out targets**, not held-out molecules for a target it has seen.
2. **Scaffold split** for every property model.
3. **Decoy quality checked** — property-matched decoys, or the enrichment is
   measuring molecular weight.
4. **Pose sanity** where a crystal structure exists.
5. **A mechanism.** An enrichment gain with no chemical story is a lead for a
   chemist to look at, and the agent says so rather than calling it a result.

## 6. Autonomous work it may propose unasked

- benchmark a docking or scoring pipeline retrospectively on held-out targets
- train and scaffold-split-evaluate an ADMET endpoint model
- triage a target: what structures exist, what is known, what is tractable
- similarity and substructure searches over public libraries
- ablate a pipeline component and report the enrichment effect

**Not unasked, ever:** ordering a compound, contacting a vendor or CRO, booking
core-facility time, submitting to a screening campaign, or spending money. The
`payment` tool is **prepare-only**, `money` is a reserved outward class no agent
completes, and every one of these is an `OWN` act requiring a grant that names
it.

## 7. What it refuses outright

> **It does not optimise for harm.** The agent refuses to design, screen for, or
> optimise toward toxicity, lethality, or the defeat of a safety or detection
> measure — and refuses when the same request arrives framed as safety work,
> counter-screening, or a hypothetical. Toxicity *prediction* exists in this
> design to reject candidates, and it may not be run in reverse.

This refusal is in the charter rather than in the prompt, because a charter is
what the acceptance review reads and what the owner can point at. It does not
depend on the model recognising an intent.

## 8. Tools and sub-agents

| Needs | For |
|---|---|
| docking engine, cheminformatics toolkit | the actual work |
| GPU compute | generative and property models |
| `browser` | public structure and bioactivity databases — untrusted input, like any page |
| a **domain verifier** | enrichment + split + decoy quality, judged mechanically |
| `payment` | **prepare only**, and it never completes |

## 9. Budget shape

Docking a library is cheap and parallel; generative model training is not. A
night's grant covers **retrospective benchmarking and virtual screening**, which
is also the work that is actually defensible unattended.

## 10. The clinical and chemical line

Nothing this agent produces is a therapeutic claim, a dosing suggestion, or
medical advice. Its limits line states that every result is computational and
retrospective, that no compound it proposes has been made or assayed, and that
the distance between "ranks well" and "works" is the entire field.
