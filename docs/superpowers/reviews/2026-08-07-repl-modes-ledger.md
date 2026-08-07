# REPL modes — execution ledger

The subagent-driven run of
[`../plans/2026-08-07-repl-modes.md`](../plans/2026-08-07-repl-modes.md):
one implementer per task, a review after each, and a fix loop when a review
found something.

Kept because the git history records *what changed* and this records **what was
caught and why**. The working copy lives in a git-ignored scratch directory that
is deleted when the plan finishes, so without this the review findings — three
of which were defects in the plan I wrote — would vanish with it.

Two entries are worth reading even if the rest is bookkeeping:

* **Task 5** — the drift guard I specified was hollow. It compared two
  hand-typed literals and never read `console.py`, so a tenth action kind would
  have left it green while that kind fell through the loop unhandled. Exactly
  the defect its own docstring claimed to prevent.
* **Task 6** — `console.route` had no `command` branch, so every harness slash
  (`/help`, `/model`, `/do`, `/exit`) was swallowed before reaching the real
  chain. No test caught it because the test fixture stubbed the resolver with a
  dict that could never return `"command"` — a fixture that cannot produce the
  failing input cannot find the bug.

---

# SDD ledger — plan: docs/superpowers/plans/2026-08-07-repl-modes.md
Task 1: implemented (commits 4b7df40..28c6d25) — review dispatched
Task 1: minor (deferred): test_a_mode_is_frozen uses pytest.raises(Exception); dataclasses.FrozenInstanceError is the precise one. Low risk — an unfrozen Mode raises nothing, so the test still fails loudly on the regression that matters.
Task 1: complete (commits 4b7df40..28c6d25, review clean)
Task 2: implemented (commits 28c6d25..6c0feb6) — review dispatched
Task 2: review — spec OK, quality CHANGES NEEDED. Open (Important):
  (a) Mode.name uses the raw token, not `detail` (the canonical lower-cased id) — /Sarsi-Worker enters Mode(name="Sarsi-Worker") and later deps["session_of"](mode.name) will not match the registry key. Fix: name=detail in the roster and task branches (NOT the `both` branch — detail is a sentence there).
  (c) test_a_spec_switches_... asserts "say" or "enter" — accepts either, catches neither; and the spec branch sets no agent= on the Action, leaving repl no structured target.
Task 2: carried to Task 5/6 (not a fix here): repl.looks_like_command/_COMMAND_WORD duplicate console._is_slash. Cycle-forced; repl should delegate to console when repl imports it.
Task 2: minor (deferred): _is_slash's "/" and "." checks are unreachable after the regex; `rest` is unused until Task 4.
Task 2: fix round deferred — Task 3 implementer is live in the same function (route). Fix after it lands.
Task 3: implemented (commits 6c0feb6..1d7b5d3, 22 tests) — review pending until Task 2 fix lands
Task 2: fix round 1/5 (2 addressed, 0 open — canonicalization, loose spec test + agent=detail; commits 1d7b5d3..8fdd95f)
Task 2: complete (commits 28c6d25..8fdd95f, review clean after 1 fix round)
Task 4: implemented (commits 8fdd95f..844bbb2, 28 tests) — review dispatched
Task 3: minor (deferred, WORTH FIXING): console.py comment at the pending branch claims the reordering risk is "silently creates a task". Reviewer traced the counterfactual: create only ever originates INSIDE the pending block, so the real risk of reordering is silently DROPPING the pending goal without telling the user. The ordering decision is right; the stated reason is wrong. In this codebase a rationale comment that names the wrong failure mode misleads the next reader.
Task 3: minor (deferred): task-mode branch shipped without a same-commit test; coverage arrived in 844bbb2.
Task 3: complete (commits 6c0feb6..1d7b5d3, review clean)
Task 4: minor (deferred): rest.strip() at console.py:119 is redundant — rest was stripped at line 102.
Task 4: note: the "no session vs cannot be read" phrasing is rhetorical, not two code paths. Reviewer searched for a second sentinel and found none; session_of's contract has one falsy value, so `if not session:` is complete.
Task 4: complete (commits 8fdd95f..844bbb2, review clean)
Task 5: implemented (commits 844bbb2..05b9a54, 4 + 58 + 50 tests green) — review dispatched
PLAN DEFECT (mine, confirmed): Task 5's "Produces" line promised repl._perform(action, state) -> bool. No step in Task 5 defines it and no test exercises it; Task 6 inlines the dispatch into the loop instead. The implementer implemented Step 3 as written and flagged the gap rather than inventing the symbol — the right call. Task 6's dispatch must say _perform does not exist.
Task 5: review — spec OK, Approved, but 2 Important open (fix round deferred: Task 6 implementer is live in the same two files):
  (1) suggest's "quiet on a tie" invariant is stated in comments and pinned by NO test. Reviewer exercised it by hand (empty demand, no match, no registry) — behaviour correct, coverage absent.
  (2) test_every_action_kind_console_can_return_is_handled_by_repl is a near-tautology, and it is MY plan code. `produced` is a hand-copied literal, so it can only fail when two hand-maintained literals disagree; it never touches console.route. If console grows a 10th kind the test stays GREEN while the kind falls through unhandled — precisely the defect class its own docstring claims to guard. Fix: derive `produced` from console.py (regex over Action("...") call sites, mirroring known_commands) or collect .kind by exercising route's branches.
Task 5: minor (deferred): _guide leaks a raw AttributeError text to the user when task.session is a non-dict; _session_of guards this with isinstance, _guide does not.
Task 5: minor (deferred): find_task and suggest have no live caller until Task 6 consumes them — Task 6's review should confirm both are wired.
Task 6: implemented (commits 05b9a54..61db73a; 63 targeted + 1945 sarsi/machine, 0 failed) — review dispatched
Task 5: fix round 1/5 (2 addressed, 0 open — derived drift guard + floor test + suggest quiet-on-tie; commits 61db73a..e193a7d). Guard verified live by controller: simulated repl dropping "attach" and the guard reports it.
Task 5: complete (commits 844bbb2..e193a7d, review clean after 1 fix round; probe evidence verified by re-reviewer AND controller)
