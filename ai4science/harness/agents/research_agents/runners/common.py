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

import hashlib
import shutil
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .. import observations

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
class Parameter:
    """One knob a method exposes, and the range it may be turned through.

    **The benchmark declares these, never the agent.** An agent that could add a
    parameter could add one that reads the answer key, or one that widens the
    split — so the space is fixed by whoever wrote the benchmark, and a proposal
    naming anything outside it is refused rather than clamped. Clamping would
    silently accept an illegal move and score it.
    """
    name: str
    low: float
    high: float
    default: float
    integer: bool = False
    #: Walk this knob multiplicatively rather than in equal absolute steps.
    #:
    #: It does NOT change the declared space — same low, same high — only how a
    #: search crosses it. That distinction matters here: the space is the
    #: benchmark's to declare and the traversal is the search's business.
    #:
    #: Set it when the range spans orders of magnitude. A linear step across
    #: [0.0001, 5000] is ~2500 wide, so every value below 1 is reachable only by
    #: clamping to the floor, and a search "exploring" that range never sees the
    #: region where the parameter actually does something. Requires low > 0.
    log: bool = False
    #: What turning it up actually does, in the field's terms. Written for the
    #: person reading the search log, who has to judge whether the winner is
    #: sensible or merely lucky.
    means: str = ""

    def __post_init__(self) -> None:
        if self.log and self.low <= 0:
            raise ValueError("%s: log stepping needs low > 0, got %g"
                             % (self.name, self.low))

    def clamp(self, v: float) -> float:
        v = max(self.low, min(self.high, float(v)))
        return float(int(round(v))) if self.integer else v

    def check(self, v: float) -> None:
        if not (self.low <= float(v) <= self.high):
            raise ValueError("%s=%r is outside [%g, %g]"
                             % (self.name, v, self.low, self.high))


@dataclass(frozen=True)
class Observed:
    """One metric this benchmark produces, and the self-model dimension it is a
    measurement of."""
    #: A key in that agent's SelfModel.
    dimension: str
    #: A key in the dict this benchmark's score() returns.
    metric: str
    #: What the number is and is not, in the field's terms. It ends up inside
    #: the evidence line, where the person reading the self-model sees it next
    #: to the figure.
    note: str = ""


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
    #: Seeds that generate genuinely DIFFERENT problems for this benchmark.
    #:
    #: Empty means every seed does. Set it where the seed maps into a finite
    #: corpus and repeats: low-dose CT has four patients, so seeds 0 and 4 are
    #: byte-identical, and a night that used both was validating on its own
    #: search set. Declaring the usable seeds here means a caller cannot get it
    #: wrong; `check_seed_independence` is the check that catches it if one does.
    usable_seeds: Tuple[int, ...] = ()
    #: The corpus this benchmark reads, if it reads one. None means the data is
    #: generated rather than measured — and a result from generated data is
    #: evidence about a method, never about the world.
    corpus: Optional[str] = None
    #: The method's tunable knobs. Empty means the method is fixed and the
    #: agent has nothing to search — which is honest for some domains.
    parameters: Tuple[Parameter, ...] = ()
    #: The metric a search is allowed to optimise, named by the benchmark.
    #:
    #: Declared because the first autonomous run picked it alphabetically and
    #: spent a night optimising `active_fraction` — a property of the library,
    #: not of the method. A search needs to be told what better means; letting
    #: it infer that from a dict ordering is how an agent ends up improving
    #: something nobody wanted improved.
    objective: str = ""
    objective_higher_is_better: bool = True
    #: Metrics that must not get worse while the objective improves. The
    #: trade the field refuses to make: fidelity at the cost of detectability,
    #: enrichment at the cost of the property baseline.
    guardrails: Tuple[str, ...] = ()
    #: Which of those are LOWER-is-better. Named explicitly because the default
    #: was silently higher-is-better, which inverted the check for exactly the
    #: metrics that matter most: a spinal cord dose RISING read as fine and a
    #: cord dose falling read as a breach. A guardrail pointing the wrong way is
    #: worse than none — it rejects the candidates that spare the organ.
    guardrail_lower_is_better: Tuple[str, ...] = ()
    #: Which of this benchmark's metrics measure which self-model dimensions.
    #:
    #: **Declared by the benchmark, never by the agent.** The drug-design
    #: charter's `also_never` already puts `benchmark`, `metric`,
    #: `actives_decoys_set`, `split` and `hit_criteria` out of the agent's
    #: reach; a self-model that could choose which number describes it could
    #: choose the flattering one, and would have every reason to. Empty means
    #: this benchmark's numbers stay out of any self-model — which is the honest
    #: default for a benchmark whose mapping nobody has run.
    observes: Tuple[Observed, ...] = ()

    def guardrail_directions(self) -> Dict[str, bool]:
        low = set(self.guardrail_lower_is_better)
        unknown = low - set(self.guardrails)
        if unknown:
            raise ValueError("%s: %s is marked lower-is-better but is not a "
                             "guardrail" % (self.agent, sorted(unknown)))
        return {g: (g not in low) for g in self.guardrails}

    def defaults(self) -> Dict[str, float]:
        return {p.name: p.default for p in self.parameters}

    def check_params(self, params: Dict[str, float]) -> Dict[str, float]:
        """Refuse anything the benchmark did not declare, or out of range."""
        known = {p.name: p for p in self.parameters}
        unknown = set(params) - set(known)
        if unknown:
            raise ValueError(
                "%s: %s is not a declared parameter of this benchmark. The "
                "space is the benchmark's, not the agent's."
                % (self.agent, sorted(unknown)))
        for k, v in params.items():
            known[k].check(v)
        out = self.defaults()
        out.update({k: float(v) for k, v in params.items()})
        return out

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


def child_env(base: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """The environment a spawned generator or solver must run under.

    A child is started with `cwd` set to its workspace, and that is exactly what
    takes `ai4science` off its import path: the parent usually has it there
    because the parent's working directory is the repository. The child then
    falls back to whatever copy is installed on the machine.

    The loud version of that is a `ModuleNotFoundError` when the installed copy
    predates this subpackage. The quiet version is the one to design against:
    on a merely *stale* install the data is **generated by old code and scored
    by new code**, and nothing in the result says so.

    So the child is told where the parent's package lives rather than left to
    find one. Whatever the caller already put on `PYTHONPATH` is kept — it is a
    list, and a caller who set one meant it.
    """
    env = dict(os.environ if base is None else base)
    root = str(Path(__file__).resolve().parents[5])
    here = [q for q in env.get("PYTHONPATH", "").split(os.pathsep) if q]
    if root not in here:
        here.insert(0, root)
    env["PYTHONPATH"] = os.pathsep.join(here)
    return env


#: Generated benchmarks are cached here, keyed by agent, seed and generator
#: source. Outside the repo, because data is not source.
_CACHE_ROOT = Path(os.environ.get(
    "AI4SCIENCE_SEED_CACHE",
    str(Path.home() / ".ai4science" / "cache" / "seed")))


def _seed_key(bench: DomainBenchmark, seed: int) -> str:
    """What the generated data depends on: the seed and the generator's source.

    Hashing the source rather than a version string means nobody has to remember
    to bump anything — editing a generator invalidates its cache by definition.
    """
    h = hashlib.sha256()
    h.update(("%s|%d|" % (bench.agent, seed)).encode())
    for f in sorted(bench.files(), key=lambda q: q.name):
        h.update(f.name.encode())
        h.update(f.read_bytes())
    return h.hexdigest()[:24]


def seed_workspace(bench: DomainBenchmark, ws: Path, *, seed: int,
                   params: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    """Generate the problem, deterministically, including the answer key.

    `params` are the method's knobs, validated against the benchmark's declared
    space and written where the solver reads them. A solver with no params.json
    uses its own defaults, so an unparameterised domain keeps working."""
    ws = Path(ws)
    (ws / "code").mkdir(parents=True, exist_ok=True)
    if bench.parameters:
        chosen = bench.check_params(params or {})
        (ws / "params.json").write_text(json.dumps(chosen, indent=1))
    elif params:
        # Refusing beats dropping. A caller that passes knobs to a benchmark
        # declaring none has a wrong belief about what it is tuning, and
        # silently ignoring them lets a whole parameter sweep return identical
        # numbers that look like a flat response surface. That happened: five
        # settings of the RT planner produced the same figure to four decimals
        # and read as "the objective weights do not matter".
        raise ValueError(
            "%s declares no parameters, so %s cannot be applied. The space is "
            "the benchmark's; declare it there before tuning it."
            % (bench.agent, sorted(params)))
    for p in bench.files():
        (ws / "code" / p.name).write_bytes(p.read_bytes())

    # Generation is deterministic in the seed and does NOT read params, so every
    # candidate in a search regenerates byte-identical data. Measured: 19.2s per
    # generation for screening, 4.3s for LDCT — about an hour of a full night
    # spent re-deriving what it already had.
    #
    # The key is what the data actually depends on: the agent, the seed, and the
    # SOURCE of every generator file. Change a generator and the key changes, so
    # a stale cache cannot serve data the current code would not produce. That
    # matters more than the speed: a benchmark quietly served from an older
    # generator is the exact failure this system is built to refuse.
    key = _seed_key(bench, seed)
    hit = _CACHE_ROOT / bench.agent / key
    if (hit / "meta.json").exists():
        shutil.copytree(hit / "data", ws / "data", dirs_exist_ok=True)
        return json.loads((hit / "meta.json").read_text())

    out = subprocess.run([sys.executable, "code/generate.py", "--workspace", ".",
                          "--seed", str(seed)],
                         cwd=str(ws), capture_output=True, text=True,
                         env=child_env())
    if out.returncode:
        raise RuntimeError("%s: benchmark generation failed:\n%s"
                           % (bench.agent, out.stderr[-2000:]))
    meta = json.loads(out.stdout or "{}")
    if os.environ.get("AI4SCIENCE_NO_SEED_CACHE") != "1" and (ws / "data").is_dir():
        try:
            tmp = hit.with_name(hit.name + ".tmp%d" % os.getpid())
            if tmp.exists():
                shutil.rmtree(tmp, ignore_errors=True)
            tmp.mkdir(parents=True, exist_ok=True)
            shutil.copytree(ws / "data", tmp / "data")
            (tmp / "meta.json").write_text(json.dumps(meta))
            tmp.replace(hit)          # atomic: a reader never sees a half-copy
        except Exception:
            shutil.rmtree(tmp, ignore_errors=True)   # a cache miss is not an error
    return meta


def run_domain_task(bench: DomainBenchmark, *, client, workspace: Path,
                    seed: int = 42, capability_profile: str = "A1",
                    interaction_mode: str = "I2",
                    params: Optional[Dict[str, float]] = None,
                    agent_id: Optional[str] = None) -> Dict[str, Any]:
    """Seed, stage (minus the key), execute, then score from outside.

    Deliberately the same sequence as `run_imaging_task`. A second shape here
    would mean two things to audit."""
    workspace = Path(workspace)
    meta = seed_workspace(bench, workspace, seed=seed, params=params)

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

    # The one place a number reaches the agent's self-model. Not wrapped in a
    # try/except on purpose: a run that could not be recorded is a run the
    # report will go on calling `unmeasured`, and a traceback here is cheaper
    # than a self-model that is quietly a night out of date. A failed run never
    # reaches this line — the two returns above take it — and `record_run`
    # refuses a rejected verdict and non-default params itself.
    used_params = bench.check_params(params or {}) if bench.parameters else {}
    recorded = observations.record_run(bench, seed=seed, metrics=metrics,
                                       verdict=verdict, params=used_params,
                                       run_workspace=str(run_ws))
    return {"status": "delivered" if verdict.passed else "rejected",
            "agent": bench.agent, "seed": seed, "benchmark": meta,
            "real": bench.real, "provenance": bench.provenance(),
            "params": used_params,
            "withheld": withheld, "metrics": metrics, "verdict": verdict,
            "observed": [r["dimension"] for r in recorded],
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
