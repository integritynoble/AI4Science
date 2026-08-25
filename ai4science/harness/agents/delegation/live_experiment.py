"""The same four-arm question, with a real executor: Claude Code.

Everything about the design is unchanged from :mod:`.experiment`. Only the thing
inside the ``attempt`` box differs, which is the point -- if the harness matters,
it matters for a capable executor too, and if it does not, that shows here.

Two differences forced by using a real executor rather than a script.

**The answer key is moved out of the tree before the run.** A benchmark instance
builds ``work/`` and ``keyed/`` as siblings, and an executor with a shell can
read ``../keyed``. The scripted solvers could not; this one could. So the key is
relocated before any executor starts, and the executor additionally runs in a
standalone copy with no parent to walk up into. Two independent barriers,
because an executor that can read the answer will eventually read it and the
measurement would then be of the directory layout.

**Runs cost time and money.** The arms are therefore reported per episode as
they complete, and the sample is small and stated as such. A result from six
episodes is a reading, not a rate.
"""
from __future__ import annotations

import json
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from ..dli_bench.tasks import GENERATORS
from .bench_solver import COVERED, CarelessSolver
from .claude_executor import ClaudeCodeExecutor, available
from .executor import CompetenceModel, SolverExecutor
from .loop import DelegationAgent, Outcome


@dataclass
class LiveRow:
    key: str
    seed: int
    bare_passed: bool
    harnessed_passed: bool
    attempts: int
    accepted: bool
    agreed: bool          # harness verdict == benchmark verdict
    bare_seconds: float
    harn_seconds: float
    escalated: bool
    note: str = ""


@dataclass
class LiveResult:
    rows: List[LiveRow] = field(default_factory=list)
    executor: str = "claude-code"
    version: str = ""

    def table(self) -> str:
        L = ["%-22s %4s | %-6s %-6s | %4s %-8s %-9s | %6s %6s"
             % ("task", "seed", "bare", "harn", "att", "accepted", "agreed",
                "bare_s", "harn_s"),
             "-" * 92]
        for r in self.rows:
            L.append("%-22s %4d | %-6s %-6s | %4d %-8s %-9s | %6.0f %6.0f"
                     % (r.key, r.seed,
                        "pass" if r.bare_passed else "FAIL",
                        "pass" if r.harnessed_passed else "FAIL",
                        r.attempts, "yes" if r.accepted else "no",
                        "yes" if r.agreed else "NO", r.bare_seconds, r.harn_seconds))
        return "\n".join(L)

    def summary(self) -> str:
        n = len(self.rows)
        if not n:
            return "no episodes"
        b = sum(r.bare_passed for r in self.rows)
        h = sum(r.harnessed_passed for r in self.rows)
        fixed = sum(1 for r in self.rows if r.harnessed_passed and not r.bare_passed)
        broke = sum(1 for r in self.rows if r.bare_passed and not r.harnessed_passed)
        false_accept = sum(1 for r in self.rows if r.accepted and not r.harnessed_passed)
        silent = sum(1 for r in self.rows if not r.bare_passed)
        held = sum(1 for r in self.rows if not r.harnessed_passed and not r.accepted)
        bt = sum(r.bare_seconds for r in self.rows)
        ht = sum(r.harn_seconds for r in self.rows)
        L = ["", "executor: %s  %s" % (self.executor, self.version),
             "%d episodes. Small; a reading, not a rate." % n, "",
             "  bare       %d/%d passed" % (b, n),
             "  harnessed  %d/%d passed" % (h, n),
             "",
             "  turned around by the harness: %d" % fixed,
             "  broken by the harness:        %d" % broke,
             "",
             "  wrong work returned as done:",
             "    bare       %d/%d  (there is no acceptance step, so every"
             % (silent, n),
             "                    failure is returned as a completed task)",
             "    harnessed  %d/%d  (accepted, and the benchmark disagrees)"
             % (false_accept, n),
             "    held back  %d     (not accepted, so not reported as done)" % held,
             "",
             "  time: bare %.0fs total, harnessed %.0fs total" % (bt, ht),
             "        the harness costs wall-clock, and buys the acceptance step",
             ]
        disagree = [r for r in self.rows if not r.agreed]
        if disagree:
            L += ["", "  the harness's criteria disagreed with the benchmark on "
                  "%d episode(s):" % len(disagree)]
            for r in disagree:
                L.append("    %s#%d: harness %s, benchmark %s"
                         % (r.key, r.seed, "accepted" if r.accepted else "rejected",
                            "passed" if r.harnessed_passed else "failed"))
            L += ["  That gap is the harness's own false-pass/false-fail rate and",
                  "  is the number it must report about itself."]
        return "\n".join(L)


def _isolate_key(root: Path, keys_dir: Path, tag: str) -> Path:
    """Move ``keyed/`` somewhere the executor has no path to."""
    keys_dir.mkdir(parents=True, exist_ok=True)
    dst = keys_dir / tag
    if dst.exists():
        shutil.rmtree(dst)
    shutil.move(str(root / "keyed"), str(dst))
    return dst


def run(seeds: Sequence[int] = (0,), keys: Sequence[str] = COVERED,
        model: Optional[str] = None, timeout: int = 420,
        verbose: bool = True) -> LiveResult:
    ok, version = available()
    if not ok:
        raise RuntimeError("claude CLI unavailable: %s" % version)
    res = LiveResult(version=version)

    for key in keys:
        gen = GENERATORS[key]
        for seed in seeds:
            with tempfile.TemporaryDirectory(prefix="dl-live-") as td:
                td = Path(td)
                keys_dir = td / "keys"

                # ARM 1 -- bare: one pass, no acceptance step, hand it back.
                r1 = td / "bare"
                spec = gen.instantiate(r1, seed)
                k1 = _isolate_key(r1, keys_dir, "bare")
                ex1 = ClaudeCodeExecutor(model=model, timeout=timeout)
                t0 = time.time()
                from .contract import read_task
                c1 = read_task(spec.task_id, spec.prompt, r1 / "work")
                ex1.execute(c1, r1 / "work", ())
                bare_s = time.time() - t0
                bare = gen.verify(r1 / "work", k1).passed

                # ARM 2 -- harnessed: same executor, inside the loop.
                r2 = td / "harnessed"
                spec = gen.instantiate(r2, seed)
                k2 = _isolate_key(r2, keys_dir, "harnessed")
                ex2 = ClaudeCodeExecutor(model=model, timeout=timeout)
                # Criteria come from the harness, not from the executor: the
                # thing being judged does not write the judgement.
                criteria_source = SolverExecutor("criteria", CarelessSolver(key))
                agent = DelegationAgent(
                    executors=[ex2], competence=CompetenceModel(), max_attempts=3)
                agent.executors.insert(0, _CriteriaOnly(criteria_source))
                t0 = time.time()
                out: Outcome = agent.run(
                    spec.task_id, spec.prompt, r2 / "work", r2 / "store",
                    declared_loss={"value": spec.loss.value,
                                   "c_detect": spec.loss.c_detect,
                                   "c_undo": spec.loss.c_undo,
                                   "c_residual": spec.loss.c_residual},
                    class_key=key)
                harn_s = time.time() - t0
                harnessed = gen.verify(r2 / "work", k2).passed

                row = LiveRow(
                    key=key, seed=seed, bare_passed=bare,
                    harnessed_passed=harnessed, attempts=out.attempts,
                    accepted=out.accepted, agreed=(out.accepted == harnessed),
                    bare_seconds=bare_s, harn_seconds=harn_s,
                    escalated=bool(out.escalations))
                res.rows.append(row)
                if verbose:
                    print("%-22s seed %d | bare %-4s harnessed %-4s | %d attempt(s) "
                          "| %.0fs / %.0fs"
                          % (key, seed, "pass" if bare else "FAIL",
                             "pass" if harnessed else "FAIL", out.attempts,
                             bare_s, harn_s), flush=True)
    return res


class _CriteriaOnly:
    """Supplies criteria and never executes.

    Present so the register is filled by something other than the executor
    without that thing also being a candidate to do the work. The router never
    picks it because :meth:`execute` refuses.
    """

    name = "criteria-source"

    def __init__(self, inner) -> None:
        self.inner = inner

    def capabilities(self):
        return {"name": self.name, "cost": 1e9, "kind": "criteria-only"}

    def propose_criteria(self, contract, workspace):
        return self.inner.propose_criteria(contract, workspace)

    def execute(self, contract, workspace, feedback):
        raise RuntimeError("the criteria source does not execute work")


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", default="0")
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--model", default=None)
    ap.add_argument("--timeout", type=int, default=420)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    seeds: List[int] = []
    for part in a.seeds.split(","):
        if "-" in part:
            x, y = part.split("-", 1)
            seeds.extend(range(int(x), int(y) + 1))
        elif part.strip():
            seeds.append(int(part))
    r = run(seeds, keys=(a.only or COVERED), model=a.model, timeout=a.timeout)
    print()
    print(r.table())
    print(r.summary())
    if a.out:
        Path(a.out).write_text(r.table() + "\n" + r.summary() + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
