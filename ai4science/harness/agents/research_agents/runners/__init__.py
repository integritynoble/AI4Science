"""Domain runners: the five agents that had no way to compute anything.

`imaging` already had one (`agents/imaging/`) and this is built to its shape —
generate a benchmark from a seed, stage it into the run workspace minus the
answer key, execute the solver there, and score from outside against the key the
sandbox never saw.
"""
from __future__ import annotations

from .common import DomainBenchmark, Verdict, run_domain_task, seed_workspace, seeds_run
from .domains import (BENCHMARKS, CAPSULE, LDCT, MEDPHYS, METHYLAGE, ONCO,
                      SCREENING, benchmark_for)

__all__ = ["DomainBenchmark", "Verdict", "run_domain_task", "seed_workspace",
           "seeds_run", "BENCHMARKS", "benchmark_for", "METHYLAGE",
           "LDCT", "MEDPHYS", "CAPSULE", "SCREENING", "ONCO"]
