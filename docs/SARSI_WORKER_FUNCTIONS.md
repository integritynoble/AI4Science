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
| `board` | **The board's third face — a page**, over the same records the CLI and chat show. **Loopback only**, and a non-local host is refused: the board holds goals, criteria and verdicts, and `abraham`'s are personal. Read-only, no form and no button — a page that could start work would be an unauthenticated door into the fleet. |
| `tasks` / `/task` / `/tasks` | The board — every task, its state, and what each waits on. |
| `plan` / `adopt` | A task's phases, criteria and declared permissions, rendered from the plan **file**. Editing `plan0.md` by hand used to change what `plan` displayed and **not** what the verifier applied — live that cost two FAILs whose stated reasons were both true of a criterion nobody was looking at. `check` now **refuses** a task whose file has drifted from its recorded criteria (`UNVERIFIED`, not `FAIL` — which of the two is meant is genuinely unknown), and `adopt` is the owner taking the file as the standard, clearing the verdicts of the phases that changed. It refuses rather than adopting on its own because **the plan file sits in the session's own working directory**: "the file wins" would let the agent being judged restate the question and drop the verdict that failed it. A **stale** plan is exempt — its criteria were withheld on purpose. |
| `grant` | Grant one permission the plan declared — including `delete files in the working directory`, the **only** destructive gate the loop may answer, and only for a non-recursive delete of named paths inside that directory in a command that does nothing else. |
| `goal` / `/goal` | **Move the goal.** The plan is re-drafted to follow it, the agreement drops, the owner's own criteria survive, and a running session is told. |
| the write gate · declared paths | **A write inside what the task declared is one the owner already authorised.** Every live run today ended with correct work and the loop stopped at `Do you want to create win.md?` for a file in the very directory the task declared, on a task the owner had granted and released. `blast` already treats those paths as ones the task may write and the sandbox is already launched with them, so the hook was asking for a decision that had been made — and the answer the owner would give to unblock is *yes*, every time, which is a gate being rubber-stamped rather than consulted. Built to `deletion.permitted`'s rule: **refusing is the default and every path out is explicit.** Four refusals carry it — outside the declared roots (compared as resolved paths: `/x/work-evil` is not inside `/x/work`); before `release` (the ceiling is still A0, nothing has been granted, there is no authority to apply); a gate that does not state the path **in full** (the question line says `create summary.md?`, and live that basename belonged to `../../../../../live-retire/summary.md` — a file located by guessing is a file approved by guessing); and the wider *"allow all edits during this session"*, which is a standing grant over everything that follows and is checked **before** the path, since pressing it would take that permission whatever this gate was about. |
| the A0 shell gate | **A command is judged by everything in it, not by its syntax.** `$(…)`, backticks and `for`/`while`/`until` used to be refused outright, so an unattended run stopped the first time a session counted something into a variable — live, at `for t in foo bar baz; do c=$(grep -c -- "$t" d.csv); …`. Each wrapper is now opened and its contents classified by the same rules, recursively: **nothing is allowed inside a substitution or a loop that would not be allowed on its own.** The word list, the loop condition and the body are each judged; a leading `NAME=value` runs nothing and is stripped; `do`/`done` are keywords, not programs, and a loop that does not balance is refused. Deliberately still refused: `if`/`case`, the arithmetic `for ((…))` and `$((…))`, and `read` — plus `true` and `:` stay off the allowlist, which is the only thing keeping `while true; do …; done` (read-only and never returning) out of an unattended session. Writing the tests found that `<(…)` was ALREADY judged by its contents, since `(`/`)` have always been segment boundaries — the global `$(` reject was the outlier, not the principle. |
| a verified task · its session | **It lets go of the terminal.** Live, `attention` reported it straight after a PASS: *"its task is verified but session sarsi-worker-5b2f is still running, holding whatever it was granted"* — a live session at the released ceiling, with write permission to the working directory, and no task left that needs any of it. Every one of those grants was justified by work that had finished, and it held one of the worker's concurrency slots besides. **Not `stop`**, which sets the state to `off` and would erase the one outcome worth keeping: the terminal closes, the verdict and the plan stay. Best-effort, so a tmux that will not die does not cost the record. It does **not** fire on a phase passing (a checkpoint mid-run), on a FAIL (handed back for another attempt), or while the owner has the wheel. What it cost is kept in `past_sessions`, and `answer` reads the name from there — *"session X, verdict PASS"* is how the record says which run produced the result. |
| `check` · after release | **What the owner released is the standard, and a later edit does not stop the run.** Two live runs in a row ended UNVERIFIED with correct work: the session had edited `plan0.md` while doing it, and judging was refused until the owner ran `adopt`. Sessions revise their own plan mid-work as a matter of course, so the refusal fired on most tasks — and what it asked the owner to do to unblock was **adopt whatever the session had just written**. A gate that is habitually rubber-stamped is worse than no gate: it launders the session's rewrite as the owner's decision. Granting each declared permission and raising the ceiling IS the owner saying which reading is meant, so after release the record is applied and the divergence is **reported on the verdict** (`Judged against what you released. plan0.md has since changed at phase N…`). Before release nothing has been approved and the refusal stands. The property that does not move: the plan file lives in the session's own working directory, so judging against the record is what denies a session the power to lower its own bar. |
| `/edit <task> <n> <criterion>` · `adopt` | Change what gets verified. **The owner's edit wins**, and now survives a session's RE-PLAN: the session may rewrite its steps, notes and phases, and what a verdict is measured against stays the owner's until they change it. Three live `work` runs failed in the plan and never in the work — the last one replaced the owner's criterion with `matches the cited source character-for-character` when no source existed, then could not satisfy it, and `retry` could not converge because the objection was unmeetable rather than unmet. The rewrite is still **reported** by `why` (silently ignoring it would hide that the file no longer describes what is judged) and judging is not refused for it, because the question drift asks — *which of the two is meant?* — has an answer. |
| `stop` / `/stop` | Stop a task **and kill its session**. Resumable; the plan survives; the slot is freed. |
| `archive` / `/archive` | Terminal. Record kept, slot freed, off the board — counted on the board so archiving never reads as deleting. |
| `reopen` / `/reopen` | Put an archived task back, **stopped** — re-opening is a decision to look, not to start. |
| `/resume-task` | Put a stopped task back to work. Named apart from `/resume`, which hands *steering* back after Interact. |

### Running work

| Function | What it does |
|---|---|
| `run` | Hand the plan to `sarsi-claude` — starts its governed session. The brief is typed as **one keystroke stream**: `tmux send-keys -l` sends the literal text *including its newlines*, and a newline in a TUI input is a submit — so a multi-line brief was submitted in FRAGMENTS (`Goal: …` alone as a prompt, the rest arriving while the session answered it) and the loop then reported `undelivered` about a session it had fragmented itself. |
| `release` | Raise the ceiling from the planning `A0` to what the agent has earned. |
| `operate` | One supervision pass: answer the gates it has a rule for, submit a stranded prompt, report the rest. While **planning** it also answers the governance hook's own gate for a **provably read-only** command — A0 is *"reads allowed, everything else asks"*, but the hook gates every bash, so six passes in a row abstained at a `find … | head` the ceiling already permitted and planning needed a human at each gate. Judged by the same conservative classifier the harness gates on: an unknown binary, a redirect or a command substitution still goes to the owner. |
| `supervise` | Drive a task to a verified result. |
| `guide` / `/guided` | Steer by hand. The owner's word always goes through; the worker's stands down when the owner holds the wheel. **Never at an interface the loop cannot read** — `by_owner` is not an exemption, because the hazard is the screen, not the author. Every path that types at a session now passes this: `retry`, `answer`, `guide`, a goal change, the verdict `check` sends back, `release`'s re-brief and the chat door. A task with **no session at all** is a different refusal from a session it may not type at — *nowhere to deliver* rather than *not allowed to* — and it names `sarsi run` instead of pointing at a terminal that does not exist. |
| `/interact` | Hands over the `tmux attach` line and stands back. **It does not relay.** |
| `/history` | What has happened, from the record. |
| `handoff <agent> <task> --to <worker>` | **One worker hands finished work to another** — `work` → `funding`. A **proposal**: a worker may not give another worker work, so only the owner's `--accept` creates the task. Only *verified* work may be handed on, and the evidence travels as a **dependency link**, not a summary. |
| `handoff` | **`HANDOFF.md` for the next session**, written automatically when a task stops. Names the phases already verified so they are not redone, the verifier's last objection, open questions and grants held. It records what the RECORD knows — never what the session believed. |
| `check` | Ask the verifier: **PASS / FAIL / UNVERIFIED**, with a reason. Which judge it reaches is a fact about the MACHINE, not about who typed the command: `PATH` first, then the standard bin directories a login shell would have added — a live `check` from a script fell past an installed `claude` to an OpenAI key nobody configured and 401'd, which would have made the unattended path the one that silently cannot judge. The judge is then INVOKED by the path it was found at, since finding it and running it are two lookups. The verdict is read from a verdict **line**, decoration and all (`**PASS**:`, `- FAIL:`), so prose containing the words is not a judgment and a bolded judgment is not discarded. **Gathers its own evidence** when none is given. A **stale plan is refused, not judged** — see decision 2. |
| `blast` | **What it wrote, against the paths its plan declared.** Read from the session's own `Write`/`Edit` records — the Claude Code transcript, or **the harness's own session record for an attended agent**, whose relative `path` is resolved against the workspace it was written in, not the reader's. `Bash` that could WRITE names no file, so it is counted as *unchecked* and never reported as clean — but one **proven read-only** by the same conservative classifier that decides what may run without asking is counted apart, because a command that cannot change anything has nothing to vouch for. Every run this week closed on *N shell commands could not be checked* and every one of those was the session verifying its own work (`wc -w`, `ls -la`, `grep -c`); counting those as unobserved claimed the report might be missing a write that could not have happened. They are still **reported**, so a reader can tell a session that ran fifty commands from one that ran none — "nothing escaped" and "nothing was left unobserved" are separate answers. |
| `do --after <agent>/<task>` | **One task waits on another, across agents.** Satisfied means **verified** — not stopped, not archived, because closing a task is not succeeding. An unknown dependency and a cycle are both refused at declaration, since a task that can never run must say so while you are still looking. It never auto-starts what it unblocks. |
| `do --steps N --minutes M` | **A declared ceiling on the WORK**, counted from the moment planning ends. Past it the task *stops and keeps its plan* — it does not fail, because running out of budget says nothing about whether the work was right. Checked **before** the loop acts. Steps come from the transcript; unreadable means *not enforced*, never *over*. No default. |
| `do --plan-steps N --plan-minutes M` | **Planning's own ceiling**, spent apart from the work's. A live task declared 24 steps, its planning session used 25 reading the folder and drafting, and it stopped with its working directory empty — a ceiling a task can exhaust *without attempting its goal* does not bound the work. The boundary is **`plan_agreed`** — the same flag `assign` reads to leave the A0 planning ceiling — and the mark is recorded where the session's plan is adopted, not only at `release`, which is an owner command the loop never calls. With no mark the floor is zero: the old behaviour, which can only stop a task *earlier* than the truth. No default here either — an undeclared planning ceiling is not enforced. |
| `do --workdir <dir>` | Declare **where the work happens**. Evidence is gathered from there instead of the task folder — declared, never inferred, so a criterion naming a path cannot move the boundary. A path outside it is reported as outside, never read and never silently dropped. The **sandbox honours it too**: the session is launched able to write there. It was not, and the effect was an inversion — `write` (which names its path, and is what `blast` reads) was refused, while a `bash` heredoc doing the same thing succeeded, so the act that mattered moved from observed to unchecked. Two boundaries that disagree are one boundary and one blind spot. The roots come from the plan and are passed at launch, so widening needs a new session — and they are **named in the `write`/`edit` tool descriptions**, because a capability the model cannot discover changes nothing: the first run after the sandbox fix still reached for a heredoc into a directory `write` had just been given. |
| `check --phase N` | Judge **one phase against its own criterion**. A phase is done when a verdict says so about *that* phase; the task is verified only when every phase is. Editing a criterion clears that phase's verdict; moving the goal clears all of them. |
| `retry` | **Hand a FAIL back carrying the verifier's reason.** Only a judged `FAIL` retries; capped at 3; a `PASS` clears the count. It **refuses at an interface the loop cannot read** and hands the owner the text plus the attach command, rather than typing prose at whatever screen is showing. A refused hand-back **costs no attempt** — counted first, three refusals would exhaust a task nothing was ever delivered to. |

### Knowing where you are, and what needs you

| Function | What it does |
|---|---|
| `questions` / `answer` | **The escalations, in one place, answerable from either surface.** `answering` declines what it must not answer and escalates it; these list what is open and deliver your reply into the session. The owner closes a question — a later automatic answer does not. On an **attended** agent it refuses instead of typing, and the question **stays open** — one closed by an undelivered answer is one the owner believes they have dealt with. |
| `attention` | **"Is anything waiting on me?"** across every worker, or one. Gates (with the actual command), **terminals no task claims**, orphans, ungranted permissions, open questions, exhausted retries, undelivered kickoffs, **plans edited since they were attached** (judging is refused until `adopt` settles which is the standard), stale plans, **attended sessions with what is on their screen** — not driving an interface is not the same as not reading one, and `capture-pane` is read-only; the lines are labelled as a screen rather than interpreted, because a confident label on an interface nobody parsed is the same mistake as driving it, and records pointing at terminals that are gone. Exits non-zero when something waits, so a timer can act on it. |
| `enter` | Step into a worker: the task you last touched, or — holding none — **the question "what would you like done?"** rather than an empty board. It **reconciles the records against tmux** first, so it reports now rather than what was true when the record was written. |
| workspace fold | The history a node plans from keeps the most recent lines **and folds the overflow**: anything said three times or more is promoted with its count (`use the staging host ×5`), which is exactly what a plain tail loses. Repeats take **one** slot in the visible window rather than filling it. A **tally, never a précis** — every promoted line was actually written. |
| cursor per `(surface, account)` | Being *in* a task, so plain words are about that task. Stored on disk; the phone and the laptop stand in different places. |
| `why` / `/why <task>` | **The goal, the criteria a verdict will apply, and what the last verdict said** — in one answer. Reports and never infers: no verdict says *not judged yet*, and it will not name a "current phase" (see below). |
| `spend` | **What it cost** — tokens in/out, cached apart from fresh, and wall-clock — read, not estimated, from whichever book the session kept: a `claude-code` session's transcript, or **the meter's ledger for an attended one** (`social`, `funding`, `jobs`, `abraham` run the ai4science TUI and write no transcript — for three live runs they reported *not recorded*, which was honest and useless). Unknown is still *not recorded*, never 0. PWM is **priced** for an attended session, which went through the meter, and *not charged here* for a Claude Code one, which never did — the two are never flattened to `0`. |
| `digest` | **One read across what an agent did**, instead of many — **delivered unprompted** by the gateway poll to the agents whose roster asked for it, once a period, and never for a quiet one — `social` and `abraham` asked for it in the roster. It reports what *happened* and **points at** what is still waiting rather than restating it, so one obligation keeps one home. The span is stated, not implied; a quiet period and an unreadable ledger are different answers. |
| `decisions` | **What it decided without you, and at which rung.** Only the agent's own acts — the owner's guidance is not the agent deciding. An act recorded with no ceiling reads `unknown`, never `A2`. Reading does not acknowledge; `--ack` moves the line and `--all` still shows everything under it. |
| `rules` | **House rules for this machine**, told to every session that agent starts — the host facts it would otherwise rediscover (`use python3 on this host`). They live in `W_host` and never travel; the **owner** writes them, because an agent that can write its own standing instructions can widen them — an agent may **propose** one with its reason, and only the owner's `--sign` adopts it. A rule may *name* a credential, never carry one. |
| `supervise` · the brief | **A brief is typed at a screen that can take it, and the count belongs to the session that failed.** Three live runs reported *the session is not taking its brief*; the same text sent by hand landed instantly. All three tries had been spent against a session `start_session` reported and never started, and `assign` left the counter alone on restart — so the loop declared the brief undeliverable before one keystroke reached the session that existed. A send that never reached tmux is now a **different** answer (*there is no session to send it to*) from a session ignoring the brief, because the owner would act differently on each. And the delivery is guarded: keystrokes at a modal are discarded while the Enter votes on whichever option is highlighted, so a pass that correctly declines to type spends no try. |
| `supervise` · a stranded prompt | **Dim is the discriminator, not the wording.** The loop pressed Enter on `granted, write report.md` at a session waiting for the owner to grant a write — text nobody typed. `\x1b[2m` is SGR dim, Claude Code's own placeholder, and `capture-pane -p` strips it, so a hint and an instruction were the same string. The `Try "…"` filter catches one shape and the hints are contextual now (*go ahead, write the report*). `capture-pane -e` is read for this one question; a pane that cannot supply it falls back to the shape filter, because an unstyled capture is not evidence that something was typed. |
| `who` / `/who <demand>` | **"Who should do this?"** — `sarsi-machine`'s one power. It ranks on **precedent** (a worker that has *verified* similar work, cited by task id), then on what the roster says each agent is *for*, then tools, then name. It **creates nothing**, and it **declines to pick** when nothing distinguishes two workers: routing personal work to `abraham`, or personal work to a general worker, is a scope mistake, not a coin toss. It never offers a **retired** agent. |
| `agents` · *retired* | **Out of routing, still readable.** The owner asked for one general worker, so `work` retired and `sarsi-worker` is it. The roster entry was **not deleted**, because a roster entry owns its task folder and `work` holds 32 archived tasks — `tasks --archived`, `plan`, `blast` and `spend` all still read them. `do work "…"` is refused **by name** rather than filing a task nobody will supervise, and the listing shows it as *retired* rather than dropping it, because an agent that vanished reads as a machine that lost one. Its general vocabulary (`code`, `repo`, `script`, `benchmark`…) moved to `sarsi-worker` so no demand is stranded on *"I cannot tell"*; **`mail`, `email` and `mailbox` did not move** — the vocabulary follows the capability, and a do-everything agent that also reads the mailbox is the concentration the split exists to prevent. |
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

**Everything the merged list named is built, and so are the two items that
finishing it produced.** Part 2 is empty on purpose: the next entries should be
written the way every entry above was — named by the run that exposed them,
rather than invented to keep a list full.

Tier 3 below is still deliberately later.

## Part 3 — Deliberately later

*(The per-agent page was built **local** instead — see `board` above. The
Tier 3 entry said `physicsworldmodel.org/<agent>/`, which I had written by
conflating this repo's own `board.py` — "CLI, chat, and a **local** HTML page" —
with a passing suggestion of that URL. They are different products: the site
page would need the board uploaded off the machine, and every other rule here
refuses to let a local fact travel. The owner chose local.)*

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
| `questions` / `answer` | **The escalations, in one place, answerable from either surface.** `answering` declines what it must not answer and escalates it; these list what is open and deliver your reply into the session. The owner closes a question — a later automatic answer does not. On an **attended** agent it refuses instead of typing, and the question **stays open** — one closed by an undelivered answer is one the owner believes they have dealt with. |
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
