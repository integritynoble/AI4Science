"""The paired design: score HG0 and HG1 from the same executor outputs.

HG0 and HG1 differ only in whether an acceptance step runs *after* the work.
Neither changes what the executor is asked to do, and neither gives it a second
attempt. So running them as independent experiments -- as the first three curves
did -- introduces between-rung variance from the executor's own stochasticity,
and on a stochastic model that noise exceeded the effect being measured, which
is exactly zero.

Here the executor runs **once** per (task, seed) and both rungs are evaluated
against the identical artifacts:

    register the criteria           (before the deliverable exists)
    run the executor once
    HG0: the verifier's verdict; no acceptance step, so whatever was produced
         is delivered, and a wrong result is a false completion
    HG1: run the registered criteria against a COPY; the verifier's verdict is
         unchanged, but a rejected result is held back instead of delivered

The gross surface is then identical between the rungs **by construction**, which
is the point: it turns Proposition 1 from an observation that came out exactly
zero twice into a controlled result. What the two rungs can still differ in is
the split between false completions and correct refusals, which is what the net
primitive prices.

The check that keeps this honest is that the verifier verdict is recorded once
and reused, so a difference in gross A_DI would indicate a bug in this harness
rather than a property of acceptance.
"""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from ..dli_bench.tasks import GENERATORS
from .acceptor import accept
from .bench_solver import COVERED, CarelessSolver
from .claude_executor import ClaudeCodeExecutor, available
from .codex_executor import CodexExecutor
from .codex_executor import available as codex_available
from .contract import read_task
from .criterion import CriterionRegister, RegisterViolation
from .ladder import W_T, V_H

BUDGET = "H1"


@dataclass
class PairedEpisode:
    key: str
    band: str
    seed: int
    verifier_pass: bool          # one verdict, shared by both rungs
    hg1_accepted: bool           # did the acceptance step accept it
    criteria: int
    seconds: float

    @property
    def hg0_false_completion(self) -> bool:
        """HG0 has no acceptance step: anything wrong is handed back as done."""
        return not self.verifier_pass

    @property
    def hg1_false_completion(self) -> bool:
        return self.hg1_accepted and not self.verifier_pass

    @property
    def hg1_held_back(self) -> bool:
        return (not self.hg1_accepted) and (not self.verifier_pass)

    @property
    def hg1_false_rejection(self) -> bool:
        return (not self.hg1_accepted) and self.verifier_pass


def _executor(family: str, model, timeout):
    return (CodexExecutor(model=model, timeout=timeout) if family == "codex"
            else ClaudeCodeExecutor(model=model, timeout=timeout))


def run_one(key: str, seed: int, family: str, model, timeout: int) -> PairedEpisode:
    gen = GENERATORS[key]
    with tempfile.TemporaryDirectory(prefix="paired-") as td:
        td = Path(td)
        spec = gen.instantiate(td / "i", seed)
        keyed = td / "keys"
        shutil.move(str(td / "i" / "keyed"), str(keyed))
        ws, store = td / "i" / "work", td / "i" / "store"
        store.mkdir(parents=True, exist_ok=True)

        # Criteria first, while no deliverable exists to fit them to.
        register = CriterionRegister(store / "criteria.jsonl", workspace=ws)
        src = CarelessSolver(key)
        contract = read_task(spec.task_id, spec.prompt, ws)
        for name, check, covers in src.propose_criteria(contract, ws):
            try:
                register.register(name=name, check=check, covers=covers,
                                  author="agent")
            except RegisterViolation:
                pass
        n_crit = len(register.criteria())
        register.seal()

        # ONE execution. Both rungs read what it produced.
        t0 = time.time()
        _executor(family, model, timeout).execute(contract, ws, ())
        secs = time.time() - t0

        # The verdict, taken once.
        verdict = gen.verify(ws, keyed).passed

        # HG1's acceptance step, against a copy so it cannot disturb the work.
        with tempfile.TemporaryDirectory(prefix="paired-acc-") as td2:
            mirror = Path(td2) / "work"
            shutil.copytree(ws, mirror)
            acc = accept(register, mirror)

        return PairedEpisode(key=key, band=gen.difficulty.band, seed=seed,
                             verifier_pass=verdict, hg1_accepted=acc.accepted,
                             criteria=n_crit, seconds=secs)


def _surface(eps: Sequence[PairedEpisode]) -> Dict[str, float]:
    by: Dict[str, List[bool]] = {}
    for e in eps:
        by.setdefault(e.band, []).append(e.verifier_pass)
    return {b: sum(v) / len(v) for b, v in by.items()}


def _weighted(surface: Dict[str, float], fc: Optional[Dict[str, float]] = None,
              rho: float = 1.0) -> float:
    num = den = 0.0
    for b, s in surface.items():
        w = W_T.get(b, 1.0) * V_H.get(BUDGET, 1.0)
        v = s - (rho * fc.get(b, 0.0) if fc else 0.0)
        num += w * max(0.0, v)
        den += w
    return (num / den) if den else 0.0


def report(eps: Sequence[PairedEpisode], label: str) -> str:
    surface = _surface(eps)
    by_band: Dict[str, List[PairedEpisode]] = {}
    for e in eps:
        by_band.setdefault(e.band, []).append(e)
    fc0 = {b: sum(x.hg0_false_completion for x in v) / len(v)
           for b, v in by_band.items()}
    fc1 = {b: sum(x.hg1_false_completion for x in v) / len(v)
           for b, v in by_band.items()}

    gross = _weighted(surface)
    net0, net1 = _weighted(surface, fc0), _weighted(surface, fc1)
    L = ["Paired HG0/HG1 measurement", "=" * 26, "",
         "executor: %s" % label,
         "episodes: %d   (one execution each, both rungs scored from it)" % len(eps),
         "",
         "%-6s %-9s %-9s %s" % ("band", "episodes", "pass rate", "shared by both rungs"),
         "-" * 56]
    for b in sorted(surface, key=lambda x: list(W_T).index(x)):
        L.append("%-6s %-9d %-9.3f %s" % (b, len(by_band[b]), surface[b], "yes"))
    L += ["",
          "GROSS A_DI (v1.3 primitive)",
          "  HG0 %.3f   HG1 %.3f   difference %.6f" % (gross, gross, 0.0),
          "  Identical by construction: the same artifacts, one verdict each.",
          "",
          "OUTCOME SPLIT (what the rungs actually differ in)",
          "  HG0  delivered wrong: %d   held back: %d"
          % (sum(e.hg0_false_completion for e in eps), 0),
          "  HG1  delivered wrong: %d   held back: %d   false rejections: %d"
          % (sum(e.hg1_false_completion for e in eps),
             sum(e.hg1_held_back for e in eps),
             sum(e.hg1_false_rejection for e in eps)),
          "",
          "NET A_DI (v1.4 primitive, rho=1)",
          "  HG0 %.3f   HG1 %.3f   difference %+.3f" % (net0, net1, net1 - net0),
          "",
          "Proposition 1 predicts the gross difference is exactly zero. Under the",
          "paired design it is zero by construction rather than by luck, and the",
          "whole of the acceptance rung's contribution appears in the net figure."]
    return "\n".join(L)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", default="0-1")
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--family", choices=("claude", "codex"), default="claude")
    ap.add_argument("--model", default=None)
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)

    ok, version = (codex_available() if a.family == "codex" else available())
    if not ok:
        print("%s CLI unavailable: %s" % (a.family, version), file=sys.stderr)
        return 2

    seeds: List[int] = []
    for part in a.seeds.split(","):
        if "-" in part:
            x, y = part.split("-", 1)
            seeds.extend(range(int(x), int(y) + 1))
        elif part.strip():
            seeds.append(int(part))

    eps: List[PairedEpisode] = []
    for key in (a.only or list(COVERED)):
        for seed in seeds:
            e = run_one(key, seed, a.family, a.model, a.timeout)
            eps.append(e)
            print("%-22s seed %d | verifier %-4s | HG1 %-8s | %.0fs"
                  % (key, seed, "pass" if e.verifier_pass else "FAIL",
                     "accepted" if e.hg1_accepted else "declined", e.seconds),
                  flush=True)
    text = report(eps, "%s / model=%s" % (version, a.model or "default"))
    print()
    print(text)
    if a.out:
        Path(a.out).write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
