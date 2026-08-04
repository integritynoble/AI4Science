# What a `sarsi-worker` can do — and what it should do next

One list, merged from three sources that were drifting apart:

- `AI4Science/docs/SARSI_ROADMAP.md` — written from failures observed on live
  runs against `tina` and `grace`;
- `singularity/docs/sarsi-worker-functions.md` — proposed commands, split by
  confidence, with three explicit refusals;
- `singularity/docs/specs/2026-08-03-sarsi-worker-functions.md` — ranked by what
  the first end-to-end runs proved was missing.

Where the three disagreed, the disagreement is stated rather than averaged away.

**`AI4Science/ai4science/harness/agents/sarsi/` is the canonical implementation**
(decided 2026-08-03). `singularity/sarsi/` is superseded — kept for reference,
not extended. Three behaviours had diverged; **all three are now decided** —
see [the three decisions](#two-implementations--and-the-three-decisions-that-settled)
at the end.

---

## Part 1 — Built

Each of these is live, tested, and exercised on the installed binary.

### Holding work

| Function | What it does |
|---|---|
| `do` / `/new <goal>` | Open a task. `/new` works from inside the worker; `do` from the CLI. |
| `tasks` / `/task` / `/tasks` | The board — every task, its state, and what each waits on. |
| `plan` | A task's phases, criteria and declared permissions. |
| `grant` | Grant one permission the plan declared — including `delete files in the working directory`, the **only** destructive gate the loop may answer, and only for a non-recursive delete of named paths inside that directory in a command that does nothing else. |
| `goal` / `/goal` | **Move the goal.** The plan is re-drafted to follow it, the agreement drops, the owner's own criteria survive, and a running session is told. |
| `/edit <task> <n> <criterion>` | Change what gets verified. The owner's edit wins; polish may only propose around it. |
| `stop` / `/stop` | Stop a task **and kill its session**. Resumable; the plan survives; the slot is freed. |
| `archive` / `/archive` | Terminal. Record kept, slot freed, off the board — counted on the board so archiving never reads as deleting. |
| `reopen` / `/reopen` | Put an archived task back, **stopped** — re-opening is a decision to look, not to start. |
| `/resume-task` | Put a stopped task back to work. Named apart from `/resume`, which hands *steering* back after Interact. |

### Running work

| Function | What it does |
|---|---|
| `run` | Hand the plan to `sarsi-claude` — starts its governed session. |
| `release` | Raise the ceiling from the planning `A0` to what the agent has earned. |
| `operate` | One supervision pass: answer the gates it has a rule for, submit a stranded prompt, report the rest. |
| `supervise` | Drive a task to a verified result. |
| `guide` / `/guided` | Steer by hand. The owner's word always goes through; the worker's stands down when the owner holds the wheel. |
| `/interact` | Hands over the `tmux attach` line and stands back. **It does not relay.** |
| `/history` | What has happened, from the record. |
| `handoff` | **`HANDOFF.md` for the next session**, written automatically when a task stops. Names the phases already verified so they are not redone, the verifier's last objection, open questions and grants held. It records what the RECORD knows — never what the session believed. |
| `check` | Ask the verifier: **PASS / FAIL / UNVERIFIED**, with a reason. The verdict is read from a verdict **line**, decoration and all (`**PASS**:`, `- FAIL:`), so prose containing the words is not a judgment and a bolded judgment is not discarded. **Gathers its own evidence** when none is given. A **stale plan is refused, not judged** — see decision 2. |
| `blast` | **What it wrote, against the paths its plan declared.** Read from the session's own `Write`/`Edit` records. `Bash` names no file, so it is counted as *unchecked* and never reported as clean — "nothing escaped" and "nothing was left unobserved" are separate answers. |
| `do --after <agent>/<task>` | **One task waits on another, across agents.** Satisfied means **verified** — not stopped, not archived, because closing a task is not succeeding. An unknown dependency and a cycle are both refused at declaration, since a task that can never run must say so while you are still looking. It never auto-starts what it unblocks. |
| `do --steps N --minutes M` | **A declared ceiling.** Past it the task *stops and keeps its plan* — it does not fail, because running out of budget says nothing about whether the work was right. Checked **before** the loop acts. Steps come from the transcript; unreadable means *not enforced*, never *over*. No default. |
| `do --workdir <dir>` | Declare **where the work happens**. Evidence is gathered from there instead of the task folder — declared, never inferred, so a criterion naming a path cannot move the boundary. A path outside it is reported as outside, never read and never silently dropped. |
| `check --phase N` | Judge **one phase against its own criterion**. A phase is done when a verdict says so about *that* phase; the task is verified only when every phase is. Editing a criterion clears that phase's verdict; moving the goal clears all of them. |
| `retry` | **Hand a FAIL back carrying the verifier's reason.** Only a judged `FAIL` retries; capped at 3; a `PASS` clears the count. |

### Knowing where you are, and what needs you

| Function | What it does |
|---|---|
| `questions` / `answer` | **The escalations, in one place, answerable from either surface.** `answering` declines what it must not answer and escalates it; these list what is open and deliver your reply into the session. The owner closes a question — a later automatic answer does not. |
| `attention` | **"Is anything waiting on me?"** across every worker, or one. Gates (with the actual command), **terminals no task claims**, orphans, ungranted permissions, open questions, exhausted retries, undelivered kickoffs, stale plans, and records pointing at terminals that are gone. Exits non-zero when something waits, so a timer can act on it. |
| `enter` | Step into a worker: the task you last touched, or — holding none — **the question "what would you like done?"** rather than an empty board. It **reconciles the records against tmux** first, so it reports now rather than what was true when the record was written. |
| workspace fold | The history a node plans from keeps the most recent lines **and folds the overflow**: anything said three times or more is promoted with its count (`use the staging host ×5`), which is exactly what a plain tail loses. Repeats take **one** slot in the visible window rather than filling it. A **tally, never a précis** — every promoted line was actually written. |
| cursor per `(surface, account)` | Being *in* a task, so plain words are about that task. Stored on disk; the phone and the laptop stand in different places. |
| `why` / `/why <task>` | **The goal, the criteria a verdict will apply, and what the last verdict said** — in one answer. Reports and never infers: no verdict says *not judged yet*, and it will not name a "current phase" (see below). |
| `spend` | **What it cost** — tokens in/out, cached apart from fresh, and wall-clock — read from the session transcripts, not estimated. Unknown is reported as *not recorded*, never as 0, and PWM as *not charged here* rather than 0. |
| `decisions` | **What it decided without you, and at which rung.** Only the agent's own acts — the owner's guidance is not the agent deciding. An act recorded with no ceiling reads `unknown`, never `A2`. Reading does not acknowledge; `--ack` moves the line and `--all` still shows everything under it. |
| `ask` / `self model` | What the worker observes about itself. |
| `improve yourself` / `yes` | RSI: it proposes a playbook change and holds it until the owner signs. |

### Outward, and secrets

| Function | What it does |
|---|---|
| `send` | Ask to let one act leave the machine. Drafting is not sending. |
| `undo` | **Take back the last outward act — when that is possible at all.** Mail cannot be recalled and a submitted form cannot be withdrawn; both say so and name the real remedy. A post **is** retractable: the platform's id is recorded when it publishes (cleared before every send, so a stale one can never be attributed to the next), and `x` / `linkedin` / `substack` have a delete call wired. Every ambiguity resolves toward doing nothing — a 404 is not called success, because *already gone* and *wrong id* look identical from here. A failed attempt is recorded as an attempt, never as a retraction. |
| `submit` | Submit a form — every field shown, and it cannot be undone. |
| `vault` | Two-stage secrets; money policies need a limit, a counterparty and a rate. |
| `ceiling` | Set the auto level (A0–A3), per agent or all. Reports where it will *actually* land. |

---

## Part 2 — Next, in order

### 1. Per-agent house rules

A file each worker injects into every kickoff.

> **Observed 2026-08-03, grace:** the session ran `python demo.py`, hit
> `/bin/sh: 1: python: not found`, and retried with `python3`. Cheap once; paid
> again on every new session. *"Always use python3 on this host"* belongs in the
> agent's host workspace, not in each session's trial and error.

### 2. `digest`

§6's `DIG` — one daily read across tasks.

---

## Part 3 — Deliberately later

- **Handoff between workers** (`work` → `funding`).
- **`sarsi-machine` routing** — "who should do this?"
- **Per-agent web pages** at `physicsworldmodel.org/<agent>/`.

All three are more valuable now that tasks close and retry, but they are still
after the list above.

---

## Part 4 — What NOT to build

Both source documents refuse the same things, for the same reasons. Each is a
plausible convenience that would cost the property it sits next to.

- **Auto-approving permission gates** — even "safe" ones. The moment the worker
  can approve, the ceiling means nothing. Two of the three gates hit on
  2026-08-03 were things the owner would want to see.
- **`approve all pending`** — batching approvals is how consent stops meaning
  anything. Each outward act must be read.
- **`trust this agent more`** — *the one to refuse hardest.* It widens authority
  from a **feeling**, and the whole competence design exists to make that
  impossible. Trust is earned in the ledger or it is not trust.
- **A worker that starts work on its own** — `run` is the owner's opt-in, and it
  is the only thing separating *"I asked a question"* from *"I authorised
  work"*.
- **A worker choosing its own concurrency** — RSI proposes, the owner signs.
- **Relaying keystrokes in Interact** — a relay is a lossy imitation of a
  terminal and puts two things typing into one pane. The attach line is honest.

### The one refusal that was overruled, and why

`singularity/docs/sarsi-worker-functions.md` lists **`retry`** as *do not
build*: *"a bare retry re-runs a plan that already failed its criteria."*

That objection is correct, and the `retry` that was built satisfies it rather
than ignoring it:

- the verdict's **reason** is the instruction — a retry with no new information
  is exactly what the doc warns against, and is impossible here;
- a task with **no verdict** is refused outright;
- **`UNVERIFIED`** is refused by name — nothing was judged, so a retry would
  spend a session on a *looking* problem rather than a *doing* one;
- it **caps at 3** and then reports.

What the doc refuses is a *button*. What exists is a *reason carrier*.

---

## Two implementations — and the three decisions that settled

These functions exist twice, in two repositories, from one spec. Three
behaviours had diverged. **All three are now decided, and this implementation
follows the decision in every case.**

### 1. Should `retry` exist? — **yes**

`singularity/docs/sarsi-worker-functions.md` listed it as *do not build*:
*"a bare retry re-runs a plan that already failed its criteria."*

The objection is right about a **button** and wrong about a **reason carrier**.
What is built refuses to be the thing the doc warns against:

- the verdict's **reason** is the instruction, so a retry always carries new
  information;
- a task with **no verdict** is refused outright;
- **`UNVERIFIED`** is refused by name — nothing was judged, so a retry would
  spend a session on a *looking* problem rather than a *doing* one;
- it **caps at 3**, then reports instead of spending.

### 2. The stale-plan rule — **yes, the strict one**

After Interact the owner drove the session by hand, so the plan no longer
describes what happened. The two builds handled that differently:

| | behaviour |
|---|---|
| was, here | criteria **withheld**, judged **against the goal alone** |
| was, singularity | **`UNVERIFIED`** — rewrite the plan before asking |

**The strict rule wins, and this implementation now uses it.** Judging against
the goal alone silently answers a *weaker* question than the one the owner set
and reports the answer as though it were the one they asked. That is exactly how
a false PASS gets recorded — the failure mode this system has already been bitten
by once, when a narrated `PASS/FAIL` line was read as a verdict.

The refusal names the escape hatch: `/edit <task> <phase#> <criterion>` clears
the staleness, because rewriting the plan *is* the owner restating the mission.

### 3. Should answering be wired into the loop? — **yes**

It is, here: `operator.py` calls `answering.answer()` inside the supervision
pass, so a session that asks *"which directory should I index?"* is answered
within a pass instead of waiting for the owner. In `singularity/sarsi/`,
`answer.py` is built, tested, and called by nothing — its own proposal calls
wiring it *"the largest value per line of new code anywhere in the system."*

### Where that leaves the two builds

**`AI4Science/ai4science/harness/agents/sarsi/` is canonical.** Decided
2026-08-03. `singularity/sarsi/` is superseded: it is kept as a reference and
should not be extended.

| | `AI4Science/…/sarsi/` (canonical) | `singularity/sarsi/` (superseded) |
|---|---|---|
| `retry` | built, reason-carrying | listed "do not build" |
| stale plan | **UNVERIFIED, strict** | UNVERIFIED, strict |
| answering wired | **yes** | no |
| task lifecycle | `stop` / `archive` / `reopen` | proposed |
| entry cursor | built | `shell.py`, uncommitted |
| `questions` / `answer` | **The escalations, in one place, answerable from either surface.** `answering` declines what it must not answer and escalates it; these list what is open and deliver your reply into the session. The owner closes a question — a later automatic answer does not. |
| `attention` | built, incl. **orphan** | proposed |

### What was salvaged from it before retiring it

The superseded build made observations this one had not. Those are worth more
than its code, so they were carried across rather than lost:

- **the strict stale-plan rule** — adopted wholesale (decision 2 above);
- **`orphan`** — a terminal *still running* after its task ended. The mirror of
  a dead session, and the more dangerous of the two: nothing is steering it and
  it still holds whatever the task was granted.

  > **Observed on that fleet:** a session sat running for two hours after its
  > task had FAILED, holding a grant at A2, and nothing reported it.

  `attention` now reports it, ranked directly after a gate. A finished task
  whose terminal is *also* gone is **not** reported — the record and the machine
  agree, nothing holds a grant, and tidying a stale record is not something that
  needs the owner.

### Still worth porting

Not yet built here, and named so the decision to retire that build does not
quietly drop them:

| From | Idea | Why it is worth having |
|---|---|---|
| `competence.py` | read the ledgers back into a **capability estimate** | the system records what it *did* and nowhere what it *can do* |
| `board.py` | one source, **three faces** — CLI, chat, and a local HTML page | the page is the `physicsworldmodel.org/<agent>/` idea, and it guarantees a task cannot look ready in one place and blocked in another |
| `conversation.py` | never re-ask on one surface what was answered on the other | `ownerlog` records both surfaces; nothing yet *uses* that to suppress a repeat question |

---

See also: [`SARSI_AGENTS_GUIDE.md`](SARSI_AGENTS_GUIDE.md) — how to use what is
built today.
