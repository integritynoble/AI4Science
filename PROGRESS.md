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
