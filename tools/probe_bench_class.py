"""Probe one dli_bench class against a live executor, at several seeds.

    python3 tools/probe_bench_class.py t5.hidden_law "" 0,9,11,17
    python3 tools/probe_bench_class.py t4.mini_language haiku 0,1,2,3

Reports whatever metrics the class defines rather than assuming ``accuracy``:
a graded class exists to grade, and the sealed class reports extrapolation
error against a baseline instead.

**It also prints the executor's exit note, and that is not decoration.** A run
the harness killed and a run that answered wrongly produce the same verdict --
"produced no output", "did not state the mechanism" -- and are distinguishable
only by why the episode ended. A published result was retracted because that
line was missing: a discovery episode cut off at 2400 seconds was recorded as a
capability failure, and passes comfortably when given time to finish.

Two operational notes paid for the same way. Discovery episodes need a limit of
two hours or so; they have been observed running 1350-4983 seconds, and a limit
shorter than the task corrupts the measurement silently. And streams are
network-bound rather than CPU-bound, so several can run in parallel on one box.
"""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai4science.harness.agents.dli_bench.catalog import GENERATORS
from ai4science.harness.agents.delegation.claude_executor import ClaudeCodeExecutor
from ai4science.harness.agents.delegation.contract import Contract, Reading

TASK = sys.argv[1] if len(sys.argv) > 1 else "t4.mini_language"
MODEL = sys.argv[2] if len(sys.argv) > 2 else None
SEEDS = [int(x) for x in (sys.argv[3].split(",") if len(sys.argv) > 3 else ["0", "1"])]

g = GENERATORS[TASK]
ex = ClaudeCodeExecutor(name=MODEL or "frontier", model=MODEL, timeout=7200)

for seed in SEEDS:
    root = Path(tempfile.mkdtemp(prefix="probe-"))
    spec = g.instantiate(root, seed)
    c = Contract(task_id=spec.task_id,
                 verifiability=Reading(4, "hidden cases decide it exactly"),
                 reversibility=Reading(4, "a scratch workspace, thrown away"),
                 statement=spec.prompt)
    run = ex.execute(c, root / "work", [])
    v = g.verify(root / "work", root / "keyed")
    # Not every class reports accuracy -- the sealed one reports extrapolation
    # error against a baseline -- so print whatever it does report.
    metrics = " ".join("%s=%.3f" % (k, x) for k, x in sorted(v.metrics.items()))
    # The executor note is printed because a timed-out episode and a genuinely
    # empty delivery look identical in the verdict, and one of them is not a
    # measurement. A contaminated point already cost a wrong conclusion here.
    print("%-10s seed %d | %-4s %s  (%s) [%s]" % (
        MODEL or "frontier", seed, "pass" if v.passed else "FAIL",
        metrics, "; ".join(v.reasons)[:150], run.note[-90:]), flush=True)
