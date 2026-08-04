"""The shape every research-agent runner shares.

Copied in spirit from `agents/imaging/`, which had it right first:

  * the benchmark is **generated** deterministically from a seed, so a run is
    reproducible without shipping data;
  * the solver is **staged into the run workspace** and executed there;
  * the **answer key is never staged** — `_NEVER_STAGE` in the imaging agent,
    `DomainBenchmark.answer_key` here. A solver that cannot read the ground
    truth cannot copy it into its own output and pass a reference-free judge;
  * **scoring happens outside the sandbox**, against the withheld key, in this
    process — never by code the solver could have written.

That last pair is the design's "the benchmark is outside the agent's reach as a
file permission, not a policy", made executable. Everything else here is
plumbing around it.

Each domain supplies a `DomainBenchmark` and a `judge` that knows what its field
counts as a defensible result. The judges differ on purpose: the whole point of
six agents is that "better" means six different things, and a shared scorer
would quietly make them one.
"""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

PAYLOAD = Path(__file__).parent / "payload"


@dataclass(frozen=True)
class Verdict:
    """What the domain judge concluded, and why."""
    passed: bool
    reasons: Tuple[str, ...]
    metrics: Dict[str, float]

    provenance: str = ""

    def report(self) -> str:
        L = ["verdict: %s" % ("PASS" if self.passed else "FAIL")]
        if self.provenance:
            L.append("  %s" % self.provenance)
        for k, v in sorted(self.metrics.items()):
            L.append("  %-26s %.6g" % (k, v))
        for r in self.reasons:
            L.append("  - %s" % r)
        return "\n".join(L)


@dataclass(frozen=True)
class DomainBenchmark:
    """One field's runnable problem."""

    agent: str
    goal: str
    #: Module under payload/ holding generate.py and run_solver.py.
    package: str
    #: Files the solver produces that the judge reads.
    deliverables: Tuple[str, ...]
    #: Paths that must NEVER reach the sandbox. The ground truth, always.
    answer_key: Tuple[str, ...]
    #: Given the seeded workspace (with the key) and the run workspace (without),
    #: return the metrics. Runs here, not in the sandbox.
    score: Callable[[Path, Path], Dict[str, float]]
    #: Given metrics, decide. One per field; see the module docstring.
    judge: Callable[[Dict[str, float]], Verdict]
    criteria: Tuple[str, ...] = ()
    #: The corpus this benchmark reads, if it reads one. None means the data is
    #: generated rather than measured — and a result from generated data is
    #: evidence about a method, never about the world.
    corpus: Optional[str] = None

    @property
    def real(self) -> bool:
        return self.corpus is not None

    def provenance(self) -> str:
        if not self.real:
            return ("SYNTHETIC — generated, not measured. This exercises the "
                    "field's characteristic failure and says nothing about real "
                    "%s data." % self.agent)
        from . import corpus as _c
        c = _c.ALL[self.corpus]
        return "real data: %s (%s)" % (c.title, c.source)

    def files(self) -> List[Path]:
        d = PAYLOAD / self.package
        return sorted(p for p in d.iterdir() if p.is_file() and p.suffix == ".py")


def seed_workspace(bench: DomainBenchmark, ws: Path, *, seed: int) -> Dict[str, Any]:
    """Generate the problem, deterministically, including the answer key."""
    ws = Path(ws)
    (ws / "code").mkdir(parents=True, exist_ok=True)
    for p in bench.files():
        (ws / "code" / p.name).write_bytes(p.read_bytes())
    out = subprocess.run([sys.executable, "code/generate.py", "--workspace", ".",
                          "--seed", str(seed)],
                         cwd=str(ws), capture_output=True, text=True)
    if out.returncode:
        raise RuntimeError("%s: benchmark generation failed:\n%s"
                           % (bench.agent, out.stderr[-2000:]))
    return json.loads(out.stdout or "{}")


def run_domain_task(bench: DomainBenchmark, *, client, workspace: Path,
                    seed: int = 42, capability_profile: str = "A1",
                    interaction_mode: str = "I2",
                    agent_id: Optional[str] = None) -> Dict[str, Any]:
    """Seed, stage (minus the key), execute, then score from outside.

    Deliberately the same sequence as `run_imaging_task`. A second shape here
    would mean two things to audit."""
    workspace = Path(workspace)
    meta = seed_workspace(bench, workspace, seed=seed)

    run = client.open_run(bench.goal, capability_profile,
                          {"actions": 4}, interaction_profile=interaction_mode,
                          agent_id=agent_id)
    run_ws = Path(run["workspace_path"])
    withheld: List[str] = []
    for p in sorted(workspace.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(workspace).as_posix()
        if rel in bench.answer_key:
            withheld.append(rel)
            continue
        client.stage_input(run["run_id"], rel, p.read_bytes())

    exec_out = client.sandbox_execute(run["run_id"],
                                      ["python3", "code/run_solver.py",
                                       "--workspace", "."])
    if exec_out.get("is_error"):
        return {"status": "failed", "agent": bench.agent, "withheld": withheld,
                "why": (exec_out.get("stderr") or "")[-1500:],
                "run_workspace": str(run_ws)}

    missing = [d for d in bench.deliverables if not (run_ws / d).exists()]
    if missing:
        return {"status": "failed", "agent": bench.agent, "withheld": withheld,
                "why": "deliverables missing: %s" % ", ".join(missing),
                "run_workspace": str(run_ws)}

    # Scored here, against the key the sandbox never saw.
    metrics = bench.score(workspace, run_ws)
    verdict = bench.judge(metrics)
    verdict = Verdict(verdict.passed, verdict.reasons, verdict.metrics,
                      provenance=bench.provenance())
    return {"status": "delivered" if verdict.passed else "rejected",
            "agent": bench.agent, "seed": seed, "benchmark": meta,
            "real": bench.real, "provenance": bench.provenance(),
            "withheld": withheld, "metrics": metrics, "verdict": verdict,
            "run_workspace": str(run_ws), "criteria": list(bench.criteria)}


def seeds_run(bench: DomainBenchmark, *, client_factory, workspace_root: Path,
              seeds: Tuple[int, ...]) -> List[Dict[str, Any]]:
    """The same benchmark over a fixed seed set. Every seed is returned —
    filtering happens nowhere in this function, because the one thing the design
    is most worried about is a caller keeping the run that looked good."""
    out = []
    for s in seeds:
        ws = Path(workspace_root) / ("seed-%d" % s)
        out.append(run_domain_task(bench, client=client_factory(s),
                                   workspace=ws, seed=s))
    return out
