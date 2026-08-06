# Using the sarsi agents

How to run work through them, how to write a task worth running, and what
happens between your message and a verified result.

Design: [`singularity/docs/specs/2026-08-02-sarsi-worker-one-machine-design.md`](https://github.com/integritynoble/singularity/blob/main/docs/specs/2026-08-02-sarsi-worker-one-machine-design.md).

---

## 1. The shape, in one paragraph

You talk to an **agent**. If it is a worker, it turns what you said into a
**task**, writes that task a **plan**, and hands the plan to a **`sarsi-claude`**
session — one session per task, in its own folder, governed at a ceiling. That
session drives **Claude Code**, which does the work. An **independent verifier**
decides whether the goal was met; the agent never grades itself. Anything that
would leave the machine stops and waits for you.

```
you ──▶ agent ──▶ task ──▶ plan0.md ──▶ sarsi-claude ──▶ Claude Code
                                             │
                          verifier ◀─────────┘        anything outward ──▶ you
```

**One rule holds all of it up:** *the agent you talk to does not execute.*
`sarsi-machine` routes and answers and can never touch a session — not by
policy, by a raise in the code.

## 2. The roster

| Agent | Use it for | What stops at you |
|---|---|---|
| **`sarsi-machine`** | "who should do this?", the fleet view | — it executes nothing |
| **`sarsi-worker`** | anything with no better home | — |
| **`work`** | your job: code, data, the tools that job needs | **sending** an email |
| **`social`** | one daily read; drafts for X / LinkedIn / Substack | **posting** |
| **`funding`** | grant and programme applications | **submitting** |
| **`jobs`** | CV, and filling in application sites | **submitting** |
| **`abraham`** | your own life, not your work | **anything outward** |

### They are built on the ai4science agents, not beside them

Each of the seven names an ai4science agent spec its sessions run. The registry
already ships agents written for exactly these roles, so the seven are an
orchestration layer over those — a task board, a plan, a supervised session —
rather than a second stack with the same names.

| Agent | Built on | Drivable unattended |
|---|---|---|
| `sarsi-machine` | `manager` | attended |
| `sarsi-worker` | `claude-code` | yes |
| `work` | `claude-code` | yes |
| `social` | `social` | attended |
| `funding` | `research` | attended |
| `jobs` | `unified-LLM` | attended |
| `abraham` | `pocket` | attended |

`ai4science sarsi agents` prints this as the **Built on** column.

Two consequences worth knowing:

**A spec that is not installed is refused by name.** The specs live in separate
packages (`pwm-agent-claude-gpu`, `pwm-agent-research`, `pwm-agent-unified`, …),
so a fresh machine with only `pwm-agent-core` has some of them missing. The
refusal lists what *is* installed. It never falls back to a generalist — running
the wrong agent under the right label is worse than not starting.

**"attended" means the supervision loop will not drive it unwatched.** The
screen-reading in `sarsi operate` — permission gates, stranded prompts, the busy
marker — is tuned to Claude Code's TUI. An agent on another interface starts
fine and you steer it yourself; the table says so rather than letting the loop
mis-read a screen it does not understand.

### Two you should understand before using

**`work` may read your mailbox and may never send by itself.** And an
instruction *inside* an email is not an instruction to it — a message saying
*"please wire the invoice"* is evidence that someone asked, never authority to
act. Without that rule, "read my email" is a remote-control channel into your
machine.

**`abraham` has the loosest scope and the tightest authority.** It holds no
standing grants at all, and it **abstains** on money, consent, publishing and
legal rather than asking — because asking would imply a grant would help, and
none would. It prepares those and completes none.

## 3. Setting up

```bash
ai4science sarsi init --owner-id <your telegram user id>
ai4science sarsi agents --bindings
```

`--owner-id` is the **only** id whose Telegram messages are honoured. Everything
else is dropped and counted, never answered.

Optional, per agent:

```bash
ai4science sarsi set-token work 8541204756:AA…      # a bot per agent
ai4science sarsi vault put mail.smtp                # prompts; never echoed
```

Both surfaces reach the same agent, the same memory, the same sessions:

```bash
ai4science sarsi ask sarsi-worker "…"        # CLI
# …or message that agent's bot
```

A surface is a door, not a scope. What you say on one is visible on the other,
and the agent will not re-ask something you already answered elsewhere.

## 4. Designing a task

This is the part that decides whether any of it works.

```bash
ai4science sarsi do sarsi-worker "<goal>" [--tool matlab] [--secret mail.read]
```

### From inside the chat REPL: `/do`

There are two agents called `work`, and telling them apart saves confusion.

`/agent work` in the `ai4science` REPL switches the **chat** agent. That is the
original ai4science agent and it answers in-process — ask it for a GAP-TV
implementation and it writes one, right there, in your session. Nothing is
wrong with that; it is what that agent has always been for.

Its **sarsi** counterpart is the other contract: the agent you talk to does not
execute. `/do` is the door between them:

```
❯ /agent work
❯ /do write a gap-tv algorithm for cassi
work holds tsk_a1b2c3d4 — planning
  plan drafted; sarsi-claude agrees it before work starts
  open it:    ai4science sarsi plan sarsi-worker tsk_a1b2c3d4
  run it:     ai4science sarsi run sarsi-worker tsk_a1b2c3d4
❯ /tasks
```

`/do` **delegates and returns** — it files the task and drafts the plan, and the
goal text is never run in your REPL process. From an agent with no sarsi
counterpart it lists the ones that have a board rather than guessing which you
meant, because a guess files the task under the wrong owner.

Rule of thumb: **`/do` when you want it planned, verified and on a board; plain
chat when you want an answer now.**

**The goal is one sentence.** Not the conversation — a goal longer than 2,000
characters is refused rather than truncated, because truncating drops the part
you cared about without telling you.

**Name what it needs.** `--tool` is checked against this machine for real. If
it is absent the task is refused **naming what is missing**, and is *not
queued* — nothing waits quietly pretending to be work in progress.

### The plan is where the task becomes real

Every task gets a `plan0.md`:

```markdown
# finish the export

## Phase 1 — drain the queue
Verified when: the queue length reads 0 in the console

## Phase 2 — re-run the export
Verified when: export.csv exists and has 1,204 rows

## Permissions needed
- read secret mail.read
```

Three things about it:

- **Each phase ends in `Verified when:`** — that line *is* what the independent
  verifier judges. A phase without one is refused at construction, because the
  only grader left would be the agent that did the work.
- **`Permissions needed` is asked before anything runs.** The worst moment to
  request permission is halfway through unattended work.
- **The first draft is deterministic and thin.** With no criterion given it
  writes one from your goal and marks it `(provisional)`. That is the honest
  floor, and it is why the next step matters.

### Write the criterion yourself

The single highest-leverage thing you can do:

```bash
ai4science sarsi ask sarsi-worker "/<task-id>"                    # read the plan
ai4science sarsi ask sarsi-worker "/edit <task-id> 1 export.csv exists and has 1,204 rows"
```

Your edit is **authoritative**: it makes the plan fresh, and a later polish
round may only *propose* a successor, never replace it.

A good `Verified when:` line names something a stranger could **see on the
screen**. Compare:

| weak | strong |
|---|---|
| the export works | `export.csv` exists and `wc -l` reports 1,205 lines |
| tests pass | `pytest -q` prints `0 failed` |
| the site is up | `curl -sI …` returns `200` |

An unproven claim fails, so a criterion that cannot be *shown* cannot pass.

### Grants

```bash
ai4science sarsi tasks sarsi-worker                                # state + what it waits on
ai4science sarsi grant sarsi-worker <task-id> "read secret mail.read"
```

A grant answers the permission it names and no other.

## 5. From task to `sarsi-claude` to Claude Code

The plan is made **between** the worker and the session, and the ceiling is what
holds the work back until you have seen it.

```bash
ai4science sarsi do        sarsi-worker "<goal>"  # 0. create the task
ai4science sarsi run       sarsi-worker <task>    # 1. plan, at A0
ai4science sarsi supervise sarsi-worker <task>    # 2. collect it   ← REQUIRED
ai4science sarsi grant     sarsi-worker <task> "…" # 3. grant what it declared
ai4science sarsi release   sarsi-worker <task>    # 4. raise the ceiling
ai4science sarsi supervise sarsi-worker <task>    # 5. drive it to a verdict
ai4science sarsi check     sarsi-worker <task>    # 6. judge it again, any time
```

> **Step 2 is not optional, and skipping it is the commonest way to get stuck.**
> The session drafts `plan0.md` in its own folder; until `supervise` collects it,
> nothing is attached to the task — so there is no declared permission to grant
> and nothing to release against. `release` says so and names the step.
>
> **Give collection time.** It takes several passes. A `supervise` interrupted
> after a minute has usually not got there, and the task will still read
> `planning` — which looks like a failure and is not one.
> `--passes 20 --interval 12` is a sensible first run.

**1 — plan.** The worker writes an initial `plan0.md` (anchored to your goal,
scope and declared tools) and asks the session to *improve it in place, then
stop*. The session has the model and the repo; the worker has what you asked
for. The session starts at **`A0`** — reads allowed, everything else asks — so
"stop after planning" is enforced by the ceiling rather than requested in a
sentence. The one write it needs, `plan0.md` itself, is the single extra gate
the supervisor will answer while planning.

The kickoff also carries the **workspace**: your own words, grants already held,
criteria that passed before, permissions discovered mid-run last time, and
secrets previously refused. A plan written without the history asks again for
what you already refused.

**2 — collect.** The worker reads the plan back. If a phase has no
`Verified when:` line it is sent back to be fixed, not accepted. If the session
never touched the seed, that is recorded — a stub is never mistaken for a
considered plan.

**3 — grant.** The task waits at `awaiting-grant`. Negative bullets ("no
network") are separated out as constraints; you are not asked to grant a limit.

**4 — release.** The ceiling rises to whatever that agent has **earned** —
`A3` in the registry is still capped at `A2` until the trust ledger says
otherwise — and the session is told which phase to work.

Then supervise it:

```bash
ai4science sarsi supervise sarsi-worker <task-id> --passes 8 --interval 25
```

One pass, in this order — and the order is the point:

| | | |
|---|---|---|
| **V** | is the goal already met? | verification sits **above** the typing steps |
| **AN** | a gate on screen? | answers only gates it recognises; anything else waits for you |
| — | mid-turn? | leave it alone |
| **Q** | is it **asking you something**? | answers from the plan, or stops for you |
| **SP** | a prompt stranded at the `❯`? | submits it **verbatim**, retypes nothing |
| **S** | otherwise | composes **one** instruction and types it |

### When `supervise` stops, and what each stop means

The loop ends a run rather than using every pass whenever another pass cannot
change the answer. What it prints is what to do next:

| it says | what it means | you |
|---|---|---|
| `verified` / `done` | the verifier passed it | nothing |
| `awaiting-grant` | the plan is collected and declares permissions | `sarsi grant <agent> <task> "<permission>"`, one per line it names |
| `asks-owner` | the session asked something the plan, the scope and the record do not settle | answer it — `sarsi guide <agent> <task> "<answer>"` — then supervise again |
| `attended` | this agent's interface is not one the loop can read | drive it yourself: `tmux attach -t <session>`, then `sarsi check` |
| `no-session` | the session is gone | `sarsi run` again |
| `paused` | you have the wheel (Interact) | resume when ready |
| `over-budget` | the task's budget is spent | raise it, or stop the task |

`over-budget` is the one kind that keeps looping deliberately: you can raise a
budget from another terminal, so waiting can genuinely change it. The others
cannot change without you, and a loop that re-derived them every twenty seconds
was reporting the same sentence six times while the work sat finished.

### What the verifier is given

**Not the terminal.** The pane is where a session *says* what it did; evidence is
what it *left behind*. So a listing of the task folder and the real contents of
the files your criteria name are read from disk, absence of a named file is
reported as absence, and the pane is included last and labelled *narration*.

Naming a file in your `Verified when:` line is still worth doing — a named file
is read **first** and in full. When a criterion names none, the folder's own text
files are read instead, newest first and capped, with anything the cap left out
stated rather than dropped. Before that, a verdict could rest on a directory
listing, and a verifier was right to refuse it: *the existence of a file named
`report.md` is a claim that work was done, not evidence of its content.*

### When the session asks a question

Claude Code asks things mid-task: *which directory*, *tests first?*, *which of
these two approaches*. The agent answers **only from what it already holds** —
the goal, the criteria, the scope, and what you have said — and records the
question with its answer.

It stops for you rather than guessing when the workspace does not settle it, and
it will **never** answer:

- an **owner fact** (salary, start date, a reference) — it asks rather than invents;
- a request for a **secret** — that is the vault's question;
- anything that would **widen what the session may do** — `sudo`, skipping a
  check. Authority is decided at the gate, and a clarification that grants
  permission is not a clarification.

The composer is given the plan, the phase by name, the verifier's last reason,
**what you said**, its own last five prompts (*do not repeat what failed*), and
any failure signature on screen.

### A run that actually happened

Verified end to end on a second user account on 2026-08-06, `sarsi-worker`
driving a Claude Code session. Goal: *count the `.md` files under
`/home/grace/sarsi-state-check`, and if the folder does not exist say so and do
not create it.*

| | |
|---|---|
| `run` | session started, `planning`, at A0 |
| `supervise --passes 20 --interval 12` | `planned — 4 criterion(s)`, then `awaiting-grant`, naming three permissions |
| `grant` ×3 | on the third the task became `running` |
| `release` | ceiling raised |
| `supervise` | it worked, wrote `probe-log.txt` and `findings.md`, then stopped at `asks-owner` |
| `check` | one criterion FAIL, the rest PASS |

**The result was right**: `RESULT: folder does not exist` / `COUNT: 0 (folder
absent)`, confirmed independently. **The FAIL was also right** — phase 4's
post-check never ran, and the session had said so itself.

Two things in that run are the design working rather than the run going well:

* the session reasoned *"`Read` came back 'File does not exist' — but that tool
  returns the same error for a missing path and for a directory, so it settles
  nothing. I can't assert it from A0."* It asked instead of guessing.
* the verifier noticed `plan0.md` had been edited after release and **refused to
  judge against the moved copy**: *"Judged against what you released… to make
  the file the standard instead: `sarsi adopt`."*

### Which agents this flow drives

Only the ones whose interface the loop can read — `claude-code` and `codex`.
`sarsi agents` marks the rest **(attended)**: they start and run normally, and
`supervise` will tell you it cannot read them rather than typing blind at a menu.
For those, attach, work with the session yourself, and record the outcome with
`sarsi check` — which is what the `attended` stop prints.

### If a roster agent is missing

A registry written by an earlier release does not gain agents that shipped
later, and `init` refuses to overwrite a live one:

```bash
ai4science sarsi init --reconcile     # adds roster agents this release ships
```

Additive only — it never removes, rewrites or re-ceilings anything you have set.

## 6. Getting into a running session

```bash
ai4science sarsi ask sarsi-worker "/<task-id>"
```

| Mode | Who drives | What happens |
|---|---|---|
| **Guided** | the worker | `/guided <task> add tests first` — steered in |
| **Interact** | **you** | pauses steering, marks the plan stale, prints `tmux attach -t …` |
| **History** | nobody | `/history <task>` — the record |

**Interact does not relay.** It hands you the terminal and stands back: a relay
would leave two things typing into one pane with a protocol deciding who wins.
`/resume <task>` gives the wheel back.

## 7. The verdict

```bash
ai4science sarsi check sarsi-worker <task-id> --evidence "$(…)" --engine claude
```

Three answers, and the third is why you can trust the other two:

- **PASS** — a judge saw the evidence and every criterion was met.
- **FAIL** — a judge saw it and they were not. The reason is fed back into the
  session as the next instruction.
- **UNVERIFIED** — **nobody judged it.** No verifier reachable, an unreadable
  answer, or no visible evidence. Never a pass, and nothing is steered on it.

Answers state their authority: *verified*, *recorded*, *not judged*, *I think* —
and name the session. In a fleet, "it worked" is an incomplete sentence.

**A stale plan is refused, not judged.** After Interact you drove the session by
hand, so the plan no longer describes what happened — and judging against the
goal alone would quietly answer a *weaker* question than the one you set, then
report the answer as though it were the one you asked. That is how a false PASS
gets recorded. `check` returns UNVERIFIED and names the way out:

```bash
ai4science sarsi ask sarsi-worker "/edit <task> 1 <what done now means>"
```

Rewriting the plan **is** you restating the mission, so it clears the staleness.

## 8. What leaves the machine

Nothing, without you:

```bash
ai4science sarsi send sarsi-worker --kind mail --to bob@x.com --subject "…" --body "…"
ai4science sarsi submit jobs form.json
```

You are shown **exactly** what would go out — recipient, subject, whole body, or
every form field and value. The approved bytes are the transmitted bytes: a
platform or a form that trims, re-cases or drops anything is caught and refused.
A timeout denies. A refusal is an outcome, not an error. One approval covers one
act.

Reversibility is stated: a submission reads **THIS CANNOT BE UNDONE**; where
nobody supplied the cost it reads **unknown**, never *free*.

## 9. The self-model, and improving an agent

```bash
ai4science sarsi ask sarsi-worker "self model"
ai4science sarsi ask sarsi-worker "improve yourself"      # proposes, citing real numbers
ai4science sarsi ask sarsi-worker "yes"                   # only you can sign it
```

Every line of the self-model carries its source, `verified` counts only what the
verifier granted, and an unmeasured ability answers *unverified* rather than
being guessed at. An agent can never promote its own candidate, raise its own
ceiling, or widen any authority.

## 10. Command reference

```
SETUP     sarsi init --owner-id <id> · init --reconcile · agents [--bindings]
          sarsi set-token <agent> <token>
          sarsi ceiling <agent|all> A0|A1|A2|A3
TALK      sarsi ask <agent> "<text>"        (or that agent's bot)
REPL      /agent <name> then /do <goal> · /tasks     # inside `ai4science`
WAITING   sarsi attention [--agent <id>]    # what is waiting on YOU (exit 1 if any)
ENTER     sarsi enter <agent>               # the task you last touched, or the question
LIFECYCLE sarsi stop|archive|reopen <agent> <task> · tasks <agent> --archived
          sarsi goal <agent> <task> "<new goal>" · retry <agent> <task>
TASK      sarsi do <agent> "<goal>" [--tool T] [--secret S]
          sarsi tasks <agent> · plan <agent> <task> · grant <agent> <task> "<perm>"
BOARD     ask <agent> "/tasks" · "/<task>" · "/new <goal>" · "/archived"
          "/edit <task> <n> <criterion>" · "/goal <task> <text>"
          "/guided <task> <instruction>" · "/interact <task>" · "/history <task>"
RUN       sarsi run <agent> <task> · operate · supervise [--passes N --interval S]
          # the order: do → run → supervise (collect) → grant → release → supervise
VERDICT   sarsi check <agent> <task> --evidence "…" [--engine claude]
OUTWARD   sarsi send <agent> --kind mail|post … · sarsi submit <agent> form.json
VAULT     sarsi vault list · put <name> · policy <agent> <secret> <act> --allow …
SELF      ask <agent> "self model" · "improve yourself" · "yes" / "no"
GATEWAY   sarsi gateway [--passes N]        # poll every agent's bot
```

## 11. Who is driving

| | who | beats |
|---|---|---|
| 1 | **you**, in Interact | everything — the worker stands down entirely |
| 2 | **you**, guiding (`sarsi guide`, `/guided`) | the worker's own steering |
| 3 | the **worker**, guiding and steering | its own automatic composer |

Your guidance goes through even while you hold the wheel — it is your word on
your own session. The worker's does not.

## 12. Honest limits

- **`sarsi-worker`, `work` and `abraham` have run live end to end.** The other
  four assign, get their own governed session and are handed the plan — but
  through a stand-in runtime, not four more live sessions.
- **The A0 planning drop is confirmed live**: a session planning at `A0` left
  `plan0.md` and nothing else in its folder, where the same shape at `A1` had
  written its artefact during planning. Release raises a running session
  without restarting it.
- **No transmitter has run against a live service.** Mail, post and submit are
  all exercised against fakes; the endpoint shapes are unverified.
- **`AN` knows one gate** — the folder-trust prompt. Any command-approval prompt
  stops and waits for you, which is safe and means a task needing to run code
  will pause until you attach.
- **Plans are drafted deterministically.** A model writes the *instructions*;
  it does not yet write the plan.
- **Secrets reach a session through its environment** — the right shape, but
  visible to anything that session later spawns.
