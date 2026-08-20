# AI4Science — sarsi-worker + sarsi-claude usage

Practical reference for running tasks through sarsi-worker using real Claude Code
(`sarsi-claude`) as the backend. Commands are as shipped and exercised live.

---

## 1. Start the REPL

```bash
ai4science
```

Run this as the `ai4science` user (or any sub-user). The REPL opens with a
folder-trust gate — answer `1` to proceed.

The prompt starts at `❯`. The banner line shows the current chat spec
(`Unified-LLM · Opus 5` or similar).

---

## 2. Enter sarsi-worker

```
❯ /sarsi-worker
```

Or use the picker:

```
❯ /agents
```

Select `sarsi-worker` from the list (workers appear first). The prompt
changes:

```
sarsi-worker ❯
```

To leave, type `/back` at any time.

---

## 3. Create a task on sarsi-claude

Type any imperative sentence — the worker classifies it as a goal and
shows a confirmation block:

```
sarsi-worker ❯ write fib.py that prints the first 10 Fibonacci numbers
```

**The confirmation block:**

```
  goal:    write fib.py that prints the first 10 Fibonacci numbers
  agent:   sarsi-worker
  backend: sarsi-ai4sci
  it will plan at A0 first, and stop for your grant

  create it? [Enter=yes / e=edit / p=plan / b=sarsi-claude / n=no]
```

The default backend is `sarsi-ai4sci`. To use real Claude Code, **press `b`**
before creating:

```
b
```

The block re-displays with `backend: sarsi-claude`. Then press Enter:

```
→ tsk_3e8f2a91b4
```

Note the last 4 characters of the id (`b4` here) — they identify the tmux
session.

### Confirmation keys

| Key | What happens |
|-----|--------------|
| Enter / `y` | Create the task |
| `b` | Toggle backend: `sarsi-ai4sci` ↔ `sarsi-claude` |
| `e` | Edit the goal, start over |
| `p` | Create the task and then set your own plan file (see §8) |
| `n` | Drop it — goal is echoed so you can retype |

### Forcing a directive

If the worker responds with *"I could not tell whether that is a goal"*,
use `/do` to bypass classification:

```
sarsi-worker ❯ /do write fib.py that prints the first 10 Fibonacci numbers
```

`/do` always files a goal. Then press `b` + Enter as above.

---

## 4. The board

```
sarsi-worker ❯ /tasks
```

Shows every task held by this worker:

```
write-fib-py---task   ready     sarsi-worker---agent   write fib.py …
run-analysis---task   running   sarsi-worker---agent   run analysis on dataset
```

`/task` (no `s`) shows ALL tasks on the machine across all agents and states.

### Task states

| State | Meaning |
|-------|---------|
| `ready` | Created, not started |
| `running` | Session is up (or startable) |
| `awaiting-grant` | Plan done, waiting for permission grants |
| `verified` | Passed its check (PASS) |
| `off` | Stopped, resumable |
| `archived` | Closed for good — record kept |

---

## 5. Run the task

Leave the REPL or open a second terminal. Run:

```bash
ai4science sarsi run sarsi-worker tsk_3e8f2a91b4
```

This starts a tmux session named `sarsi-worker-<last4>` (e.g.
`sarsi-worker-91b4`) running real Claude Code at planning ceiling A0.

The session answers the folder-trust gate, delivers the brief, and
writes a plan. It then stops at **`awaiting-grant`** — Claude Code needs
permission to write files.

---

## 6. Drive it to done with supervise

```bash
ai4science sarsi supervise sarsi-worker tsk_3e8f2a91b4 --passes 25
```

`supervise` runs the automation loop: answers gates, delivers the brief,
approves the plan, then stops at `awaiting-grant` for you to grant
permissions.

While it runs, you can watch from the REPL:

```
sarsi-worker ❯ /tsk_3e8f2a91b4
```

This enters **guided mode** (prompt: `tsk_3e8f2a91b4 (guided) ❯`).

```
tsk_3e8f2a91b4 (guided) ❯ /interact --print
```

Prints the current screen of the Claude Code session. Useful when you
can't attach.

```
tsk_3e8f2a91b4 (guided) ❯ /interact
```

Hands your terminal to the tmux session directly. Press `Ctrl-z` to
return to the REPL.

An imperative line in guided mode is sent ahead of the worker's loop:

```
tsk_3e8f2a91b4 (guided) ❯ focus on the edge case first
```

A question is answered from the task record without touching the session:

```
tsk_3e8f2a91b4 (guided) ❯ what is the current plan?
```

---

## 7. Grant permissions and release

When the task reaches `awaiting-grant`, read what it needs:

```bash
ai4science sarsi tasks sarsi-worker
```

The `awaiting[]` field lists the exact permission strings. Grant each one
verbatim:

```bash
ai4science sarsi grant sarsi-worker tsk_3e8f2a91b4 "write files in /home/ai4science/work"
```

Then raise the ceiling so the work phase can run:

```bash
ai4science sarsi release sarsi-worker tsk_3e8f2a91b4
```

Run `supervise` again to drive the work + verify passes:

```bash
ai4science sarsi supervise sarsi-worker tsk_3e8f2a91b4 --passes 25
```

---

## 8. Check and verify

```bash
ai4science sarsi check sarsi-worker tsk_3e8f2a91b4
```

Returns `PASS`, `FAIL`, or `UNVERIFIED` with a reason.

From the REPL:

```
sarsi-worker ❯ /why tsk_3e8f2a91b4
```

Shows goal, criteria, and the last verdict — phase by phase.

If `check` returns `FAIL`, the loop retries automatically (up to 3 times)
and delivers the verifier's reason to the session. After 3 failures, you
take the wheel via `/interact`.

---

## 9. CLI reference — the six verbs

All lifecycle authority lives in the CLI (`ai4science sarsi …`).

```bash
ai4science sarsi run      sarsi-worker <task-id>               # start session (A0)
ai4science sarsi supervise sarsi-worker <task-id> --passes 25  # auto-drive to done
ai4science sarsi grant    sarsi-worker <task-id> "<permission>" # grant one permission
ai4science sarsi release  sarsi-worker <task-id>               # raise ceiling to work level
ai4science sarsi check    sarsi-worker <task-id>               # independent verdict
ai4science sarsi why      sarsi-worker <task-id>               # phase verdicts + reason
```

Full lifecycle in one line:

> **directive → `b` (pick sarsi-claude) → Enter → `run` → `supervise` → `grant` × N → `release` → `supervise` → `check` → PASS**

---

## 10. REPL slash commands

| Command | Where | What it does |
|---------|-------|--------------|
| `/sarsi-worker` | `❯` | Enter the worker |
| `/agents` | `❯` | Agent picker (workers first) |
| `/back` | anywhere | Return to previous level |
| `/do <goal>` | `sarsi-worker ❯` | Force a goal (skip classification) |
| `/tasks` | `sarsi-worker ❯` | Board for this worker |
| `/task` | anywhere | All tasks, all agents |
| `/<name>` or `/tsk_xxxx` | anywhere | Open guided mode for that task |
| `/interact` | guided | Attach to the tmux session |
| `/interact --print` | guided | Print the session screen (no attach) |
| `/stop [task]` | worker/guided | Stop session; task goes to `off` |
| `/archive [task]` | worker/guided | Close for good |
| `/rename [task] <name>` | worker/guided | Give a task a short name |
| `/goal [task] <sentence>` | worker/guided | Change the goal; plan re-drafted |
| `/why [task]` | worker/guided | Goal, criteria, last verdict |
| `/back` | guided | Leave guided mode |

---

## 11. Watching for things that need you

```bash
ai4science sarsi attention
```

Lists everything waiting on you across all workers: pending grants,
open questions, blocked sessions, exhausted retries. Exits non-zero when
something is waiting, so scripts can poll it.

---

## 12. Set your own plan (optional)

If you want to author the acceptance criteria before the session plans:

1. At the confirmation block, press `p` instead of Enter. The task is
   created in `ready` state.
2. Write a markdown plan file:
   ```markdown
   ## Phase 1 — write the file
   Verified when: fib.py exists and `python3 fib.py` prints exactly 10 lines.

   ## Phase 2 — test
   Verified when: all 10 numbers are correct Fibonacci values.

   ## Permissions needed
   - write files in /home/ai4science/work
   ```
3. Attach it:
   ```bash
   ai4science sarsi plan sarsi-worker tsk_3e8f2a91b4 --set-from myplan.md
   ```
4. Then `run` / `supervise` as normal. Your criteria are locked — the
   session cannot rewrite them.

---

## 13. Backend comparison

| Backend | Engine | Governance | Use when |
|---------|--------|------------|----------|
| `sarsi-claude` | Real Claude Code | Full (ceiling enforced) | Any code/file task — default choice |
| `sarsi-ai4sci` | AI4Science REPL | Weak (auto-yes) | Research/analysis, no strict write control needed |
| `sarsi-open` | Opencode | Limited (no hook) | Fast scripting; opencode's strengths matter |

Switch at the confirmation block with `b`. The backend is per-task, set once.

---

## 14. Sixty-second smoke test

```bash
# Throwaway state — doesn't touch your live tasks
export SARSI_STATE_DIR=/tmp/test-state
ai4science sarsi init --owner-id 1
mkdir -p /tmp/test-work && cd /tmp/test-work
ai4science
```

In the REPL:

```
❯ /sarsi-worker
sarsi-worker ❯ write hello.txt containing exactly the word hello
[confirmation block appears]
b
[backend: sarsi-claude]
[Enter]
→ tsk_xxxxxxxx
sarsi-worker ❯ /tasks
sarsi-worker ❯ /back
❯ /exit
```

Then in a shell:

```bash
ai4science sarsi run sarsi-worker tsk_xxxxxxxx
ai4science sarsi supervise sarsi-worker tsk_xxxxxxxx --passes 25
# grant any permissions that appear, then release, then supervise again
ai4science sarsi check sarsi-worker tsk_xxxxxxxx

# Cleanup
tmux kill-session -t sarsi-worker-xxxx 2>/dev/null
rm -rf /tmp/test-state /tmp/test-work
```

---

## 15. Common problems

**"I could not tell whether that is a goal"**
Use `/do <goal>` to force it.

**Confirmation block eats next line**
The `create it?` prompt owns whatever you type next. Answer it first (`n`
is always safe) before typing anything else.

**Claude Code shows a 1/2/3 menu; supervise stalls**
`supervise` can't answer interactive menus. Go to guided mode:
```
sarsi-worker ❯ /tsk_xxxx
tsk_xxxx (guided) ❯ /interact
```
Type `1` (or the right answer), then `Ctrl-z` back.

**`/interact` fails in nested tmux**
Use `/interact --print` to read the screen, or attach from a plain
terminal:
```bash
tmux attach -t sarsi-worker-<last4>
# Ctrl-b d to detach
```

**Task is `awaiting-grant` and supervise keeps stopping**
Read the `awaiting[]` field and grant each permission string verbatim:
```bash
ai4science sarsi tasks sarsi-worker   # shows awaiting[]
ai4science sarsi grant sarsi-worker tsk_xxxx "<exact string from awaiting[]>"
ai4science sarsi release sarsi-worker tsk_xxxx
```
