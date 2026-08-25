"""Certification: each level agent, against the band it claims.

Two directions, because a level claim has two halves and only one of them is
usually checked.

**It holds its own band.** The agent completes tasks at its level, accepted by a
locus that did not perform them.

**It refuses the band above.** This is the half that makes the label mean
something. An agent that attempts everything and reports what it managed is
describing its luck; an agent that declines out-of-band work is stating a
boundary.
"""
from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from ..dli_bench.tasks import GENERATORS
from .bench_solver import COVERED, CarelessSolver, CompetentSolver
from .executor import SolverExecutor
from .levels import BANDS, SPECS, LevelAgent

#: Benchmark classes usable for certification, by band. Only classes whose
#: criteria this package can derive; anything else would need a criterion
#: supplied with the task.
BY_BAND: Dict[str, Tuple[str, ...]] = {
    "T0": ("t0.csv_to_json", "t0.extract_fields"),
    "T1": ("t1.clean_dataset", "t1.request_timeout"),
    "T2": ("t2.pipeline",),
    "T3": ("t3.search_latency",),
}


@dataclass
class Certification:
    level: str
    band: str
    in_band: List[Tuple[str, int, bool]] = field(default_factory=list)
    refusals: List[Tuple[str, bool, str]] = field(default_factory=list)
    executor: str = ""
    note: str = ""

    @property
    def held(self) -> int:
        return sum(1 for _, _, ok in self.in_band if ok)

    @property
    def passed(self) -> bool:
        return (bool(self.in_band) and self.held == len(self.in_band)
                and all(ok for _, ok, _ in self.refusals))

    def report(self) -> str:
        L = ["certification: %s" % self.level,
             "  executor: %s" % (self.executor or "none"),
             "",
             "  holds its own band (%s):" % self.band]
        for key, seed, ok in self.in_band:
            L.append("    %-24s seed %d  %s" % (key, seed, "accepted" if ok else "NOT ACCEPTED"))
        L.append("    %d/%d" % (self.held, len(self.in_band)))
        if self.refusals:
            L += ["", "  refuses the band above:"]
            for band, ok, why in self.refusals:
                L.append("    %-6s %s" % (band, "refused" if ok else "DID NOT REFUSE"))
                if ok and why:
                    L.append("        %s" % why.split(".")[0])
        L += ["", "  verdict: %s" % ("PASS" if self.passed else "FAIL")]
        if self.note:
            L += ["", "  " + self.note]
        return "\n".join(L)


def certify(level: str, seeds: Sequence[int] = (0, 1),
            model: Optional[str] = None, use_claude: bool = True) -> Certification:
    spec = SPECS[level]
    band = spec.highest_band
    keys = BY_BAND.get(band, ())
    cert = Certification(level=level, band=band)

    if use_claude:
        from .claude_executor import ClaudeCodeExecutor, available
        ok, why = available()
        if not ok:
            cert.note = ("the Claude Code CLI is unavailable (%s), so this ran "
                         "with the scripted executor instead" % why)
            use_claude = False
        else:
            cert.executor = "claude-code %s" % why
    if not use_claude:
        cert.executor = cert.executor or "scripted (offline)"

    for key in keys:
        if key not in COVERED:
            continue
        gen = GENERATORS[key]
        for seed in seeds:
            with tempfile.TemporaryDirectory(prefix="dli-cert-") as td:
                td = Path(td)
                spec_t = gen.instantiate(td / "i", seed)
                keyed = td / "keys"
                shutil.move(str(td / "i" / "keyed"), str(keyed))
                if use_claude:
                    from .claude_executor import ClaudeCodeExecutor
                    execs = [ClaudeCodeExecutor(model=model)]
                else:
                    # A level with no retry loop gets its reliability from the
                    # executor, so certifying it offline needs one that is right
                    # first time. Levels that DO retry are certified against the
                    # careless one, because recovering from a detected error is
                    # the capability being claimed.
                    solver = (CarelessSolver(key) if spec.max_attempts > 1
                              else CompetentSolver(key))
                    execs = [SolverExecutor("scripted", solver)]
                agent = LevelAgent(level, execs,
                                   criteria_source=SolverExecutor(
                                       "criteria", CarelessSolver(key)))
                out = agent.run(spec_t.task_id, spec_t.prompt,
                                td / "i" / "work", td / "i" / "store",
                                band=gen.difficulty.band,
                                declared_loss={"value": spec_t.loss.value,
                                               "c_detect": spec_t.loss.c_detect,
                                               "c_undo": spec_t.loss.c_undo,
                                               "c_residual": spec_t.loss.c_residual},
                                class_key=key)
                # Accepted by the harness AND correct by the benchmark. Either
                # alone is not a certification.
                real = gen.verify(td / "i" / "work", keyed).passed
                cert.in_band.append((key, seed, bool(out.accepted and real)))

    above = BANDS[BANDS.index(band) + 1] if BANDS.index(band) + 1 < len(BANDS) else None
    if above:
        agent = LevelAgent(level, [])
        ok, why = agent.would_accept(above)
        cert.refusals.append((above, not ok, why))
    return cert
