# sarsi-worker — what to build next

Ordered by what blocks real use, not by what is interesting. Everything in
Tier 1 comes from a failure observed on a live run, and each entry names the
observation rather than the intuition.

Status legend: **open** · **in progress** · **done**

---

## Tier 1 — build these next

### 1. Task lifecycle: `stop`, `pause`, `archive` — *open*

There is no way to close a task. A worker that can open work but never close it
wedges itself: every task counts against `maxConcurrentTasks`, so a board that
fills stops accepting new work permanently.

**Observed (2026-08-03, grace):** the `work` board held five finished test
tasks. Every new directive was refused with `not started — concurrency`, and the
only available fix was `rm -rf` on the task directories — deleting state by
hand, outside any command, with no record that it happened.

**What it needs:** a terminal state that frees the slot, distinct from deletion
(`archive` keeps the plan, the verdict and the history — those are the record of
what the agent actually did). `pause` should stop the session without losing the
plan, so a task can be resumed rather than re-created.

### 2. Retry on FAIL, carrying the verdict's reason — *open*

The verifier already produces PASS / FAIL / UNVERIFIED **with a stated reason**.
A FAIL currently just sits on the board. The owner has to read the reason and
relay it into the session by hand.

**What it needs:** `retry` re-enters the session with *"the verifier says this is
not done yet: `<reason>`"* as the instruction, and re-verifies afterwards. This
closes the loop the verifier opens. It should refuse to retry indefinitely —
after N attempts it reports rather than spending.

### 3. Goal editing, not just criteria — *open*

`/edit <task> <n> <criterion>` changes what gets **verified**. The goal itself is
fixed at creation, so "make the plan and goal together with the user" is only
half possible today.

**What it needs:** a `/goal` verb, and a re-draft of the plan when the goal
moves — with the owner's edited criteria preserved, the way `polish` already
preserves owner-edited phases rather than adopting over them.

### 4. Evidence that can follow the work out of the task folder — *open*

Evidence gathering deliberately never leaves the task folder. But a goal that
names a project directory puts every artefact **outside** it, and the verifier
then receives nothing.

**Observed (2026-08-03, grace):** the goal named `/home/grace/live-gaptv`. The
session wrote `gaptv.py` and `result.json` there and finished correctly. `sarsi
check` returned `UNVERIFIED: nothing visible was supplied, so nothing was
judged`. Passing the listing by hand with `--evidence` produced an immediate
`PASS` citing `"psnr": 25.41`. The work was done; only the *looking* failed.

**What it needs:** the plan should declare its working directory, and evidence
gathering should read that declared root — still a fixed, declared boundary, not
a roaming search. This pairs naturally with **#8, blast radius**: one declaration
serves both.

### 5. A step and wall-clock budget per task — *open*

A session that loops burns tokens until someone looks at it. A declared budget
that pauses and reports beats one that runs all night.

---

## Tier 2 — worth it once Tier 1 works

### 6. A rule for destructive-command gates — *open*

At A2 the loop answers ordinary gates and abstains on anything it has no rule
for. That is the right default, but it stalls sessions doing legitimate cleanup.

**Observed (2026-08-03, grace):** the session chose to prove reproducibility by
deleting `result.json` and regenerating it. The `rm` tripped a `PreToolUse` hook;
the loop abstained four passes running and the task stalled with `a gate is
waiting for you`. Nothing was wrong with the session's plan — the loop simply
had no rule for it.

**What it needs:** a narrow rule — a delete confined to paths the plan declared,
of files the session itself created, during a phase that declared it. Narrow on
purpose: a blanket "allow rm" would make the abstention decorative.

### 7. Verdict parsing that resists narration — *open*

**Observed (2026-08-03, grace):** a verifier reply contained both words and the
loop reported `the verifier's answer gave more than one verdict: ['FAIL',
'PASS']`, correctly refusing to pick one. Refusing is right; **inviting** the
ambiguity is not. The prompt should demand a verdict line and nothing else, so
UNVERIFIED is reserved for genuine uncertainty rather than for chattiness.

### 8. Blast-radius declaration — *open*

The plan declares permissions; have it declare which **paths** it may touch, then
check afterwards that nothing outside them changed. This turns "it said it would
only touch the export folder" into something verified rather than trusted. Shares
its declaration with **#4**.

### 9. Task dependencies — *open*

`funding` drafting an application that needs `work`'s benchmark numbers is the
obvious case. Without dependencies the owner is the scheduler.

### 10. `status` across all seven — *open*

One screen: running, waiting on you, failed. Today answering "what is everything
doing?" means seven separate `sarsi tasks` calls.

### 11. A workspace fold — *open*

History is bounded with the overflow counted, but never summarised — so a long
task's early context is dropped rather than compressed. This matters most during
planning, which is exactly where the history is worth keeping.

### 12. Per-agent house rules — *open*

A file each worker injects into every kickoff.

**Observed (2026-08-03, grace):** the session ran `python demo.py`, hit
`/bin/sh: 1: python: not found`, and retried with `python3`. Cheap once;
paid again on every new session. `always use python3 on this host` belongs in
the agent's host workspace, not in each session's trial and error.

---

## Tier 3 — deliberately later

- **Handoff between workers** (`work` → `funding`).
- **`sarsi-machine` routing** — "who should do this?"
- **Per-agent web pages** at `physicsworldmodel.org/<agent>/`.

All three are more valuable once tasks reliably close (#1) and retry (#2).

---

## Recommended order

**1 → 2 → 3**, then **4**.

The board is unusable without #1, the verify loop is open-ended without #2, the
requested entry model depends on #3, and #4 is what stopped a *successful* run
from being recorded as one.

---

## Deferred by the owner, on purpose

- **PWM economics** — the 10% PWM fee on own-key / own-subscription LLM use, the
  auto-starting exchange node, the non-exchangeable treasury float, and stopping
  the node once holding enough PWM. Recorded in
  `singularity/docs/specs/2026-08-02-sarsi-worker-one-machine-design.md` §13.7.
- **Server-side domain agents** — computational-imaging, drug design and others,
  to be built as server agents rather than per-user workers.

See also: [`SARSI_AGENTS_GUIDE.md`](SARSI_AGENTS_GUIDE.md) for how the agents are
used today.
