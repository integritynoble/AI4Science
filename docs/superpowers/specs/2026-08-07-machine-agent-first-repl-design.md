# Machine-agent-first REPL — design

**Status: design, 2026-08-07. Nothing below is built.**

A user entering `ai4science` today can be told that workers exist and given no
way to reach one. This is the live transcript that produced this document:

```
❯ /agent sarsi-worker
[agents] unknown agent 'sarsi-worker'; /agent to list
❯ /do write a gap-tv algorithm for cassi
[harness] unified-LLM has no sarsi worker — it answers here instead of delegating.
  workers with a task board: abraham, computational-imaging, funding, jobs,
  sarsi-machine, sarsi-worker, social, work
```

The REPL names eight workers and offers no route to any of them. `/do` resolves
its worker by the *chat agent's* name, and no chat spec is called
`sarsi-worker`, so no sequence of existing commands reaches it.

The path a user should have: **say what you want → be told which worker it
belongs to → enter that worker → hand it a goal → get a task → enter the task →
steer it, or take the wheel in its session.**

---

## 1. The mode model

Three levels, and **the prompt always names where the words are going.** That
label is not decoration: it is what makes "plain text becomes a goal"
acceptable. A mode that does not show itself is a trap.

| level | prompt | plain text goes to | entered by |
|---|---|---|---|
| **top** | `❯` | the chat agent, as today | start, or `/back` |
| **agent** | `sarsi-worker ❯` | a goal, shown for confirmation | `/sarsi-worker` |
| **task** | `tsk_ab12cd34 (guided) ❯` | a guided instruction, ahead of the worker | `/tsk_ab12cd34` |

`/back` pops one level. `/exit` leaves the REPL from any depth — a user wanting
out should not have to know how deep they are.

### Resolving `/<name>`

```
roster agent            → enter agent mode
chat spec only          → switch the chat agent, no mode      (/research)
both                    → enter agent mode, and say the other exists
task id                 → enter task mode
otherwise               → refused, with a near-miss suggestion   (built)
```

**This is what settles the two agents called `work`.** `/<name>` addresses the
thing that *holds tasks*; `/agent <name>` addresses the thing that *answers
here*. The chat spec `work` writes you a GAP-TV implementation in your session;
the roster agent `work` drafts a plan and lets `sarsi-claude` agree it first.
Neither is wrong, and picking one silently is how the confusion started.

### Two invariants

1. **Entering costs nothing.** `/sarsi-worker` creates no task, starts no
   session and spends nothing. Only the confirmation does.
2. **Mode never widens authority.** Task mode grants nothing. Guided
   instructions take the path `sarsi guide` already uses; the ceiling and the
   grants are untouched.

---

## 2. Components and data flow

One new module, `ai4science/harness/console.py`, with one job: **given the mode
and a line, say what should happen.** It never prints, never calls a model and
never touches tmux, so all of it is testable without a terminal.

```python
Mode(kind="top"|"agent"|"task", name="", pending=None)

console.prompt_label(mode) -> str
console.route(line, mode, deps) -> (Action, Mode)   # pure; returns a new Mode
```

`repl.py` is the only thing that performs an action:

| Action | `repl.py` does |
|---|---|
| `answer(text, note)` | the normal turn, plus the recommendation line if any |
| `say(text)` | print it |
| `confirm(goal, agent)` | print the block; the returned Mode carries `pending` |
| `create(goal, agent)` | `tsk.create` + `attach_plan`; print the id |
| `guide(task, text)` | `ses.guide(...)` |
| `attach(session, task)` | pause the worker, release the terminal, attach, restore |
| `enter(mode)` / `leave()` | swap the prompt |

### The confirmation is two calls, not a blocking prompt

Line 1 returns `confirm(...)` and puts the goal in `mode.pending`. Line 2 is
read against that pending goal: empty or `y` creates it, `e` reopens it for
editing, anything else drops it. Two ordinary calls, so both are testable — and
Ctrl-C between them leaves no half-made task.

### Dependencies are injected

`deps` carries `resolve_name`, `roster`, `find_task`, `suggest` and `attach`.
Tests pass fakes; the REPL passes the real ones.

---

## 3. The recommendation, and error handling

**At the top level a line is answered as it is today, and a one-line note is
printed underneath** when `triage.suggest` returns a candidate:

```
───
sarsi-worker could take this as a task instead (cassi, algorithm)
— /sarsi-worker to enter it
```

`triage.suggest` creates nothing and is already built. When it returns a tie or
nothing, **no note is printed** — a router that guesses is worse than one that
is quiet.

Every failure in this path returns a string; nothing raises. The REPL is what
the owner is standing in, and dropping it to report a routing problem trades a
small failure for a large one. Concretely:

| when | what the user sees |
|---|---|
| no sarsi registry on the machine | "no registry yet — `ai4science sarsi init`" |
| the task id no longer exists | "not a task on this machine — `/task` lists them" |
| the session is gone | task mode still works; `/interact` says there is no session and how to start one |
| `guide` fails | the reason, and the mode is kept |

---

## 4. `/interact` — the one part that cannot be honestly unit-tested

From task mode, `/interact` pauses the worker, hands the terminal to tmux, and
restores the REPL when the user detaches with `Ctrl-b d`. The worker stays
paused afterwards; `/resume` hands it back.

The risk is real and worth stating plainly: **prompt_toolkit must release the
terminal, a child process takes it, and the app is restored on return.** If that
goes wrong the failure mode is an unusable terminal, and no unit test will catch
it.

Two mitigations:

* **the attach is an injected callable**, so tests assert *"it paused the worker
  and asked to attach `sarsi-worker-cd34`"* without attaching anything;
* **`/interact --print` always exists** and only prints the `tmux attach` line,
  so there is a way through on any terminal where the hand-off misbehaves.

---

## 5. Testing

Everything except the hand-off is a pure function over `(line, mode)`.

| what | how |
|---|---|
| prompt labels | one assertion per level |
| `/<name>` resolution | roster **injected**, not read from the machine — a test that passes because of whose registry is on the box is testing the box |
| the confirmation | two calls: `confirm` then `y` / `e` / `n` / empty |
| entering costs nothing | after `enter`, assert no task was created and no session started |
| the recommendation | a tie prints nothing; a clear winner prints one line |
| `/interact` | the injected attach records `(session, paused)`; assert the worker was paused **before** the attach |
| the terminal hand-off | **not unit-tested.** Verified live as grace, once, and recorded here as such |

---

## 6. What this does not do

* It does not move planning. The machine agent produces a **goal and scope**;
  `plan0.md` is still drafted by the session at A0 and collected by `supervise`.
  Owner-authored plans stay the exception they are today.
* It does not change any ceiling, grant or gate.
* It does not touch the Telegram or CLI surfaces. `chat.py`'s board keeps its
  verbs; this is a REPL-only layer.

---

## 7. `/agents` is the switcher

`/agent` and `/mode` both switch today. **`/agents`** becomes the one that
switches — it lists and switches in the same breath, which is what someone
typing it expects. `/agent` and `/mode` stay as aliases: removing a command
people already use, to make a naming point, is a cost paid by the user for the
designer's tidiness.

---

## 8. `sarsi-pwm` — a second session backend, and the default

`sarsi-claude` opens a tmux session running Claude Code. **`sarsi-pwm` opens a
tmux session running ai4science** — any LLM, and GPU-capable — and is the
**default** for new tasks.

**It needs no change to the supervision loop.** The loop reads four things: the
gate shape, the `❯` prompt line, the busy marker and the folder-trust gate. The
first two are already identical in both TUIs. The other two diverge in *string
only*, and only in the full-screen renderer:

| | today | parity |
|---|---|---|
| `tui.py:1012` | `esc to stop` | `esc to interrupt` |
| `chat.py:113` | "Quick safety check: is this a **folder** you created or trust" | "Is this a **project** you created or one you trust" |

`chat.py:489` already says `esc to interrupt`, so the inline renderer is
already at parity and the full-screen one drifted from it.

> **The loop does not learn a second dialect; the TUI stops speaking one.** One
> set of patterns, because there is one interface. Making this a special case in
> the loop would have bought a second thing to keep in step forever, in exchange
> for two strings.

`attended` stays as a mechanism — it is what protects any future backend nobody
has verified. `sarsi-pwm` graduates out of it by having its patterns checked
live, exactly as `claude-code` did, and `DRIVABLE_SPECS` gains it only after
that check passes on a real session.

### Choosing between them

| where | how |
|---|---|
| at creation | the confirm block names the backend; one key flips it |
| an existing task | `/tsk_ab12cd34 sarsi-claude` · `/tsk_ab12cd34 sarsi-pwm` |
| in words | inside `sarsi-worker ❯`, say it; the worker proposes and you answer yes |

```
sarsi-worker ❯ write a GAP-TV algorithm for CASSI

  goal:    write a GAP-TV algorithm for CASSI
  agent:   sarsi-worker
  backend: sarsi-pwm  (any LLM + GPU)      [c = sarsi-claude]
  ceiling: A1 — it will plan at A0 first

  create it? [Enter=yes / e=edit / c=claude / n=no]
```

Switching an existing task's backend **does not migrate a running session**: it
takes effect on the next `sarsi run`, and says so. Moving a live session between
engines mid-plan would silently change who wrote what, and the plan record is
the one thing that must stay attributable.

---

## 9. Settled — the roster change is a WEB change

Raised while this was written and first misread as a change to the CLI agent
registry. It is not: it is the catalogue on
`test.physicsworldmodel.org/agents`, served from `pwm_nonprofit`
(`routers/pages.py`, `_AGENTS_DATA`).

That distinction avoided a serious mistake. **`claude-code` cannot be deleted
from the CLI.** It is the spec `sarsi-worker` runs on (`registry.py:278`), the
spec every market-installed agent is given (`market.py:276`), and half of
`DRIVABLE_SPECS` — what the whole supervision loop keys on. Removing the *card*
is safe; removing the *spec* would break the path this document is built around.

The catalogue change:

* **Unified LLM → PWM code.** Two axes, and they are independent — which is the
  whole point of the rename:

  | | what it can use |
  |---|---|
  | **the model** | any LLM the exchange gateway fronts — Claude, GPT, Gemini, a local one. Not one vendor's |
  | **the compute** | any provider on the PWM compute mesh — a GPU server, a high-CPU box, or the machine it is standing on |

  The cards it replaces each fixed one axis: `claude-code` fixed the model,
  `claude-code-gpu` fixed the model and added compute, and the same for the two
  codex cards. PWM code fixes neither, so four cards collapse into one without
  losing a capability — that is *why* the four can go, rather than a
  coincidence that makes it convenient.

  **How "any LLM" is actually reached: the comparegpt method.** Not by building
  a provider integration per vendor. `comparegpt-product/main/openai_bridge.py`
  (184 lines) is the pattern — it speaks the **standard OpenAI chat-completions
  wire protocol** on the front and translates to the ai4science gateway's JSONL
  streaming on the back, so a client using a subscription reaches models it has
  no code for. The gateway decides which provider serves the call; the client
  exports a base URL and a token.

  | | |
  |---|---|
  | client side | one base-URL export, as the Claude Code card already documents (`ANTHROPIC_BASE_URL` → the PWM gateway) |
  | server side | the gateway fronts Claude, Google and OpenAI-family models, on subscriptions or keys |
  | cost of a new provider | a gateway change, **not** a PWM-code change |

  **Which model reaches which provider, decided:**

  | family | how |
  |---|---|
  | Claude | the PWM exchange gateway, as the Claude Code card documents |
  | ChatGPT / OpenAI | **the codex subscription**, as `openai_bridge.py` already does — a subscription, not an API key |
  | Google | the same gateway route |

  The bridge exists precisely to call OpenAI models *"via the ChatGPT Plus
  subscription (codex) rather than an API key"* — its own docstring. So the
  answer to "which of the famous models can PWM code reach" is: the ones the
  gateway fronts, on subscriptions where a subscription exists.

  > **This is why "any LLM" is one line in a shell profile rather than N
  > integrations**, and why the four cards collapse cleanly: they differed in
  > which endpoint they were pinned to, and PWM code is pinned to none.

  > **The card must say both.** "Uses any LLM" alone reads as a model picker and
  > leaves a reader who needs a GPU thinking they still want the `+ GPU` card
  > that is no longer there.
* **remove** the Claude Code, Claude Code + GPU, Codex and Codex + GPU cards.
* **remove** the `research` tier (the two SARSI cards) and the `general` tier.
* **flatten**: one group called **Agents**, plus the existing **Tools**. PWM
  code joins the agents.
* `research` and `paper-review` are not named for removal, so they move into the
  flattened list rather than being dropped — a judgement call, and one word
  reverses it.

**PWM code inherits Claude Code's how-to-use, step for step.** That card is the
only one on the page carrying a `how_to_use` block — install, generate a `pwm_`
key, point the tool at the PWM gateway, use it normally — and it is what made
Claude Code the obvious thing to start with. PWM code is replacing it on the
page, so it has to answer the same four questions in the same order:

| step | Claude Code today | PWM code |
|---|---|---|
| 1 | install Claude Code from claude.ai/code | `pip install pwm-agent-unified` — or the one-line installer |
| 2 | generate a `pwm_` key in Settings → API Keys | unchanged |
| 3 | export `ANTHROPIC_BASE_URL` / `ANTHROPIC_AUTH_TOKEN` at the PWM gateway | the same, and **any** provider the gateway fronts — not Anthropic alone |
| 4 | run `claude` as usual; the balance covers it; `/exchange` shows per-call logs | run `pwm-code`; identical wording |

> A card that says only *what an agent is* leaves the reader with nothing to do.
> Removing the one card that told them how, and not carrying its steps across,
> would make the page worse in the exact way the removal was meant to improve.

---

## 10. This is three pieces, not one

The self-review caught it: this document describes three deliverables, in two
repositories, with different risks. One implementation plan covering all three
would be a plan whose failure modes have nothing to do with each other.

| # | piece | where | depends on |
|---|---|---|---|
| **1** | the agents-page catalogue — rename, removals, flatten, how-to-use | `pwm_nonprofit` | nothing |
| **2** | the REPL: modes, `/<name>`, confirm, `/task`, `/agents`, `/interact` | `AI4Science` `console.py` + `repl.py` | nothing |
| **3** | `sarsi-pwm` as a backend and the default | `AI4Science` sessions + two parity strings | piece 2's confirm block, to be chosen at creation |

**Current priority: make `sarsi-worker` work well.** That is piece **2** — the
REPL is the only surface where reaching `sarsi-worker` is currently impossible,
and the reported failure is a user being shown eight workers and given no route
to one. Pieces 1 and 3 wait.

`sarsi-pwm` (piece 3) is explicitly *not* the thing to chase first: today
`sarsi-worker` runs on `sarsi-claude`, that path is supervised end to end, and
it has been verified live — plan collected, three grants, released, worked,
judged. Making the default backend a second one before the first is comfortable
to use would be widening the thing that already works instead of finishing it.

**Order when the others come: 1, then 2, then 3.** The catalogue is independent and the smallest; the
REPL is where the reported failure lives; `sarsi-pwm` is last because its
confirm-time choice needs the confirm block, and because its parity change wants
a live check on a real session before `DRIVABLE_SPECS` grows.

Each gets its own plan. This document is the shared design they all refer back
to, not a single work item.

### Out of scope for all three: exercising a compute provider

**No GPU-provider or CPU-provider function is to be tested as part of this
work.** PWM code is *described* as able to use any compute provider, and
`sarsi-pwm` opens a session that could dispatch to one — but leasing compute,
dispatching a job to a GPU server or a high-CPU box, and settling what it cost
are a separate system with their own money and their own failure modes.

What that means concretely for each piece:

| piece | tested | not tested |
|---|---|---|
| 1 catalogue | the card says PWM code works with any LLM **and** any compute provider | that it does — no provider is contacted |
| 2 REPL | modes, resolution, confirm, guide, attach | nothing compute-related is reachable from here |
| 3 `sarsi-pwm` | a session starts, the loop reads it, a task runs on this machine | no lease, no dispatch, no remote execution, no settlement |

> **A capability stated on a page is a claim; a capability exercised in a test
> is a result.** Keeping them apart here is deliberate: the page may say what
> PWM code is for, and this work does not get to claim the compute half has
> been shown to work. When it is tested, that is its own piece with its own
> evidence.
