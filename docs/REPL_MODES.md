# REPL modes — using `sarsi-worker` from inside `ai4science`

**Status: on `feat/repl-modes`, not yet merged.** Everything here was exercised
live on a second user account on 2026-08-07; where something does not work, it
says so on the line rather than in a footnote at the end.

Before this, the REPL would list eight workers and give you no way to reach one:

```
❯ /agent sarsi-worker
[agents] unknown agent 'sarsi-worker'; /agent to list
❯ /do write a gap-tv algorithm for cassi
[harness] unified-LLM has no sarsi worker — it answers here instead of delegating.
  workers with a task board: abraham, computational-imaging, funding, jobs,
  sarsi-machine, sarsi-worker, social, work
```

`/do` looks up its worker by the **chat agent's** name, and no chat spec is
called `sarsi-worker`. The name had nowhere to go.

---

## 1. The distinction everything rests on

| | what it does with your request |
|---|---|
| a **chat agent** — PWM code (`unified-LLM`), Research, `work` | **answers you, here.** Ask for a GAP-TV implementation and it writes one in your session |
| a **sarsi worker** — `sarsi-worker`, `computational-imaging` | **delegates.** Drafts a plan, `sarsi-claude` agrees it, you grant what it declared, and it works under supervision |

You land in **PWM code** — it is what answers at `❯`. You never *become* a
worker; you enter it and hand it work.

## 2. Three levels

| where you are | prompt | plain text does |
|---|---|---|
| top | `❯` | asks the chat agent, as always |
| agent | `sarsi-worker ❯` | proposes a **goal**, and waits for you |
| task | `tsk_… (guided) ❯` | **steers** that task, ahead of the worker |

`/back` pops one level. `/exit` leaves the REPL from any depth — wanting out
should not require knowing how deep you are.

## 3. A session that actually happened

Transcript from the live run, trimmed:

```
❯ /sarsi-worker
now addressing sarsi-worker

sarsi-worker ❯ count the md files under /home/grace/sarsi-state-check
  goal:   count the md files under /home/grace/sarsi-state-check
  agent:  sarsi-worker
  it will plan at A0 first, and stop for your grant
  create it? [Enter=yes / e=edit / n=no]

sarsi-worker ❯                       ← Enter
→ tsk_593ea3762e

sarsi-worker ❯ /tsk_593ea3762e
guided on tsk_593ea3762e

tsk_593ea3762e (guided) ❯ /interact --print
  tmux attach -t sarsi-worker-762e

tsk_593ea3762e (guided) ❯ /back
❯
```

> ### Enter does mean yes
>
> Pressing Enter at the confirmation used to do nothing — the loop discarded
> an empty line ahead of the routing that reads it, so `[Enter=yes]` promised
> an interaction the full-screen TUI could not perform, and `y` was the only
> working answer. That pre-filter has been removed: an empty line now reaches
> `console.route` like any other, which already treated it as `yes` — the unit
> test always passed because it called the router directly and never crossed
> the loop's own pre-filter, which is exactly how this went unnoticed as long
> as it did. Verified live, in the full-screen TUI, not only by unit test.
> `y` still works too.

> ### The input box shows a bare `❯`
>
> The mode label appears in the transcript, one line above where you type — the
> box itself always shows `❯`. So the level you are standing at is visible, but
> not at the cursor. Read the line above the box before typing a sentence in
> agent mode, because there plain text proposes a task rather than asking a
> question.

## 4. What each mode does with plain text

**Top level** — answered by PWM code, as always. A one-line note may appear
underneath naming a worker that could take the job instead. When the router
cannot pick a clear winner it prints nothing: a router that guesses is worse
than one that is quiet.

**Agent mode** — your line becomes a *proposed goal*. Nothing is created until
you answer. `y` creates it, `e` reopens it for editing, and anything else drops
it — **including a slash**, which is read as "no" rather than as a command, so a
stray `/back` mid-confirmation cannot quietly discard a goal by a path that
never tells you.

The confirmation exists because a task starts a session and spends PWM. A
sentence must not become one by accident.

**Task mode** — your line is sent to the running session *ahead of* whatever the
worker would have said next. Steering does not move you; you stay in task mode.

## 5. The two ways into a running task

```
/tsk_…  <instruction>     guided — steer from outside, the worker keeps running
/interact                 the tmux session itself; Ctrl-b d comes back
/interact --print         just prints the `tmux attach` line, attaches nothing
```

`--print` exists because the real attach releases your terminal to a child
process, and that is the one part of this that no test can honestly cover. If
the hand-off misbehaves on your terminal, that flag is the way through.

> **Known, and honest:** the successful attach-and-return has **not** been
> demonstrated yet. The live test ran inside tmux, so `/interact` hit tmux's
> nesting guard. What that did prove is that a failed attach is handled — the
> REPL printed the reason, stayed alive, and kept its mode. The failure hint it
> prints ("is it still running?") is misleading in that case: the session was
> running, and nesting was the cause.

## 6. Entering costs nothing

`/sarsi-worker` and `/tsk_…` create no task, start no session and spend nothing.
Only the confirmation creates. And mode never widens authority: task mode grants
nothing, and guided instructions take the same path `sarsi guide` already uses,
with the ceiling and the grants untouched.

## 7. Commands

```
/agents                    list the chat agents, and switch      (/agent, /mode are aliases)
/subagents                 the nested delegation types
/task                      every task on the machine, whoever holds it
/<worker>                  enter that worker
/<worker> do <goal>        one-shot, without entering
/<worker> tasks            that worker's board
/<task-id>                 enter the task, guided
/<task-id> <instruction>   steer it
/back                      up one level
```

An unrecognised slash is **refused, not forwarded to the model** — `/agnet`
answers *"not a command… did you mean /agent or /agents?"*. A sentence that
merely begins with a path is still a sentence: `/home/grace/x is missing`
reaches the model unchanged.

## 8. From here to a verdict

Entering and creating is the start. The rest is unchanged:

```bash
ai4science sarsi run       sarsi-worker <task>
ai4science sarsi supervise sarsi-worker <task> --passes 20 --interval 12
ai4science sarsi grant     sarsi-worker <task> "<each permission it names>"
ai4science sarsi release   sarsi-worker <task>
ai4science sarsi supervise sarsi-worker <task>
```

**Give collection time.** Until `supervise` attaches the plan there is nothing
to grant and nothing to release, and the task keeps reading `planning`. That is
collection not having happened yet, not a failure — see
[`SARSI_AGENTS_GUIDE.md`](SARSI_AGENTS_GUIDE.md) §5.
