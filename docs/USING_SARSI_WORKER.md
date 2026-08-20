# Using `sarsi-worker` — Dispatching an Autonomous Motor

A field manual for the fleet owner. It tells you how to dispatch one autonomous
agent ("motor") at a problem, how to tell whether it actually did the work, how
to write a brief that won't stall, and where the ground is soft. Every command
here was run on the host on **2026-08-20** unless explicitly marked
`unverified`; see the [Verification](#verification) section at the end for the
per-command ledger.

Host at time of writing: OpenClaw **2026.6.11 (e085fa1)**, Node **v24.19.0**.

**Jump to:** [TL;DR dispatch](#tldr--the-copy-pasteable-dispatch) ·
[When NOT to use](#when-not-to-use-this) ·
[Judging a run](#judging-a-run--never-on-one-signal) ·
[Writing a brief](#writing-a-good-brief) ·
[Honest limits](#the-honest-limits) ·
[Timeouts](#timeouts-stack--the-smallest-one-binds) ·
[Verification](#verification)

---

## TL;DR — the copy-pasteable dispatch

```bash
# 1. Node must be on PATH first, or openclaw is simply "command not found".
export PATH=/home/tina3/.nvm/versions/node/v24.19.0/bin:$PATH

# 2. Write the brief to a WORLD-READABLE file (mode 644) in a readable dir.
#    /tmp is fine. A 0700 parent dir will make the launcher fail with EACCES
#    and the run dies within seconds, silently.
install -m 644 /dev/null /tmp/brief.txt
$EDITOR /tmp/brief.txt          # ... write the brief (see "Writing a good brief")
stat -c '%a %n' /tmp/brief.txt  # must print: 644 /tmp/brief.txt

# 3. Dispatch. --timeout is the brain-turn budget in seconds.
openclaw agent --agent sarsi-worker --timeout 1700 --message-file /tmp/brief.txt
```

That last command is the one working dispatch invocation. It was
**verified end-to-end by the operator on 2026-08-20** and, per policy, was
**not re-run during authoring of this manual** (dispatching a real motor from
inside a motor spawns a brain turn recursively). The CLI *surface* below
(`--agent`, `--message-file`, `--timeout`) was re-verified here with
`openclaw agent --help`.

`--timeout` default is **600** seconds (or the config value) if you omit it.
For real work that is almost always too short — set it explicitly.

### Pre-flight checklist (30 seconds, saves a dead run)

- [ ] `node --version` prints `v24.19.0` (PATH exported).
- [ ] `stat -c '%a' /tmp/brief.txt` prints `644`, and no parent dir is `0700`.
- [ ] The brief names one **concrete completion criterion** and a **nonce**.
- [ ] The brief **forbids `git push`** and forbids `cd DIR && cmd`.
- [ ] The brief has **no contradictory rules** (read it once as an adversary).
- [ ] You noted the current newest record so you can spot a new one afterward:
      `ls -t /home/tina3/.openclaw/acpx/ai4sci-records/ | head -1`.
- [ ] Only **one** motor will touch the target branch.

---

## When NOT to use this

Unattended dispatch is the wrong tool when:

- **Nobody will check the artifacts afterward.** The return value of a dispatch
  is *not* trustworthy (see [The honest limits](#the-honest-limits)). If no
  human or supervisor will inspect the branch, the commits, and the run record,
  do not dispatch — you'll act on a lie half the time.
- **The task has no concrete, checkable completion criterion.** "Improve the
  code" gives you nothing to verify against. If you can't write down the exact
  file/nonce/test that means "done", the motor can't either.
- **Two motors would touch the same branch.** They clobber each other. One
  branch, one motor. If a dispatch looks dead, *recover the handle* — do not
  respawn (see [Corollary: do not respawn](#corollary-do-not-respawn)).
- **The work is interactive or needs a human decision mid-run.** Nobody answers
  during the run. Ambiguity gets decided by the motor, or it stalls.

---

## Judging a run — never on one signal

A dispatch reporting success proves nothing on its own. Confirm with **all** of
the independent signals below before you believe a run finished.

1. **The artifact exists and matches a run-unique nonce.** Put a nonce in the
   brief ("write `GATE-<random>` into `path`"), then check the file contains
   exactly that nonce. This defeats stale artifacts from earlier runs.

2. **A NEW record appeared in the launcher's record dir.** This proves *our*
   launcher ran, not the gateway's own agent (that has happened: a correct-looking
   file was written by the gateway agent, not by our dispatch).

   ```bash
   ls -lt /home/tina3/.openclaw/acpx/ai4sci-records/ | head
   ```

   Baseline for 2026-08-20: the newest record *before* today's runs was
   `ai4sci-72476a8636ee4788.log`, dated **Aug 19 20:03**. Anything newer is new.
   To list only records newer than that baseline:

   ```bash
   find /home/tina3/.openclaw/acpx/ai4sci-records/ -type f \
     -newer /home/tina3/.openclaw/acpx/ai4sci-records/ai4sci-72476a8636ee4788.log
   ```

3. **That record's header says `rc=0` AND `mode_fallback=none`.** Check the
   first non-blank line:

   ```bash
   head -3 /home/tina3/.openclaw/acpx/ai4sci-records/<the-new-record>.log
   ```

   A real header looks like:

   ```
   ===== turn 1  rc=0  mode=Unified-LLM  mode_requested=ai4sci  mode_fallback=none  harness_session=...  elapsed=12.77s
   ```

   `rc=0` **alone means nothing** — a mode fallback still reports `rc=0`. You
   need `mode_fallback=none` as well. If it says anything other than `none`, the
   agent did not run in the mode you asked for.

4. **"accepted" is NOT "done".** The yield point is `send()`, not acceptance of
   the request. A queued/accepted dispatch has not produced anything yet.

If any one of these four disagrees with the others, trust the artifacts and the
record over the return string.

---

## Writing a good brief

This is the part that most determines whether a run succeeds. The brief is the
entire contract; the motor cannot ask you anything.

- **State what is already established.** Every fact the agent has to re-derive is
  time it spends not doing the task — and a chance to derive it wrong. Give it
  the paths, the versions, the working invocation, the known hazards.
- **Give a CONCRETE completion criterion.** Not "fix the bug" — "test `X` goes
  from red to green, and `git log` shows the failing run committed before the
  fix." Something you can mechanically check afterward.
- **Demand RED evidence, committed.** Require the failing run (test output,
  repro) to be committed *before* the green one. A green-only history can't be
  distinguished from a test that never actually exercised the bug.
- **Forbid pushing, explicitly.** Say "commit only, never `git push`." Motors
  will push if you don't forbid it.
- **Tell it to report what it could NOT determine.** A run that says "I couldn't
  verify Y" is worth far more than one that silently papers over Y.
- **Check for CONTRADICTORY constraints before you send.** The agent catches
  contradictions and stalls on them. Real example that killed a run: a brief
  forbade "starting a session" while also asking the agent to spawn one. Read
  your own brief once as an adversary looking for a rule it cannot satisfy.

A brief skeleton that has worked:

```
# TASK: <one line>
## GROUND TRUTH (already established — do not re-derive)
  - <paths, versions, the working command>
## COMPLETION CRITERION (all must hold)
  1. <concrete, checkable>
  2. Commit the RED run before the GREEN run.
## HARD RULES
  - Commit every few minutes. Never `git push`.
  - Never write `cd DIR && cmd`; use absolute paths / `git -C <dir>`.
  - Report anything you could NOT determine.
## FINAL ANSWER
  - <what to print, and a RESULT: PASS/FAIL line>
```

---

## The honest limits

Read this before you trust any dispatch.

**Autonomous EXECUTION works.** A dispatched motor has, unattended, written
failing tests, fixed the code, re-run to green, and committed **9 commits** of
verified work. The execution loop is real.

**Autonomous OPERATION does not (yet).** The layer that tells you *what
happened* is unreliable. Three dispatches all returned the identical string
`"The operation timed out"` while their true fates were **completed / vanished /
completed**. A supervisor that reads the return value is wrong in *both*
directions: it abandons finished work, and it respawns jobs that are still
running.

**Honest hit-rate — six dispatches on 2026-08-20:**

| Outcome                     | Count |
|-----------------------------|-------|
| Substantial verified work   | 2     |
| Produced nothing            | 3     |
| Still running at report time| 1     |

That is two-in-six confirmed good. Do not round it up. Plan for a dispatch to
fail and build the check into your workflow — that's what the
[judging](#judging-a-run--never-on-one-signal) section is for.

### Corollary: do not respawn

If a dispatch *appears* to time out, **do not respawn it.** The return string
lies; the work may be finished or still in flight. Instead, recover the handle
and poll for artifacts:

```bash
export PATH=/home/tina3/.nvm/versions/node/v24.19.0/bin:$PATH
openclaw sessions list --agent sarsi-worker --active 60 --json | head
```

Then check the artifact + record signals above. Two executors on one branch
clobber each other — respawning turns a maybe-finished job into a definitely-
corrupted one.

---

## Timeouts stack — the smallest one binds

There are four timeouts in the path. The **smallest** one that fires ends the
run, so raising just one changes nothing if a smaller one is still in effect.

| Timeout | Where | Default | Notes |
|---|---|---|---|
| `AI4SCI_ACP_TIMEOUT` | adapter subprocess, set in the launcher `/home/tina3/.openclaw/acpx/ai4sci-run.sh` | 300s stock; **raised to 1800s** in the launcher | Verified present: `export AI4SCI_ACP_TIMEOUT="${AI4SCI_ACP_TIMEOUT:-1800}"` |
| AcpRuntime timeout | client side | 900s | unverified here (not re-grepped) |
| `openclaw --timeout` | the brain turn | 600s or config | set per call; this is the one you control on the CLI |
| `CLAUDE_ACP_SESSION_CREATE_TIMEOUT_MS` | session create, vendored openclaw | 60s | env-overridable as `ACPX_CLAUDE_ACP_SESSION_CREATE_TIMEOUT_MS`, but **masked** by the MCP SDK's own 60s `DEFAULT_REQUEST_TIMEOUT_MSEC` — which is *why raising the adapter cap alone does nothing* |

The two 60s constants in the last row could not be re-confirmed by grep during
authoring: a scoped `grep -rl` under
`/home/tina3/.openclaw/npm/projects/openclaw-acpx-052d680d6d/node_modules/`
exceeded a 60s budget under this host's I/O load and was killed. They are
therefore marked **unverified — grep exceeded time budget under load**. The
behavioral consequence (raising the adapter cap alone changes nothing) matches
what the operator observed.

Practical guidance: set `openclaw --timeout` generously (e.g. 1700), and know
that the session-create step still has a ~60s ceiling you cannot lift from the
CLI. If a run dies within ~60s of dispatch, suspect session-create, not your
`--timeout`.

---

## Verification

Every command in this manual, with its status as of **2026-08-20**. Commands run
on this host during authoring are `verified 2026-08-20`. The one dispatch that
must not be re-run recursively is marked accordingly.

| # | Command | Status |
|---|---------|--------|
| 1 | `export PATH=/home/tina3/.nvm/versions/node/v24.19.0/bin:$PATH` | verified 2026-08-20 (`which node` → that path, `node --version` → v24.19.0) |
| 2 | `openclaw --version` → `OpenClaw 2026.6.11 (e085fa1)` | verified 2026-08-20 |
| 3 | `openclaw agent --help` (surface: `--agent`, `--message-file`, `--timeout` default 600) | verified 2026-08-20 |
| 4 | `openclaw agent --agent sarsi-worker --timeout 1700 --message-file /tmp/brief.txt` (full end-to-end dispatch) | verified by the operator on 2026-08-20; **not re-run during authoring** (recursive brain turn). CLI surface re-verified via `--help`. |
| 5 | `install -m 644 /dev/null /tmp/brief.txt` + `stat -c '%a %n' /tmp/brief.txt` → `644 ...` | verified 2026-08-20 |
| 6 | `ls -lt /home/tina3/.openclaw/acpx/ai4sci-records/ \| head` | verified 2026-08-20 (baseline newest = `ai4sci-72476a8636ee4788.log`, Aug 19 20:03) |
| 7 | `find .../ai4sci-records/ -type f -newer .../ai4sci-72476a8636ee4788.log` | verified 2026-08-20 (returned empty, as expected pre-run) |
| 8 | `head -3 <record>.log` shows `rc=0 ... mode_fallback=none` header | verified 2026-08-20 (header format confirmed on baseline record) |
| 9 | `openclaw sessions list --help` (surface: `--agent`, `--active`, `--json`) | verified 2026-08-20 |
| 10 | `openclaw sessions list --agent sarsi-worker --active 60 --json` | verified 2026-08-20 (returned valid JSON with real sessions) |
| 11 | `grep AI4SCI_ACP_TIMEOUT /home/tina3/.openclaw/acpx/ai4sci-run.sh` → `:-1800` | verified 2026-08-20 |
| 11a | `ls -t /home/tina3/.openclaw/acpx/ai4sci-records/ \| head -1` | verified 2026-08-20 (→ `ai4sci-72476a8636ee4788.log`) |
| 11b | `node --version` → `v24.19.0` | verified 2026-08-20 |
| 12 | `grep -rl DEFAULT_REQUEST_TIMEOUT_MSEC / CLAUDE_ACP_SESSION_CREATE_TIMEOUT_MS` under the acpx node_modules path | unverified — grep exceeded time budget under load (killed at 60s) |
| 13 | AcpRuntime 900s client-side timeout | unverified — not re-grepped during authoring |

---

*If a command in this manual ever stops working, treat the manual as wrong and
fix it — a manual with a command that does not work is worse than no manual.*
