# Testing the PWM Code REPL and the sarsi task loop on grace

This is the exact sequence used on 2026-08-08 to live-verify the REPL, the
sarsi-worker task lifecycle, and a full task driven on real Claude Code
(backend `sarsi-claude`). Every command was run and every expected output
below was observed. Run everything **as the grace user** on agent-prod.

## 0. Prerequisites

```bash
sudo -u grace -i               # or log in as grace directly
```

- The CLI is grace's venv binary: `/home/grace/sarsi-venv/bin/ai4science`
  (below, `AI4S`). There is **no standalone `sarsi` binary** — sarsi is a
  subcommand: `ai4science sarsi <verb>`.
- Installed version should be `pwm-agent-core 1.1.8.dev11` or later
  (`/home/grace/sarsi-venv/bin/pip show pwm-agent-core`). dev11 makes
  **Opus 5 (`claude-opus-5`) the default model**, with Opus 4.8 as failover.
- Claude Code must be installed and logged in for grace
  (`claude --version` → 2.1.226 at the time of writing).
- `/usr/local/bin/claude` must exist (a 3-line shim,
  `exec "$HOME/.local/bin/claude" "$@"`). Without it the sarsi-claude
  backend fails with *"tmux took 'claude' and it did not stay up"*, because
  the tmux server's PATH lacks `~/.local/bin`.
- **Never touch** the pre-existing tmux sessions `sarsi-worker-2a68` and
  `sarsi-worker-f1f0` — they belong to older live state.

Set up a throwaway state for the whole test (cleanup at the end deletes it):

```bash
export AI4S=/home/grace/sarsi-venv/bin/ai4science
export SARSI_STATE_DIR=/tmp/repltest-state
mkdir -p /home/grace/repltest-work
$AI4S sarsi init --owner-id 1        # → "wrote /tmp/repltest-state/sarsi.json — 8 agents"
```

## Example A — the REPL itself, on Opus 5

```bash
cd /home/grace/repltest-work && $AI4S
```

1. A folder-trust gate appears ("Quick safety check…"). Type `1` + Enter.
2. Check the banner: it must read `agent  Unified-LLM  ·  Opus 5 (anthropic)`
   and the status bar must show `claude-opus-5`.
3. Type: `Reply with exactly: OPUS5-OK` — expect the reply `OPUS5-OK`
   with a footer like `✶ crunched 6s · 2.1k tokens`. That proves the new
   default model answers end-to-end through the gateway, PWM gate on.
4. Optional: `/model` shows the Anthropic menu with Opus 5 first, Opus 4.8
   second. `/model opus-4-8` switches back; `/model opus` returns to Opus 5.

Stay in the REPL for Example B.

## Example B — create a task through the REPL (sarsi-worker)

1. Type `/agents` — workers are listed first; row 1 is `sarsi-worker`.
2. Type `1` + Enter — expect `now addressing sarsi-worker` and the prompt
   changes to `sarsi-worker ❯`.
3. Type a directive, e.g.:
   `write fib.py in this folder that prints the first 10 Fibonacci numbers`
4. The worker frames it — goal, agent, "it will plan at A0 first, and stop
   for your grant" — and asks `create it? [Enter=yes / e=edit / p=plan / n=no]`.
   Press Enter. Expect `→ tsk_XXXXXXXXXX` (note the id; the last 4 hex chars
   name its tmux session later).
5. `/exit` the REPL, then confirm the task is on disk:

```bash
$AI4S sarsi tasks sarsi-worker      # table shows the task, state "ready"
```

A REPL-created task runs on the default backend `sarsi-pwm` (PWM Code).
To run it on real Claude Code instead, create it from the CLI (Example C) —
the backend belongs to the task and there is currently no CLI verb to switch
an existing task's backend.

## Example C — a full task on real Claude Code (sarsi-claude)

### C1. Create the task on the claude backend

```bash
$AI4S sarsi do sarsi-worker \
  "write fib.py in the working directory that prints the first 10 Fibonacci numbers, one per line" \
  --workdir /home/grace/repltest-work --backend sarsi-claude
# → "sarsi-worker holds tsk_XXXXXXXXXX — running"
```

`do` only records the task (`session: null`). Nothing starts yet.

### C2. Start the governed session

```bash
$AI4S sarsi run sarsi-worker tsk_XXXXXXXXXX
# → "it is drafting the plan from my initial one; `sarsi supervise` collects it"
```

This launches tmux session `sarsi-worker-<last4>` running the real `claude`
binary, governed (hook wired, planning ceiling A0). You can watch it any
time: `tmux attach -t sarsi-worker-<last4>` (Ctrl-b d to detach).

### C3. Let the supervision loop drive

```bash
$AI4S sarsi supervise sarsi-worker tsk_XXXXXXXXXX --passes 25
```

Expected log lines, in order:

```
answered — the folder-trust prompt, for a folder this worker created
briefing — waiting to see the brief land
busy
answered — writing this task's own plan file, which is exactly what it was asked to do
planned — 2 criterion(s); …
awaiting-grant — it needs you to grant …
```

The loop answers the trust gate, delivers the brief, approves the plan-file
write, collects the plan — and then **stops at awaiting-grant, by design**:
granting permissions is the owner's act, never the loop's.

### C4. Grant, release, drive to a verdict (the owner's moves)

Read the exact permission strings and grant each one verbatim:

```bash
python3 - <<'EOF'
import json, os
t = json.load(open(os.environ["SARSI_STATE_DIR"] +
    "/agents/sarsi-worker/tasks/tsk_XXXXXXXXXX/task.json"))
print(json.dumps(t["awaiting"], indent=1))
EOF

$AI4S sarsi grant sarsi-worker tsk_XXXXXXXXXX "<permission string 1>"
$AI4S sarsi grant sarsi-worker tsk_XXXXXXXXXX "<permission string 2>"   # etc.
# last grant flips the task awaiting-grant → running

$AI4S sarsi release sarsi-worker tsk_XXXXXXXXXX   # raises ceiling A0 → A2 live
$AI4S sarsi supervise sarsi-worker tsk_XXXXXXXXXX --passes 15
```

**Known gap:** Claude Code's own confirm menus ("Do you want to create
fib.py? 1/2/3") have no supervise rule yet — the loop abstains, and at the
permissions layer an unanswered confirm reads as a deny (the session reports
`[blocked] user decision`). When that happens, answer it yourself:

```bash
tmux attach -t sarsi-worker-<last4>    # then type 1 (or 2), Ctrl-b d
```

The final supervise round should end with:

```
steered — Run `grep -n '34' …`
verified — the goal is met
verified — write fib.py … verdict PASS
```

### C5. Independent check and evidence

```bash
$AI4S sarsi check sarsi-worker tsk_XXXXXXXXXX    # → PASS
cat /home/grace/repltest-work/fib.py              # the 4-line program
cat $SARSI_STATE_DIR/agents/sarsi-worker/tasks/tsk_XXXXXXXXXX/run_stdout.txt
# → 0 1 1 2 3 5 8 13 21 34 (one per line), run_exit_code.txt → 0
$AI4S sarsi why sarsi-worker tsk_XXXXXXXXXX       # phase verdicts + blast radius
```

## Cleanup (always)

```bash
tmux kill-session -t sarsi-worker-<last4> 2>/dev/null
rm -rf /tmp/repltest-state /home/grace/repltest-work
tmux ls    # only sarsi-worker-2a68 and sarsi-worker-f1f0 may remain
```

## Quick reference — the lifecycle in one line

`init` → (`REPL /agents → enter → directive → Enter` **or** `do --backend
sarsi-claude`) → `run` (starts the governed session) → `supervise` (drives:
gates, brief, plan) → `grant` × N → `release` → `supervise` (work + verify)
→ `check` → cleanup.
