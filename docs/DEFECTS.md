# Named defects

One entry per defect that cost real time to find, with the test that would
catch it again. A defect nobody named is one the next person rediscovers.

Every entry states **how to prove the guard works**: revert the fix, run the
named test, see it fail. A regression test nobody has watched fail is a comment.

---

## D-001 · `sarsi supervise` hung on an attended agent (rc=124)

**Status:** fixed — `b49a216`, 2026-08-06. Guard: `tests/sarsi/test_attended_supervision.py::test_supervising_an_attended_agent_stops_on_the_first_pass`

**Symptom.** `ai4science sarsi supervise computational-imaging tsk_…` returned
nothing and exited **124** — a timeout. It read as a hang, which is how it was
found; it was not one. `supervise` defaults to `--passes 12 --interval 20`, so
it was spending **240 seconds** re-deriving the same fact.

**Cause.** `operator.tick` already returned `Action("attended", …)` — *"this
loop cannot read that interface"* — and `operator.run`'s break list did not
include `attended`. So each of the twelve passes computed the same answer and
slept twenty seconds.

`attended` belongs in that list for a different reason from the rest. The
others (`no-session`, `done`, `paused`, `verified`, `awaiting-grant`) are
states the loop has finished with. `attended` is a fact about the **agent** —
its spec's interface is not one the loop can parse — and no amount of waiting
changes it. The same argument later added `asks-owner`, which repeated six
times on a live run while the work sat finished in the folder.

`over-budget` is deliberately **not** in the list: an owner can raise a budget
from another terminal, so that one really can change under the loop.

**Fix.** One line in `ai4science/harness/agents/sarsi/operator.py`:

```python
if action.kind in ("no-session", "done", "paused", "verified",
                   "awaiting-grant", "attended", "asks-owner"):
    break
```

**Live evidence.** Before: rc=124 after 120s of a 240s budget. After, on grace,
against a running attended session: **5 seconds**, one `attended` action, and
the message names the route — `sarsi check computational-imaging tsk_…`.

**Proving the guard.** In a worktree, not the shared checkout:

```bash
sed -i 's/"awaiting-grant", "attended", "asks-owner"):/"awaiting-grant"):/' \
  ai4science/harness/agents/sarsi/operator.py
python3 -m pytest tests/sarsi/test_attended_supervision.py -q
# expect: AssertionError: ['attended', …] == ['attended']
#         Left contains 11 more items
git checkout -- ai4science/harness/agents/sarsi/operator.py
```

Done on 2026-08-07: the guard fails with exactly that signature, and the
`asks-owner` guard fails alongside it.

**What it should have taught, and did.** A refusal that names no route leaves
the owner with a stopped loop and nowhere to go — the same run left its task
reading `planning` while the finished report sat in the folder. The fix that
matters is not only "stop looping" but "say what to do instead."
