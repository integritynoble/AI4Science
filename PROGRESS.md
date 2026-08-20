# PROGRESS — wire the group ceiling into the grant path

Turn opened 2026-08-14 00:35 UTC. Repo `/home/ai4science/pwm/AI4Science`,
branch `proto/repl-mode-ai4science`, HEAD at start `761a53a`.

Goal: `Group.capped()` is consulted by the GRANT path, not only by renderers.
A research agent whose members cap it at A0 must be REFUSED an A3 action.

## Phase 1 — locate the grant path  [DONE]

`capped()` had exactly three call sites before this turn, and all three are
**display**:

- `ai4science/commands/research.py:70` — `research show` CLI output
- `ai4science/harness/agents/sarsi/board.py:126` — the board's research page
- `tests/test_research_group_ceiling.py` — the unit tests of the rule itself

The grant path is `ai4science/harness/agents/machine/session.py`:
`decide_tool_call(call, *, ceiling=...)` computes `lvl = _CEILING_ORDER[ceiling]`
and every allow/ask verdict hangs off `lvl`. `SessionDriver` holds a bare
`self.ceiling` string. Its two callers — `machine/hook.py:181` and
`sarsi/operator.py:541` — pass a declared ceiling and nothing about the group.

So the rule was descriptive: a group could say A0 and the session still acted
at its declared ceiling.

**Verified when:** grep shows no `capped(` in any grant-path module. It did not.

## Phase 2 — freeze a RED check  [DONE]

`state/probe_group_ceiling_grant.py` in the sarsi-worker workspace — written by
sarsi-worker, NOT by the executor, so the session that implements the wiring
does not also write its own verdict. 7 checks:

1. `decide_tool_call` refuses an A3 action under an A0 group
2. `SessionDriver` refuses an A3 command under an A0 group
3. `SessionDriver` refuses an unmapped tool under an A0 group
4. **control** — with no group, A3 still acts (so the probe cannot pass by
   simply breaking A3)
5. a group caps and never widens (A1 group + declared A0 stays A0)
6. the ordinary case: shipped A1 group caps a declared A2 on `git push`
7. the effective ceiling is readable by the owner

An A0 group is built by adding an EMBODIED member to a real agent's group —
the case `group.py` says the kind exists to make testable.

**Verified when:** probe is RED before the change, green after, with check 4
green in BOTH runs.

RED baseline, under `/home/ai4science/.venvs/replproto/bin/python3`:

```
RED   1 decide_tool_call refuses A3 under an A0 group
RED   2 SessionDriver refuses A3 under an A0 group
RED   3 SessionDriver refuses unmapped tool under an A0 group
green 4 without a group, A3 still acts (not a blanket deny)
RED   5 a group caps, it never widens
RED   6 shipped A1 group caps a declared A2
RED   7 the effective ceiling is readable
1/7 green
TypeError: decide_tool_call() got an unexpected keyword argument 'group'
```

Note on the environment: system `python3` has no numpy and cannot import the
research registry at all. The interpreter that runs this lane is
`/home/ai4science/.venvs/replproto/bin/python3` (3.12.3, numpy 2.5.2,
pytest 9.1.1). Every number below is from that interpreter.

## Phase 3 — wire it  [DONE]

Executor: headless `claude -p` in the repo. Changes, all in
`ai4science/harness/agents/machine/session.py`:

- new `_capped_by_group(ceiling, group)` — duck-typed on `.capped(str) -> str`.
  No `research_agents` import: `group.py` imports `_CEILING_ORDER` FROM this
  module, so importing back is a cycle. A `.capped()` that raises, or answers
  outside `_CEILING_ORDER`, falls back to the DECLARED ceiling; the result is
  `min(declared, capped)` so a group answering upward is ignored rather than
  obeyed. A malformed group cannot widen authority.
- `decide_tool_call(..., group=None)` applies the cap immediately before
  `lvl = _CEILING_ORDER.get(ceiling, 1)`. It has to land there: every branch
  reads `lvl`, so a cap applied later would bind some decisions and not others.
- `SessionDriver(..., group=None)`, `drive()` passes it through, and
  `effective_ceiling()` reports what is actually in force — same distinction
  `trust.effective_ceiling` draws when it lowers an unearned A3 to A2.

**Verified when:** the probe returns 7/7 with check 4 still green. It did:

```
green 1 decide_tool_call refuses A3 under an A0 group
green 2 SessionDriver refuses A3 under an A0 group
green 3 SessionDriver refuses unmapped tool under an A0 group
green 4 without a group, A3 still acts (not a blanket deny)
green 5 a group caps, it never widens
green 6 shipped A1 group caps a declared A2
green 7 the effective ceiling is readable
7/7 green    PROBE_EXIT=0
```

The executor also added `tests/test_group_ceiling_binds_the_grant.py` (7 tests,
7 passed) — the in-repo freeze of the same rule, control case included. The
verdict above is the probe, which the executor did not write.

## Phase 4 — no regression  [DONE]

**Verified when:** the 8-file lane set still reports 91 passed.

```
........................................................................ [ 79%]
...................                                                      [100%]
```

91 dots, zero F/E. Collected count pinned separately, summing to 91:
board 6 · console_modes 61 · entering_costs_nothing 2 · live_keystrokes 5 ·
never_widens_authority 3 · are_group_agents 4 · group_ceiling 8 ·
tui_mode_label 2.

## Not reached / flagged

- **A pre-existing flake, not caused by this change.**
  `tests/test_tui_mode_label.py::test_leaving_the_mode_takes_the_label_back_off`
  failed on the FIRST baseline run, BEFORE any edit, then passed on reruns 2
  and 3 of the same unchanged tree. It is a PTY timing test. The lane is 91/91
  when it wins the race and 90/91 when it does not. Not fixed this turn.
- `decide_tool_call`'s two production callers — `machine/hook.py:181` and
  `sarsi/operator.py:541` — accept the new `group=` parameter but do not yet
  PASS one, because neither currently resolves a session to a research agent.
  The grant path now consults the group whenever it is given one; handing it
  one from the live hook is the next step, and was not done this turn.
- Per-field member text and anything embodied: not started, as instructed.

---

# PROGRESS — reconciliation against the repo's own docs

Turn opened 2026-08-14 00:56 UTC. Branch `proto/repl-mode-ai4science`, HEAD at
start `1e35776`. Read-and-reconcile turn; no broad implementation.

## R1 — the brief's baseline was stale, and in a way that matters  [REFUTED]

The brief said to read the docs on `feat/repl-modes`, and that GitHub "has not
moved ahead of what you hold". The second half is true of that branch and
misleading about the repo:

```
feat/repl-modes  9d13546   == origin/feat/repl-modes
main             fc26ba6   == origin/main
git merge-base --is-ancestor feat/repl-modes origin/main  -> MERGED
git rev-list --count feat/repl-modes..main                -> 67
```

`feat/repl-modes` is **merged into `main` and 67 commits behind it**. So it is
not a second opinion beside `main`; it is an old copy of it.

I also predicted my branch had drifted from a live branch. Refuted:

```
git merge-base HEAD main   -> fc26ba6   (= main's head)
git rev-list --count HEAD..main -> 0     (proto is not behind main)
git rev-list --count main..HEAD -> 8     (proto = main + 8)
```

`proto` descends from `main`. Its merge-base with `feat/repl-modes` is `9d13546`
only because `main` contains that branch. **The authoritative baseline is
`main`, not `feat/repl-modes`**, and every reconciliation below is against
`main`.

Consequence for the reading list: two of the six named documents
(`docs/superpowers/specs/2026-08-07-machine-agent-first-repl-design.md`,
`docs/superpowers/plans/2026-08-07-repl-modes.md`) do not exist on `main` or on
`proto`. Commits `36b1bd3` and `37221b5` moved 24 planning docs to the private
`singularity` repo because AI4Science is the public pip-install source. Read
them at `/home/ai4science/pwm/singularity/docs/{specs,plans}/`. The 58-vs-34
file count in the brief is that move, not a missing clone.

## R2 — the REPL_MODES.md divergence: my version is right  [SETTLED]

The brief asked which of the two versions is correct. Mine, and `main`'s own
commits are the reason — `main`'s manual contradicts `main`'s own code:

```
main's docs/REPL_MODES.md:3   "Status: on feat/repl-modes, not yet merged."
main's docs/REPL_MODES.md:86  "box itself always shows ❯"

yet main contains:
  b76b604 the tmux hand-off, demonstrated at last
  3e3e577 I4: the mode label reaches the input box, instead of captioning it
  main:tests/test_tui_mode_label.py::test_the_mode_label_reaches_the_input_box
```

`feat/repl-modes` and `main` hold byte-identical copies of this file (both blob
`486dd91`) — `main` landed the behaviour and never updated the manual. The
manual on `main` is stale on three counts: merge status, where the mode label
renders, and whether attach has been demonstrated. `d391063` fixes all three and
cites the evidence rather than asserting it. **Keep the proto version.**

## R3 — where the two specs disagree  [FINDING]

| | singularity spec `2026-08-07` | repo `AI4SCIENCE_ONE_MACHINE_DESIGN.md` |
|---|---|---|
| `sarsi-pwm` | "the **default** for new tasks" (§8) | "`sarsi-pwm` is the **default**" (§1) |
| but also | "piece 3 is explicitly *not* the thing to chase first"; order 1→2→3 (§10) | states the default flatly, with no ordering caveat |

The repo doc states the end state; the singularity spec states the end state
**and** the order, and defers it. They do not contradict on substance, but a
reader of the repo doc alone would build piece 3 next. Taking the spec as
authoritative on sequencing: `sarsi-claude` remains the path to finish first.

Two parity claims from the spec are already met on `proto`, so the spec's
"today" column is itself stale — I predicted a gap here and was **refuted**:

```
spec says tui.py:1012 "esc to stop"     -> actual tui.py:1049 "esc to interrupt"
spec says chat.py:113 "folder you ..."  -> actual chat.py:117 "Is this a project
                                            you created or one you trust"
session.py:159 DRIVABLE_SPECS = {"claude-code", "codex", "unified-LLM"}
```

## R4 — the highest-value gap: the group ceiling is displayed, not granted

Design, "Redesigned: a research agent is a GROUP":

> the group's ceiling is the LOWEST of its members', not the agent's. An agent
> released to A1 whose arm sub-agent could act at A2 has been released to A2 by
> the back door.

Last turn wired `group=` through `decide_tool_call` and `SessionDriver`. **No
production caller passes one.** That is not hypothetical and it does not wait
for robots — it is live on the one research agent the owner can already address:

```
roster: {"id": "computational-imaging", "role": "worker", ...}  — no ceiling key
        -> EVERYDAY_CEILING = "A2"                     (registry.py:30)
group `imaging`.ceiling() = "A1"   (5 acting reasoning members, all A1)
```

All 7 shipped research agents cap at A1 while the roster declares A2. Both
owner-facing renderers print the capped value; the grant path prints nothing and
grants the declared one.

**Verified when:** a probe sarsi-worker wrote — not the executor — shows the
display and the grant path disagreeing.
`state/probe_shipped_group_gap.py` in the sarsi-worker workspace:

```
green 1 the owner is shown an effective ceiling BELOW the declared one
        board.py:126 and research.py:70 both print: declared A2 -> effective A1
GAP   2 the grant path REFUSES the consequential command (it should, at A1)
        hook.py passes no group=; decision='allow' reason='consequential command (A2+)'
green 3 with group= passed, the same call is refused (mechanism is sound)
        decision='ask' reason='matched a consequential pattern'
green 4 CONTROL — with no group, A2 still acts
        decision='allow' reason='consequential command (A2+)'
GAP   5 a production caller passes group= into the grant path
        grep 'group=' in hook.py + operator.py -> no match
3/5 green    PROBE_EXIT=1
VERDICT: the gap is OPEN — the owner is shown A1, the machine acts at A2
```

Check 3 is what makes this a wiring gap and not a design gap: the mechanism is
sound and unreached. Check 4 is the control — any fix that turns it red is too
wide.

The missing link is a resolver from roster id to research agent. The alias it
needs exists in one place only, a tools script:
`tools/check_design_docs.py:51  ALIAS = {"imaging": "computational-imaging"}`.
The cap belongs beside `trust.effective_ceiling` at `hook.py:177-181`, which is
the same shape of cap already applied there.

**Not landed, deliberately.** Wiring this NARROWS what a shipped agent may do
(A2 → A1 for every research agent). That is an authority change, and the
authority kernel is the owner's: proposed here, not accepted.

## Not reached / flagged

- I read `AI4SCIENCE_ONE_MACHINE_DESIGN.md` §11b and §10, the singularity spec
  in full, and the two doc diffs. I did **not** read
  `AI4SCIENCE_USER_MANUAL.md` (414 lines), `CLAUDE_CODE_PARITY.md` in full
  (455), the 1145-line implementation plan beyond its headings, or the other 28
  docs. A gap named only in those is not covered by this report.
- The `hook.py` grant path is the caller I checked. `operator.py:541` also calls
  `decide_tool_call` and also passes no group; I did not trace whether a
  research agent's session reaches it.
- The pre-existing PTY flake in `tests/test_tui_mode_label.py` from last turn is
  still unfixed and still not mine.
