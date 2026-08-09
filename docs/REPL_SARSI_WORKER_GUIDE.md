# Using the ai4science REPL with sarsi-worker — the owner's guide

The REPL (`ai4science`, PWM Code) is one surface with two registries behind
it: **chat specs** (who answers when you just talk — Unified-LLM, Research,
Claude, …) and **sarsi workers** (agents that hold tasks and drive governed
sessions — sarsi-worker first among them). This guide is about the worker
side: creating tasks, steering them, and stepping into their sessions,
entirely from the REPL. Every behavior below was read from the shipped code
and exercised live on grace.

A note on state: with no `SARSI_STATE_DIR` set, the REPL and CLI use the
machine's **live** registry (`~/.sarsi`) — `/task` will show every task ever
created there. For experiments, export a throwaway
`SARSI_STATE_DIR=/tmp/...` first and `sarsi init` it (see
`docs/TESTING_REPL_GRACE.md`).

## 1. The map — where you are, and how to move

| Prompt looks like | You are | Get out |
|---|---|---|
| `❯` | top — talking to the chat spec | — |
| `sarsi-worker ❯` | inside the worker (task door) | `/back` |
| `tsk_xxxx (guided) ❯` | guiding one task | `/back` |

- `/agents` — the picker, **workers first**; selecting a worker ENTERS it,
  selecting a spec switches who answers. `/sarsi-worker` enters directly.
- `/agent <name>` — switches the chat spec only (who answers at `❯`).
  Entering a worker and switching the spec are different acts.
- `/back` — leave the worker or guided mode, back to the top.

## 2. Talking to the worker — how your line is read

The worker classifies every line before anything is created:

| You type | It does |
|---|---|
| a greeting / chat | answers, creates nothing |
| a question about itself (`what tasks are you holding?`, `can you plan at A2?`) | answers from its own state |
| an instruction (`write …`, `fix …`, `add …`, `count …`) | offers a task |
| something ambiguous | says so and asks — nothing is filed |

If it answers *"I could not tell whether that is a goal…"* (you saw this),
either rephrase as an imperative or force it:

```
/do write fib.py in this folder that prints the first 10 Fibonacci numbers
```

`/do <goal>` always files a directive, no classification. The worker also
remembers the last plausible goal, so `please create the task for this` right
after stating one will offer exactly that goal — and it says out loud which
words it picked up.

## 3. The confirmation — five answers, not two

A directive produces this block, and **the next line answers it** (even a
slash is read as an answer, so don't type commands here):

```
  goal:    write fib.py …
  agent:   sarsi-worker
  backend: sarsi-pwm
  it will plan at A0 first, and stop for your grant

  create it? [Enter=yes / e=edit / p=plan / b=sarsi-claude / n=no]
```

| Key | Meaning |
|---|---|
| Enter / `y` | create the task → `→ tsk_XXXXXXXXXX` |
| `e` | edit the goal and send it again |
| `p` | **you author the plan**: create the task, write a markdown plan (phases, a `Verified when:` line each, a `## Permissions needed` section), then `ai4science sarsi plan sarsi-worker <task-id> --set-from <file>.md`. It is agreed on arrival — no session may rewrite your criteria. Permissions still need granting. |
| `b` | **switch the engine** for this task — toggles `sarsi-pwm` (PWM Code) ↔ `sarsi-claude` (real Claude Code) and re-shows the block so you can read the choice back. The backend belongs to the task, chosen here. |
| `n` | drop it — the goal is read back so you can retype it |

So to run a REPL-created task on real Claude Code: type the directive,
press `b`, read `backend: sarsi-claude`, press Enter.

## 4. Boards — `/tasks` vs `/task`

- `/tasks` — the board of the worker you are standing in (works from
  `sarsi-worker ❯`; from the top it asks the current agent's worker).
- `/task` — **every** board on the machine, all agents, all states:

```
tsk_d3f02f2a68  running   sarsi-worker  Write a file called pwm-backend-proof.md …
tsk_bd326ebfeb  ready     sarsi-worker  write a live-test GAP-TV sanity note
…
```

States you will see: `ready` (created, not started), `running` (session up or
startable), `awaiting-grant` (plan done, needs your permissions), `verified`
(passed its check), `off` (stopped, resumable), `archived` (closed for good).

## 5. One task — view, guide, interact

`/tsk_XXXXXXXXXX` (bare) shows the task and then drops you into **guided
mode** — the prompt becomes `tsk_xxxx (guided) ❯`:

- **Every line you type is steering**: it goes into the session *ahead of*
  whatever the worker's loop would have said next. You'll see
  `sent, ahead of the worker — <your words>`. The worker keeps running; your
  word just cuts the line.
- `/tsk_XXXXXXXXXX <instruction>` from anywhere does the same as a one-shot,
  without entering the mode.
- `/interact` — hands your terminal to the task's actual tmux session (the
  work itself). Steering is paused first, and the plan is marked stale —
  because once you drive by hand, the old plan's criteria may no longer
  describe the work. `Ctrl-b d` hands the terminal back.
- `/interact --print` — prints the session's screen instead of attaching.
  **Use this when attach fails** (see §7).
- `/back` — leave guided mode.

If the task has no session yet, the view says so and gives the start
command: `ai4science sarsi run <agent> <task-id>`.

## 6. What the REPL does not do — the CLI half

The REPL is the door for *creating, watching, and steering*. The owner acts
that move a task through its lifecycle live in `ai4science sarsi …`:

```bash
sarsi run   sarsi-worker tsk_x    # start the governed session (A0, planning)
sarsi supervise sarsi-worker tsk_x --passes 25   # drive: gates, brief, plan, verify
sarsi grant sarsi-worker tsk_x "<permission verbatim from awaiting[]>"
sarsi release sarsi-worker tsk_x  # raise ceiling A0 → working level, live
sarsi check sarsi-worker tsk_x    # independent verdict
sarsi why   sarsi-worker tsk_x    # phase verdicts + blast radius
sarsi attention                   # everything waiting on YOU
sarsi stop / archive / reopen / retry / goal / handoff …
```

The full lifecycle, in one line:
**directive → confirm (`b` picks the engine) → `run` → `supervise` →
`grant` × N → `release` → `supervise` → `check` → PASS.**

## 7. Rough edges you will actually hit

- **`/interact` fails with "tmux would not attach … (exit 1)".** Almost
  always you are running the REPL *inside* tmux — tmux refuses to nest.
  Three ways through: `/interact --print` (read the screen without
  attaching); attach from a second, plain terminal
  (`tmux attach -t sarsi-worker-<last4>`); or force the nest from a shell
  with `TMUX= tmux attach -t <name>`. If none work, the session may simply
  be gone — `ai4science sarsi tasks sarsi-worker` will say what the task is
  waiting for.
- **A pending confirmation eats the next line.** By design the `create it?`
  question owns whatever you type next — answer it (`n` is always safe)
  before typing commands.
- **Claude Code's own confirm menus** ("Do you want to create X? 1/2/3") have
  no supervise rule yet; the loop abstains and the session reports
  `[blocked] user decision`. Answer them yourself via `/interact` (or tmux
  attach), typing `1`/`2`.
- **Old sessions on the live state.** `tmux ls` on grace shows long-lived
  `sarsi-worker-2a68` / `-f1f0` sessions tied to old live tasks. Look with
  `/interact --print` if you're curious — don't kill them and don't type
  into them casually.

## 8. Sixty-second smoke test

```bash
export SARSI_STATE_DIR=/tmp/replguide-state
/home/grace/sarsi-venv/bin/ai4science sarsi init --owner-id 1
mkdir -p /home/grace/replguide-work && cd /home/grace/replguide-work
/home/grace/sarsi-venv/bin/ai4science          # trust folder: 1
```

In the REPL: `/agents` → `1` (enter sarsi-worker) → type
`write hello.txt containing exactly the word hello` → `b` (pick
sarsi-claude, if you want real Claude Code) → Enter → `/tasks` → `/back` →
`/exit`. Then `run` / `supervise` / `grant` / `release` / `check` per §6,
and clean up:

```bash
tmux kill-session -t sarsi-worker-<last4> 2>/dev/null
rm -rf /tmp/replguide-state /home/grace/replguide-work
```

Companion doc: `docs/TESTING_REPL_GRACE.md` — the same lifecycle as a
verified end-to-end transcript, including the expected output at each step.
