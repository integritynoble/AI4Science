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

## 3b. Names — every task wears one

A task gets a short **name** derived from its goal (`write fib.py …` →
`write-fib-py`), shown on boards as `<name>---task` next to
`<agent>---agent` — the `---type` suffix says what a name refers to. The
`tsk_` id stays the identity underneath (sessions and folders key on it;
the task view shows both). Names are unique per worker (`write-fib-2` when
taken) and renamable:

```
/rename gen                 # rename the task you are standing in
/rename tsk_xxxx gen        # or name one explicitly
/gen                        # a name works anywhere an id works — opens guided
```

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

- **Instructions steer, questions are answered.** An imperative line goes
  into the session *ahead of* whatever the worker's loop would have said next
  (`sent, ahead of the worker — <your words>`). A line that reads as a
  question — starts with what/why/how/is/can/status/… or ends with `?` — is
  answered from the task's record instead: state, plan, phase verdicts, and
  a note that nothing was sent. So `what is the plan of this task?` shows
  the plan; `focus on the mask convention first` steers.
- `/tsk_XXXXXXXXXX <instruction>` from anywhere does the same as a one-shot,
  without entering the mode.
- `/interact` — hands your terminal to the task's actual tmux session (the
  work itself). Steering is paused first, and the plan is marked stale —
  because once you drive by hand, the old plan's criteria may no longer
  describe the work. **Press `Ctrl-z` to come back** — a single key, bound
  for the duration of the attach and removed after (the classic `Ctrl-b d`
  also works when not nested). The attach now also works when the REPL
  itself runs inside tmux.
- `/interact --print` — prints the session's screen instead of attaching.
  **Use this when attach fails** (see §7).
- `/back` — leave guided mode.

If the task has no session yet, the view says so and gives the start
command: `ai4science sarsi run <agent> <task-id>`.

## 6. Owner acts — in the REPL, and the CLI half

Lifecycle housekeeping now has slashes. Each acts on the task you name
(id or name) or, without one, the task you are standing in:

```
/rename [task] <new name>     # the board name; the id never changes
/goal   [task] <one sentence> # change the goal — the plan is re-drafted
/stop   [task]                # close its session; resumable (state → off)
/archive [task]               # close for good — record kept, slot freed
/reopen [task]                # an archived task back on the board, stopped
```

The verbs that move work forward remain CLI (`ai4science sarsi …`) — they
gate real authority and stay on the one door that grants it:

```bash
sarsi run   sarsi-worker tsk_x    # start the governed session (A0, planning)
sarsi supervise sarsi-worker tsk_x --passes 25   # drive: gates, brief, plan, verify
sarsi grant sarsi-worker tsk_x "<permission verbatim from awaiting[]>"
sarsi release sarsi-worker tsk_x  # raise ceiling A0 → working level, live
sarsi check sarsi-worker tsk_x    # independent verdict
sarsi why   sarsi-worker tsk_x    # phase verdicts + blast radius
sarsi attention                   # everything waiting on YOU
sarsi retry / handoff …
```

The full lifecycle, in one line:
**directive → confirm (`b` picks the engine) → `run` → `supervise` →
`grant` × N → `release` → `supervise` → `check` → PASS.**

## 7. Rough edges you will actually hit

- **Getting back from `/interact`.** Since 1.1.8.dev13: press **`Ctrl-z`**
  once — you are back at the REPL, and the nested-tmux case (REPL running
  inside tmux) attaches instead of failing with exit 1. On older builds:
  `/interact --print` reads the screen without attaching, or attach from a
  second plain terminal (`tmux attach -t sarsi-worker-<last4>`,
  `Ctrl-b d` back; nested: `TMUX= tmux attach …`, `Ctrl-b Ctrl-b d`). If
  nothing attaches, the session may simply be gone —
  `ai4science sarsi tasks sarsi-worker` says what the task waits for.
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

## 9. The three test examples, driven from the REPL

`docs/TESTING_REPL_GRACE.md` proves the lifecycle with CLI commands. This
section is the same three examples as keystrokes **inside the REPL**. One
honest boundary first: the four owner verbs — `run`, `supervise`, `grant`,
`release` (and `check`) — have no slash command. Two ways to reach them
without leaving your seat:

- **Cockpit + lever box (recommended):** keep the REPL in one terminal and a
  plain shell in a second. The REPL creates, watches, and steers; the shell
  runs the four verbs.
- **One terminal:** the top-prompt chat agent (`❯`, Unified-LLM) has a shell
  tool. `/back` to the top and type, as an instruction to the *assistant*:
  `run this command and show me the output: /home/grace/sarsi-venv/bin/ai4science sarsi run sarsi-worker tsk_xxxx`
  — approve its permission menu (`1`) and it runs it for you. Works for all
  four verbs. Do this from the **top** prompt only: at `sarsi-worker ❯` the
  same sentence would be classified as a new task goal.

Setup (once, in a shell, so the test uses a throwaway state):

```bash
export SARSI_STATE_DIR=/tmp/repltest-state
/home/grace/sarsi-venv/bin/ai4science sarsi init --owner-id 1
mkdir -p /home/grace/repltest-work && cd /home/grace/repltest-work
SARSI_STATE_DIR=/tmp/repltest-state /home/grace/sarsi-venv/bin/ai4science
```

(The REPL inherits `SARSI_STATE_DIR` from the shell that launches it — that
is what keeps `/task` showing only your test board.)

### Example A — the REPL itself (100% in-REPL)

1. Folder-trust gate → `1` + Enter.
2. Banner must read `Unified-LLM · Opus 5 (anthropic)`; status bar
   `claude-opus-5`.
3. Type `Reply with exactly: OPUS5-OK` → expect `OPUS5-OK` and a
   `✶ crunched …` footer.
4. `/model` → Opus 5 first, Opus 4.8 second; Esc to leave it.

### Example B — create a task in the worker (100% in-REPL)

1. `/agents` → `1` — prompt becomes `sarsi-worker ❯`.
2. Type: `write fib.py in this folder that prints the first 10 Fibonacci numbers`
3. The confirm block appears (`backend: sarsi-pwm`). Press Enter to accept —
   expect `→ tsk_XXXXXXXXXX`. Note the id and its last 4 characters.
4. `/tasks` — the task sits there `ready`.
5. If instead you get *"I could not tell whether that is a goal"*, your
   phrasing read as a question — retype it imperatively or use
   `/do write fib.py …`.

### Example C — the full lifecycle on real Claude Code (REPL cockpit)

1. **Create on the claude engine, in the REPL:** at `sarsi-worker ❯` type
   the directive; when the confirm block shows, press **`b`** — it re-shows
   with `backend: sarsi-claude` — then Enter. `→ tsk_XXXXXXXXXX`.
2. **Start it** (shell, or ask the top-prompt agent):
   `ai4science sarsi run sarsi-worker tsk_xxxx` — a tmux session
   `sarsi-worker-<last4>` comes up running real Claude Code at ceiling A0.
3. **Let the loop drive:** `ai4science sarsi supervise sarsi-worker tsk_xxxx
   --passes 25`. Meanwhile, in the REPL: `/tsk_XXXXXXXXXX` — you're in
   guided mode; `/interact --print` shows the session's screen whenever you
   want; a typed line goes in ahead of the worker. Expect the loop to answer
   the trust gate, deliver the brief, approve the plan write, then stop at
   **awaiting-grant**.
4. **Grant + release** (shell): read `awaiting[]` from the task view or
   task.json, `sarsi grant …` once per string verbatim, then
   `sarsi release …`. Run `supervise` again for the work + verify passes.
5. **Claude Code's own 1/2/3 menus:** if the session shows
   `[blocked] user decision`, answer the menu yourself — from the REPL,
   `/tsk_xxxx` → `/interact` (or, nested in tmux, attach from the second
   terminal) and type `1`. `--print` first if you just want to see what it
   is asking.
6. **Verdict:** `sarsi check sarsi-worker tsk_xxxx` → PASS; in the REPL,
   `/tsk_xxxx` shows `verified`, and `/why tsk_xxxx` from the worker door —
   or the CLI `sarsi why` — shows the phase verdicts.
7. **Cleanup** (shell): kill `sarsi-worker-<last4>`, remove
   `/tmp/repltest-state` and `/home/grace/repltest-work`. Never touch
   `sarsi-worker-2a68` / `-f1f0`.

Companion doc: `docs/TESTING_REPL_GRACE.md` — the same lifecycle as a
verified end-to-end transcript, including the expected output at each step.
