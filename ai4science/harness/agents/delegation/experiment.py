"""The experiment: does the harness move the frontier, holding the solver fixed?

This is the falsifiable form of the claim. Two arms, one solver:

  **bare**       -- the solver does the task and hands back its first result,
                    which is how most agents are actually run.
  **harnessed**  -- the same solver inside :class:`DelegationAgent`: the class
                    is read, a check is registered before the work exists, the
                    workspace is snapshotted, another process accepts, and a
                    failure restores and retries.

Nothing about the solver's ability differs between the arms. Both are scored by
the **benchmark's own hidden verifier**, which neither arm can see -- the
harness's self-registered criteria are its own opinion about being done, and the
acceptor of record is still outside.

If the harnessed arm does better, it did so by making the class checkable, not
by getting cleverer. If it does not, the claim is wrong and this prints that.
"""
from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from ..dli_bench.tasks import GENERATORS
from .bench_solver import COVERED, CarelessSolver, StubbornSolver
from .compress import Library
from .executor import CompetenceModel, SolverExecutor
from .loop import DelegationAgent, Outcome


@dataclass
class Row:
    task_id: str
    key: str
    seed: int
    #: benchmark verdict per arm
    bare: bool
    harnessed: bool
    stubborn_bare: bool
    stubborn_harnessed: bool
    #: the number that matters: handed back as done, and wrong
    stubborn_bare_false_completion: bool
    stubborn_harnessed_false_completion: bool
    stubborn_escalated: bool
    routed: bool
    routed_executor: str
    attempts: int
    sigma: float


@dataclass
class Result:
    rows: List[Row] = field(default_factory=list)
    competence_report: str = ""

    def table(self) -> str:
        L = ["%-22s %4s | %-6s %-6s | %-8s %-9s %-6s | %-8s"
             % ("task", "seed", "bare", "harn", "stub-bare", "stub-harn",
                "escal", "routed"),
             "-" * 86]
        for r in self.rows:
            L.append("%-22s %4d | %-6s %-6s | %-8s %-9s %-6s | %-8s"
                     % (r.key, r.seed,
                        "pass" if r.bare else "FAIL",
                        "pass" if r.harnessed else "FAIL",
                        "WRONG" if r.stubborn_bare_false_completion else "fail",
                        "held" if not r.stubborn_harnessed_false_completion else "WRONG",
                        "yes" if r.stubborn_escalated else "no",
                        "pass" if r.routed else "FAIL"))
        return "\n".join(L)

    def summary(self) -> str:
        n = len(self.rows)
        if not n:
            return "no episodes"
        def pc(x):
            return "%d/%d (%.0f%%)" % (x, n, 100.0 * x / n)
        b = sum(r.bare for r in self.rows)
        h = sum(r.harnessed for r in self.rows)
        sb = sum(r.stubborn_bare_false_completion for r in self.rows)
        sh = sum(r.stubborn_harnessed_false_completion for r in self.rows)
        esc = sum(r.stubborn_escalated for r in self.rows)
        rt = sum(r.routed for r in self.rows)
        L = ["", "%d tasks x seeds, one solver family, four arms." % n, "",
             "ARM 1  bare, capable-but-careless        passed %s" % pc(b),
             "ARM 2  harnessed, same solver            passed %s" % pc(h),
             "",
             "  The solver is identical. The difference is that the class was",
             "  made checkable before the work and restartable during it.",
             "",
             "ARM 3  an executor that CANNOT succeed, whatever it is told:",
             "         bare      -- handed back as done, and wrong:  %s" % pc(sb),
             "         harnessed -- handed back as done, and wrong:  %s" % pc(sh),
             "         harnessed -- escalated or refused instead:    %s" % pc(esc),
             "",
             "  This is the arm that matters. A retry loop runs a hopeless",
             "  executor three times and returns the third wrong answer. What",
             "  a delegation harness must never do is report it as done.",
             "",
             "ARM 4  routed over {stubborn, careless}, learning from verdicts",
             "         passed %s" % pc(rt),
             "",
             "  The router starts with no evidence, watches the independent",
             "  verifier reject the stubborn executor, classifies the second",
             "  failure as CAPABILITY rather than bad luck, and moves the work.",
             ]
        if self.competence_report:
            L += ["", "WHAT THE COMPETENCE MODEL LEARNED", "-" * 33, "",
                  self.competence_report,
                  "", "  Built only from independent verdicts. An executor's own",
                  "  account of how it went never enters this table."]
        return "\n".join(L)


def run(seeds: Sequence[int] = (0, 1, 2, 3, 4),
        keys: Sequence[str] = COVERED,
        library_root: Optional[Path] = None) -> Result:
    res = Result()
    lib = Library(library_root) if library_root else None
    competence = CompetenceModel()          # shared, so ARM 4 accumulates

    for key in keys:
        gen = GENERATORS[key]
        for seed in seeds:
            with tempfile.TemporaryDirectory(prefix="dl-exp-") as td:
                td = Path(td)
                loss = None

                def fresh(sub: str):
                    root = td / sub
                    spec = gen.instantiate(root, seed)
                    return root, spec

                # ARM 1 -- bare: one pass, no check, hand it back.
                r1, spec = fresh("bare")
                loss = {"value": spec.loss.value, "c_detect": spec.loss.c_detect,
                        "c_undo": spec.loss.c_undo, "c_residual": spec.loss.c_residual}
                CarelessSolver(key).attempt(None, r1 / "work", ())
                bare = gen.verify(r1 / "work", r1 / "keyed").passed

                # ARM 2 -- harnessed, same solver.
                r2, spec = fresh("harnessed")
                out2 = DelegationAgent(CarelessSolver(key), library=lib,
                                       max_attempts=3).run(
                    spec.task_id, spec.prompt, r2 / "work", r2 / "store",
                    declared_loss=loss, class_key=key)
                harnessed = gen.verify(r2 / "work", r2 / "keyed").passed

                # ARM 3a -- an executor that cannot succeed, run bare.
                r3, spec = fresh("stub_bare")
                StubbornSolver(key).attempt(None, r3 / "work", ())
                sb = gen.verify(r3 / "work", r3 / "keyed").passed

                # ARM 3b -- the same executor, harnessed.
                r4, spec = fresh("stub_harnessed")
                out4 = DelegationAgent(StubbornSolver(key), max_attempts=3).run(
                    spec.task_id, spec.prompt, r4 / "work", r4 / "store",
                    declared_loss=loss, class_key=key)
                sh = gen.verify(r4 / "work", r4 / "keyed").passed

                # ARM 4 -- routed over both, learning from the verdicts.
                r5, spec = fresh("routed")
                executors = [SolverExecutor("stubborn", StubbornSolver(key), cost=1.0),
                             SolverExecutor("careless", CarelessSolver(key), cost=1.2)]
                out5 = DelegationAgent(executors=executors, competence=competence,
                                       max_attempts=4).run(
                    spec.task_id, spec.prompt, r5 / "work", r5 / "store",
                    declared_loss=loss, class_key=key)
                routed = gen.verify(r5 / "work", r5 / "keyed").passed

                res.rows.append(Row(
                    task_id=spec.task_id, key=key, seed=seed,
                    bare=bare, harnessed=harnessed,
                    stubborn_bare=sb, stubborn_harnessed=sh,
                    # bare has no acceptance step at all, so anything wrong it
                    # returns is returned as done.
                    stubborn_bare_false_completion=not sb,
                    stubborn_harnessed_false_completion=(out4.accepted and not sh),
                    stubborn_escalated=bool(out4.escalations) or not out4.accepted,
                    routed=routed,
                    routed_executor=(out5.route[-1][0] if out5.route else ""),
                    attempts=out2.attempts, sigma=out2.sigma))

    res.competence_report = competence.report()
    return res


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", default="0-4")
    ap.add_argument("--library", default=None,
                    help="keep compressions here, so a class solved once "
                         "arrives checkable next time")
    a = ap.parse_args(argv)
    seeds: List[int] = []
    for part in a.seeds.split(","):
        if "-" in part:
            x, y = part.split("-", 1)
            seeds.extend(range(int(x), int(y) + 1))
        elif part.strip():
            seeds.append(int(part))
    r = run(seeds, library_root=Path(a.library) if a.library else None)
    print(r.table())
    print(r.summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
