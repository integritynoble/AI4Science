# Using the seven sarsi agents

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

## 2. The seven

| Agent | Use it for | What stops at you |
|---|---|---|
| **`sarsi-machine`** | "who should do this?", the fleet view | — it executes nothing |
| **`sarsi-worker`** | anything with no better home | — |
| **`work`** | your job: code, data, the tools that job needs | **sending** an email |
| **`social`** | one daily read; drafts for X / LinkedIn / Substack | **posting** |
| **`funding`** | grant and programme applications | **submitting** |
| **`jobs`** | CV, and filling in application sites | **submitting** |
| **`abraham`** | your own life, not your work | **anything outward** |

Two you should understand before using:

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
ai4science sarsi ask work "…"        # CLI
# …or message that agent's bot
```

A surface is a door, not a scope. What you say on one is visible on the other,
and the agent will not re-ask something you already answered elsewhere.

## 4. Designing a task

This is the part that decides whether any of it works.

```bash
ai4science sarsi do work "<goal>" [--tool matlab] [--secret mail.read]
```

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
ai4science sarsi ask work "/<task-id>"                    # read the plan
ai4science sarsi ask work "/edit <task-id> 1 export.csv exists and has 1,204 rows"
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
ai4science sarsi tasks work                                # state + what it waits on
ai4science sarsi grant work <task-id> "read secret mail.read"
```

A grant answers the permission it names and no other.

## 5. From task to `sarsi-claude` to Claude Code

```bash
ai4science sarsi run work <task-id>
```

What happens, in order:

1. **the vault is asked** for each declared secret — for this one use. A denial
   stops the task *before* any session exists, and names the secret.
2. **a tmux session starts** in the task's own folder, named for the agent,
   with the A0–A3 governance hook wired at that agent's ceiling.
3. **the plan goes down, not the wish.** The kickoff names `plan0.md` and the
   earliest incomplete phase, and carries none of your conversation — that is
   what keeps the session's context bounded.

Then supervise it:

```bash
ai4science sarsi supervise work <task-id> --passes 8 --interval 25
```

One pass, in this order — and the order is the point:

| | | |
|---|---|---|
| **V** | is the goal already met? | verification sits **above** the typing steps |
| **AN** | a gate on screen? | answers only gates it recognises; anything else waits for you |
| — | mid-turn? | leave it alone |
| **SP** | a prompt stranded at the `❯`? | submits it **verbatim**, retypes nothing |
| **S** | otherwise | composes **one** instruction and types it |

The composer is given the plan, the phase by name, the verifier's last reason,
**what you said**, its own last five prompts (*do not repeat what failed*), and
any failure signature on screen.

## 6. Getting into a running session

```bash
ai4science sarsi ask work "/<task-id>"
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
ai4science sarsi check work <task-id> --evidence "$(…)" --engine claude
```

Three answers, and the third is why you can trust the other two:

- **PASS** — a judge saw the evidence and every criterion was met.
- **FAIL** — a judge saw it and they were not. The reason is fed back into the
  session as the next instruction.
- **UNVERIFIED** — **nobody judged it.** No verifier reachable, an unreadable
  answer, or no visible evidence. Never a pass, and nothing is steered on it.

Answers state their authority: *verified*, *recorded*, *not judged*, *I think* —
and name the session. In a fleet, "it worked" is an incomplete sentence.

## 8. What leaves the machine

Nothing, without you:

```bash
ai4science sarsi send work --kind mail --to bob@x.com --subject "…" --body "…"
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
ai4science sarsi ask work "self model"
ai4science sarsi ask work "improve yourself"      # proposes, citing real numbers
ai4science sarsi ask work "yes"                   # only you can sign it
```

Every line of the self-model carries its source, `verified` counts only what the
verifier granted, and an unmeasured ability answers *unverified* rather than
being guessed at. An agent can never promote its own candidate, raise its own
ceiling, or widen any authority.

## 10. Command reference

```
SETUP     sarsi init --owner-id <id> · agents [--bindings] · set-token <agent> <token>
TALK      sarsi ask <agent> "<text>"        (or that agent's bot)
TASK      sarsi do <agent> "<goal>" [--tool T] [--secret S]
          sarsi tasks <agent> · plan <agent> <task> · grant <agent> <task> "<perm>"
BOARD     ask <agent> "/tasks" · "/<task>" · "/edit <task> <n> <criterion>"
          "/guided <task> <instruction>" · "/interact <task>" · "/history <task>"
RUN       sarsi run <agent> <task> · operate · supervise [--passes N]
VERDICT   sarsi check <agent> <task> --evidence "…" [--engine claude]
OUTWARD   sarsi send <agent> --kind mail|post … · sarsi submit <agent> form.json
VAULT     sarsi vault list · put <name> · policy <agent> <secret> <act> --allow …
SELF      ask <agent> "self model" · "improve yourself" · "yes" / "no"
GATEWAY   sarsi gateway [--passes N]        # poll every agent's bot
```

## 11. Honest limits

- **`sarsi-worker` is the only agent proven live end to end.** The other five
  workers assign, get their own governed session and are handed the plan — but
  through a stand-in runtime, not five more live sessions.
- **No transmitter has run against a live service.** Mail, post and submit are
  all exercised against fakes; the endpoint shapes are unverified.
- **`AN` knows one gate** — the folder-trust prompt. Any command-approval prompt
  stops and waits for you, which is safe and means a task needing to run code
  will pause until you attach.
- **Plans are drafted deterministically.** A model writes the *instructions*;
  it does not yet write the plan.
- **Secrets reach a session through its environment** — the right shape, but
  visible to anything that session later spawns.
