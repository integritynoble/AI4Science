"""Run one frozen model across the standardized ladder and report the curve.

    python -m ai4science.harness.agents.delegation.run_ladder --seeds 0-1

The model, the tool grant, the task classes, the seeds, the verifiers and the
intervention budget are identical at every rung. **Only the harness changes.**
That is what makes a difference between rungs attributable to the mechanism the
rung added, and it is the condition v1.2 §14.1 asks for when it says the ladder
must be standardized.

Governance-only intervention throughout: the human authorises and supplies no
cognition, so every rung is measured at H1 and the surface is a slice rather
than a full T x H grid. Stated rather than glossed -- a one-column surface
cannot show the frontier moving leftward.
"""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from ..dli_bench.tasks import GENERATORS
from .bench_solver import COVERED, CarelessSolver
from .claude_executor import ClaudeCodeExecutor, available
from .codex_executor import CodexExecutor
from .codex_executor import available as codex_available
from .contract import read_task
from .executor import CompetenceModel, SolverExecutor
from .ladder import LADDER, BY_NAME, Curve, RungResult
from .levels import CriteriaOnly
from .loop import DelegationAgent

BUDGET = "H1"


def _make_executor(family: str, model, timeout):
    """The executor family under test. Both adapters obey the same protocol."""
    if family == "codex":
        return CodexExecutor(model=model, timeout=timeout)
    return ClaudeCodeExecutor(model=model, timeout=timeout)


def _run_rung(rung, key: str, seed: int, model: Optional[str], timeout: int,
              family: str = "claude") -> Tuple[bool, bool, int, float]:
    """(verified success, returned-as-done-and-wrong, attempts, seconds)."""
    gen = GENERATORS[key]
    with tempfile.TemporaryDirectory(prefix="hsc-") as td:
        td = Path(td)
        spec = gen.instantiate(td / "i", seed)
        keyed = td / "keys"
        shutil.move(str(td / "i" / "keyed"), str(keyed))
        ws = td / "i" / "work"
        ex = _make_executor(family, model, timeout)
        t0 = time.time()

        if not rung.acceptance:
            # HG0: one attempt, nothing accepts it, whatever it made is handed
            # back. Scored from outside, which is what a leaderboard does.
            ex.execute(read_task(spec.task_id, spec.prompt, ws), ws, ())
            ok = gen.verify(ws, keyed).passed
            return ok, (not ok), 1, time.time() - t0

        agent = DelegationAgent(
            executors=[CriteriaOnly(SolverExecutor("criteria", CarelessSolver(key))), ex],
            competence=CompetenceModel(), max_attempts=rung.max_attempts)
        if not rung.routes:
            agent.router.executors = list(agent.executors)
        out = agent.run(
            spec.task_id, spec.prompt, ws, td / "i" / "store",
            declared_loss={"value": spec.loss.value, "c_detect": spec.loss.c_detect,
                           "c_undo": spec.loss.c_undo, "c_residual": spec.loss.c_residual},
            class_key=key)
        ok = gen.verify(ws, keyed).passed
        # A false completion is work the harness ACCEPTED that the benchmark
        # rejects. Work it declined is held back, not returned as done.
        return ok, bool(out.accepted and not ok), out.attempts, time.time() - t0


def run(seeds: Sequence[int], keys: Sequence[str], model: Optional[str],
        timeout: int, rungs: Sequence[str], verbose: bool = True,
        family: str = "claude") -> Curve:
    ok, version = (codex_available() if family == "codex" else available())
    if not ok:
        raise RuntimeError("%s CLI unavailable: %s" % (family, version))
    curve = Curve(model="%s / model=%s" % (version, model or "default"))

    for name in rungs:
        rung = BY_NAME[name]
        res = RungResult(rung=name, episodes=0)
        by_band: Dict[str, List[bool]] = {}
        for key in keys:
            band = GENERATORS[key].difficulty.band
            for seed in seeds:
                good, false_done, attempts, secs = _run_rung(
                    rung, key, seed, model, timeout, family)
                by_band.setdefault(band, []).append(good)
                res.episodes += 1
                res.attempts += attempts
                res.seconds += secs
                res.false_completions += int(false_done)
                res.held_back += int((not good) and (not false_done))
                if verbose:
                    print("%-4s %-22s seed %d | %-4s | %d attempt(s) %.0fs"
                          % (name, key, seed, "pass" if good else "FAIL",
                             attempts, secs), flush=True)
        res.surface = {(b, BUDGET): (sum(v) / len(v)) for b, v in by_band.items()}
        curve.rungs.append(res)
        if verbose:
            print("  -> %s  A_DI %.3f  HLIS_DI %.1f\n" % (name, res.a_di, res.hlis_di),
                  flush=True)
    return curve


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", default="0")
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--rungs", nargs="*", default=[r.name for r in LADDER])
    ap.add_argument("--model", default=None)
    ap.add_argument("--timeout", type=int, default=420)
    ap.add_argument("--family", choices=("claude", "codex"), default="claude")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    seeds: List[int] = []
    for part in a.seeds.split(","):
        if "-" in part:
            x, y = part.split("-", 1)
            seeds.extend(range(int(x), int(y) + 1))
        elif part.strip():
            seeds.append(int(part))
    c = run(seeds, a.only or list(COVERED), a.model, a.timeout, a.rungs,
            family=a.family)
    print()
    print(c.report())
    if a.out:
        Path(a.out).write_text(c.report() + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
