"""Acceptance, performed somewhere other than where the work was done.

The requirement is on locus, not on species: the acceptor may be a machine, and
may not be the same machine. So this runs the registered criteria in a **separate
process**, with:

  * the register verified by hash before anything runs, because a criterion the
    solver edited is not a criterion;
  * a working directory that is a *copy* of the deliverables, so a check cannot
    be made to pass by the act of running it;
  * no environment inherited from the solver, so a check cannot be satisfied by
    something the solver left in the process.

What it returns says how much it establishes. ``unknown_false_pass`` is the
honest and common answer, and it is reported rather than rounded to zero.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .criterion import Criterion, CriterionRegister
from .interpreter import find as find_python


@dataclass
class Acceptance:
    """The verdict of a locus that did not do the work."""

    accepted: bool
    results: List[Tuple[str, bool, str]] = field(default_factory=list)
    chain_ok: bool = True
    chain_note: str = ""
    sigma: float = 0.0
    locus: str = "alpha2"
    unknown_false_pass: int = 0

    def report(self) -> str:
        L = ["acceptance: %s (locus %s)"
             % ("ACCEPTED" if self.accepted else "NOT ACCEPTED", self.locus)]
        if not self.chain_ok:
            L.append("  REGISTER BROKEN: %s" % self.chain_note)
        for name, ok, detail in self.results:
            L.append("  %-28s %s" % (name, "pass" if ok else "FAIL"))
            if not ok and detail:
                L.append("      %s" % detail.strip().splitlines()[-1][:160])
        L.append("  sigma (criteria the agent wrote): %.2f" % self.sigma)
        L.append("  criteria with no false-pass estimate: %d" % self.unknown_false_pass)
        return "\n".join(L)


def _run_check(check: str, cwd: Path, timeout: int, n: int = 0) -> Tuple[bool, str]:
    """Run one criterion in ``cwd``, in its own process.

    Three forms. ``pycode:`` carries Python source, which is **written to a file
    and executed** rather than passed through a shell -- an earlier version put
    it in ``python3 -c "..."`` and every multi-line criterion arrived as a
    syntax error, so every check failed and the harness looked like it was
    working because a blind retry happened to fix the task. A verifier that
    cannot pass a correct result is worse than none: it reports failure
    regardless of the work, which is indistinguishable from strictness.
    """
    env = {"PATH": os.environ.get("PATH", ""), "HOME": str(cwd),
           "PYTHONDONTWRITEBYTECODE": "1"}
    if check.startswith("pycode:"):
        py, why = find_python()
        if py is None:
            return False, "UNDECIDABLE: %s" % why
        f = cwd / ("_criterion_%d.py" % n)
        f.write_text(check[len("pycode:"):], encoding="utf-8")
        cmd = [py, str(f)]
    elif check.startswith("python:"):
        _, mod, fn = check.split(":", 2)
        py, why = find_python()
        if py is None:
            return False, "UNDECIDABLE: %s" % why
        code = ("import importlib,sys;m=importlib.import_module(%r);"
                "sys.exit(0 if m.%s() else 1)" % (mod, fn))
        cmd = [py, "-c", code]
    else:
        cmd = ["bash", "-lc", check]
    try:
        r = subprocess.run(cmd, cwd=str(cwd), env=env, capture_output=True,
                           text=True, timeout=timeout)
        return r.returncode == 0, ((r.stdout or "") + (r.stderr or ""))[-800:]
    except subprocess.TimeoutExpired:
        return False, "check timed out after %ds" % timeout
    except OSError as e:
        return False, "check could not be run: %s" % e


def accept(register: CriterionRegister, workspace: Path,
           timeout: int = 120, locus: str = "alpha2") -> Acceptance:
    """Run every registered criterion, in a copy, in another process."""
    ok, note = register.verify_chain()
    criteria = register.criteria()
    if not ok:
        return Acceptance(accepted=False, chain_ok=False, chain_note=note,
                          sigma=register.sigma(), locus=locus)
    if not criteria:
        # No criterion is not a pass. It is an unaccepted result.
        return Acceptance(accepted=False, chain_ok=True,
                          chain_note="nothing was registered, so nothing accepts this",
                          sigma=0.0, locus=locus)

    results: List[Tuple[str, bool, str]] = []
    with tempfile.TemporaryDirectory(prefix="acceptor-") as td:
        sandbox = Path(td) / "work"
        shutil.copytree(workspace, sandbox, dirs_exist_ok=True)
        for i, c in enumerate(criteria):
            passed, detail = _run_check(c.check, sandbox, timeout, n=i)
            results.append((c.name, passed, detail))

    return Acceptance(
        accepted=all(p for _, p, _ in results),
        results=results, chain_ok=True, sigma=register.sigma(), locus=locus,
        unknown_false_pass=sum(1 for c in criteria if "unknown" in c.covers.lower()
                               or "not check" in c.covers.lower()),
    )
