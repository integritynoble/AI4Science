# The delegation agent — raising the frontier without touching the model

**Status: built and measured on this machine, 2026-08-24.** 57 tests. The
headline measurement, one solver held fixed across four arms:

| arm | result |
|---|---|
| **1** bare — capable but careless | **0/15** passed |
| **2** the same solver, harnessed | **15/15** passed |
| **3** an executor that *cannot* succeed, bare | **15/15 returned wrong work as done** |
| **3** the same executor, harnessed | **0/15 wrong work returned as done**; 15/15 escalated |
| **4** routed over both, learning from verdicts | **15/15** passed |

Nothing about the solver differs between arms. What differs is that the class
was made checkable before the work started and restartable while it ran.

---

## 1. Why this is a harness and not a model

The result the whole design rests on:

> Delegation is bounded by how cheaply a mistake can be found and how cheaply it
> can be undone — properties of the work, not of the worker.

So the lever is the task class, not the agent. And the constraint that shapes
everything else:

> Acceptance cannot be delegated to the doer. Execution scales without limit;
> acceptance only transfers. A result accepted by whatever produced it is an
> assertion, not a completed task.

Both are usually handled as advice — *use an independent verifier*, *be careful
with irreversible actions*. Advice is a property of the day. This makes them
mechanisms.

## 2. The loop

```
state a task
   │
   ├─ read the class ............ verifiability, reversibility, and p* = ρ/(1+ρ)
   │      p* unreachable? ....... escalate. That is the answer, not a failure
   │
   ├─ register a check .......... BEFORE the deliverable exists. Write-once,
   │                              hash-chained, sealed when work starts
   │
   ├─ snapshot .................. before the first mutation, not after
   │      irreversible? ......... gate it; no capability removes that floor
   │
   ├─ route ..................... P(verified success | executor, class), taken
   │                              pessimistically, from verdicts only
   │
   ├─ attempt ................... the executor. It never sees the register
   │
   ├─ accept .................... another process, running a copy, executing
   │                              what was registered
   │      not accepted? ......... classify the failure, restore, re-route
   │
   └─ compress .................. leave the check behind for next time
```

## 3. The five mechanisms

**The class is read first** (`contract.py`). Most loops open with an attempt.
This one asks *how would I know if this were wrong* and *what would undoing cost*,
and derives the reliability the class requires: `p* = ρ/(1+ρ)`. That number is
not the evaluator's to pick. A class whose failure costs thirty times what
success is worth demands 0.968, and running it at "usually fine" is not a
judgement call — it is arithmetic nobody did. Where residual harm is unbounded,
`p* = 1` and the honest move is to stop and ask.

**The check is registered before the work exists** (`criterion.py`). The register
refuses a criterion about a deliverable that already exists, refuses a second
criterion under the same name, refuses one that does not say what it misses, and
seals when execution starts. It is hash-chained, so an edit is *detectable*
rather than merely discouraged — file permissions can be undone by the same
user, and a hash cannot. It also reports **σ**, the share of criteria the agent
wrote for itself.

**The workspace is snapshotted before the first mutation** (`reversible.py`).
Anything classified irreversible does not run unattended, at any capability.
That is a floor, not a caution.

**Acceptance happens somewhere else** (`acceptor.py`). A separate process, a
*copy* of the deliverables, no inherited environment, and the chain verified
before anything runs. A check that tries to rewrite the deliverable changes only
the copy — there is a test for exactly that.

**Escalation is preferred to guessing** (`escalate.py`). An escalation has no
loss term: the task is not done and the damage is not done either. So when
confidence is below what the class requires, asking is not weakness, it is the
arithmetic. And the question asked is the *shallowest* one that unblocks — a
permission is CID0 and costs the level nothing, a strategy request is CID3 and
costs two levels.

## 4. Executors, competence, and routing

Executors sit behind one protocol (`executor.py`), so Claude Code, Codex,
Hermes, OpenClaw, Pi or a local model are adapters and the brain never learns
which vendor it is talking to. What it learns is
`P(verified success | executor, class)` as a Beta posterior — carrying its
evidence count beside its mean, so "one success" and "eighty" are not reported
identically — **updated only from independent verdicts.** An executor saying it
completed the feature is a claim, and a competence model built from claims
measures confidence rather than capability.

Routing scores `P(success)·value − cost − risk`, with `P` taken pessimistically.
An executor whose lower bound cannot reach the class's `p*` is not a candidate —
not "less preferred", *not eligible*.

**Failures re-route by kind**, which is the difference between retrying and
hoping:

| kind | what happens next |
|---|---|
| `SPECIFICATION` | back to the contract — re-running cannot fix a bad criterion |
| `EXECUTION` | the same executor again; it now knows which checks it failed |
| `CAPABILITY` | someone else. The **second** failure of one executor is called capability, not bad luck |
| `ENVIRONMENT` | same executor, after the environment is addressed |
| `VERIFICATION` | stop. A check that could not decide needs a stronger verifier, not more work |

## 5. Compression — the part that compounds

After a class is accepted, the criteria that accepted it are written out as a
reusable check (`compress.py`), and a later run of the same class finds it
already registered.

This matters more than it looks. Capability improvements raise the success rate
*within* a class. Compression **moves the class** — the next attempt, by any
executor, arrives with a check that did not exist before. It is the only route
by which an agent legitimately raises its own frontier.

## 6. Three bugs the measurement caught

Worth recording, because each one produced a *plausible* result that was wrong,
and none would have been visible from reading the code.

**The first run scored 15/15 and was meaningless.** Every derived check was
being passed through `python3 -c "…"` with json-escaped newlines, so Python
received a one-line syntax error and every check failed. The harness looked like
it worked because a blind retry happened to fix the task. The tell was in the
data: `attempts=3` on every episode and *self-check agreement 0/15*. A verifier
that cannot pass correct work is worse than none — it reports failure regardless
of the work, which is indistinguishable from strictness. Checks now carry source
and are written to a file.

**The router swapped executors on every failure.** `exclude=[…][:0]` made the
exclusion list empty, so an `EXECUTION` failure re-scored and flipped to the
other executor. Each one kept restarting from its first attempt; a budget of
four attempts bought four first attempts. Arm 4 sat at 70% until this was fixed.

**Executors were benched on three observations.** A lower bound that noisy
excludes a competent executor after an unlucky start, and an excluded executor
never earns the evidence that would readmit it — the heroic-run error run
backwards. The bar is now eight.

## 6b. A real executor: Claude Code

`claude_executor.py` puts the Claude Code CLI behind the same protocol. The
adapter is deliberately thin — everything that makes delegation work is in the
harness, and the executor is the replaceable part, so the adapter must not
smuggle any of it back in.

**It proposes no criteria.** The thing that will be judged does not write the
judgement. A criterion proposed by the doer is the acceptance ceiling with extra
steps, so the harness derives them and the executor never sees the register.

**Two isolation barriers, neither of them a prompt.** The scripted solvers could
not read the answer key because they had no shell. A real executor has one, and
`work/` and `keyed/` are siblings in a benchmark instance — `../keyed` is one
command away. So the key is *moved out of the tree* before any executor starts,
and the executor additionally runs in a standalone copy with no parent to walk
up into. An executor that can read the answer will eventually read it, and the
measurement would then be of the directory layout. Both barriers are tested.

**Confidence is self-reported and treated as such.** The escalation arithmetic
needs a number, so the executor is asked for one — and the harness never trusts
it, because an executor's account of how it went is a claim and the acceptor is
somewhere else.

The tool grant is narrow: `Read,Write,Edit,Bash,Glob,Grep`. No network, no
sub-agents.

```
python -m ai4science.harness.agents.delegation.live_experiment --seeds 0-1
```

RESULTS_PLACEHOLDER

## 7. What this does not show

**The careless solver's second pass is correct by construction.** Arm 2 shows
the harness converts a *detectable and fixable* error into a corrected result.
It does not show the harness fixes errors the solver cannot fix — arm 3 is the
control for that, and there the correct outcome is an escalation, not a pass.

**Five task classes, three families, T0–T2.** The harness has not been run
against T3+, and the DL4/DL6/DLΩ environments in `dli_bench` are not yet wired
to it.

**No LLM executor is connected.** The adapters are the protocol; the executors
measured here are scripted policies. That is deliberate for a first measurement —
a scripted solver makes the arms comparable — but it means nothing here is
evidence about any model.

**σ is 1.0 in every episode.** The agent derived all of its own criteria. That
is admissible and it is exactly what the reporting rule exists to surface: at
DL3 and above, most acceptance criteria will be self-authored, and the number
must be visible rather than assumed away.

## 8. Files

```
ai4science/harness/agents/delegation/
├── contract.py     read the class; p* = ρ/(1+ρ)
├── criterion.py    write-once hash-chained register, sealed at execution
├── acceptor.py     another process, a copy, the registered checks
├── reversible.py   snapshot first; gate what cannot be undone
├── escalate.py     the shallowest question; ask rather than guess
├── executor.py     one protocol, Beta competence, failure classification
├── router.py       score, eligibility, and re-routing by failure kind
├── compress.py     leave the check behind
├── loop.py         the agent
├── bench_solver.py a careless solver, a stubborn one, and derivable checks
└── experiment.py   the four arms above
tests/dli/test_delegation_agent.py   57 tests
```

Run it:

```
python -m ai4science.harness.agents.delegation.experiment --seeds 0-4
```
