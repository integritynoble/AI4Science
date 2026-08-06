"""The two functions every research agent has.

    1. the ordinary one   a person asks for something and the agent works it,
                          through the governed session runtime, like any other
                          sarsi agent. Plan → execute → verify → repair.

    2. the autonomous one  it does research on its own — owner-set tasks, a
                          benchmark, or the charter it shipped with — without
                          being asked each time.

**Function 1 does not need the switch.** A person asking for help is not the
agent deciding to spend their money, and requiring the autonomous permission for
ordinary work would make the off switch mean "the agent is useless" instead of
"the agent does not act unasked". So `run_user_task` runs with the switch off,
and `autonomous_round` refuses without it.

**Function 2 stops; it does not ask.** Three things end it — the owner turning
the switch off, the budget running out, and the field map running dry — and none
of them produces a request for more. An agent that could ask would be asking at
3 a.m., of whoever is least equipped to say no.

**The three ledgers are never summed.** An agent that wrote its own benchmark,
passed it, and counted the pass toward its record would have published its own
reputation, so owner-set work, benchmark scores and self-directed research are
three lines and stay three lines.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .budget import BudgetExhausted
from .improvement import Improvement, SeedResult, no_change
from .runners import DomainBenchmark, run_domain_task

OWNER_SET, BENCHMARK, SELF_DIRECTED = "owner_set", "benchmark", "self_directed"


# ------------------------------------------------------------------ ledgers

class Ledgers:
    """Three records that are never added together."""

    def __init__(self, agent: str):
        self.agent = agent
        self._rows: Dict[str, List[Dict[str, Any]]] = {
            OWNER_SET: [], BENCHMARK: [], SELF_DIRECTED: []}

    def record(self, kind: str, row: Dict[str, Any]) -> Dict[str, Any]:
        if kind not in self._rows:
            raise KeyError("no ledger %r — the three are fixed on purpose" % kind)
        row = dict(row, at=time.time())
        self._rows[kind].append(row)
        return row

    def of(self, kind: str) -> List[Dict[str, Any]]:
        return list(self._rows[kind])

    def total(self):
        """Deliberately absent. There is no single number, and offering one
        would be offering the agent its own reputation."""
        raise NotImplementedError(
            "%s: owner-set work, benchmark scores and self-directed research are "
            "three lines and are never one number — an agent that could sum them "
            "could pass its own exam and count it" % self.agent)

    def report(self) -> str:
        L = ["%s — three ledgers, never summed:" % self.agent]
        for kind in (OWNER_SET, BENCHMARK, SELF_DIRECTED):
            rows = self._rows[kind]
            passed = sum(1 for r in rows if r.get("passed"))
            L.append("  %-14s %d run%s, %d passed"
                     % (kind, len(rows), "" if len(rows) == 1 else "s", passed))
        return "\n".join(L)


# -------------------------------------------------- 1. the ordinary function

@dataclass
class DomainPlanner:
    """Run the solver; on a repairable failure, run it again.

    The same shape as `ReferenceImagingPlanner`, which is the reference for
    every agent's ordinary path. It carries no domain knowledge — a domain that
    needs a cleverer planner supplies one."""

    max_repairs: int = 2
    _attempts: int = 0

    def next_step(self, state):
        from ai4science.harness.runtime.pev import PlanStep
        if self._attempts > self.max_repairs:
            return PlanStep(summary="deliver", command=[], done=True)
        return PlanStep(summary="run the domain solver",
                        command=["python3", "code/run_solver.py",
                                 "--workspace", "."],
                        action_type="sandbox_exec")

    def replan(self, state, verdict) -> None:
        self._attempts += 1


class DomainVerifier:
    """The field's own judge, wrapped for the runtime.

    Scores host-side against the withheld answer key — the sandbox never had it,
    and a verifier that read its evidence from inside the sandbox would be
    judging whatever the solver chose to write."""

    def __init__(self, bench: DomainBenchmark, seed_ws: Path, run_ws: Path):
        self.bench, self.seed_ws, self.run_ws = bench, Path(seed_ws), Path(run_ws)
        self.last: Optional[Dict[str, float]] = None

    def check(self, result: dict, contract):
        from ai4science.harness.runtime.verifier import Verdict as RtVerdict
        missing = [d for d in self.bench.deliverables
                   if not (self.run_ws / d).exists()]
        if result.get("exit_code") not in (0, None) or missing:
            return RtVerdict(complete=False, repairable=True,
                             evidence={"missing": missing,
                                       "exit_code": result.get("exit_code")})
        metrics = self.bench.score(self.seed_ws, self.run_ws)
        verdict = self.bench.judge(metrics)
        self.last = metrics
        return RtVerdict(complete=verdict.passed, repairable=not verdict.passed,
                         evidence={"metrics": metrics,
                                   "reasons": list(verdict.reasons)})


def run_user_task(agent, bench: DomainBenchmark, *, client, store, task_id: str,
                  workspace: Path, seed: int = 42, interaction_mode: str = "I2",
                  capability_profile: str = "A1", max_repairs: int = 2,
                  ledgers: Optional[Ledgers] = None, on_ask=None) -> Dict[str, Any]:
    """Function 1. A person asked; the agent works it through the runtime.

    Runs with the autonomous switch **off** — that is the point of the
    distinction."""
    from ai4science.harness.runtime.contract import compile_contract
    from ai4science.harness.runtime.pev import run_task
    from .runners.common import seed_workspace

    workspace = Path(workspace)
    seed_workspace(bench, workspace, seed=seed)
    run = client.open_run(bench.goal, capability_profile, {"actions": max_repairs + 3},
                          interaction_profile=interaction_mode)
    run_ws = Path(run["workspace_path"])
    for p in sorted(workspace.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(workspace).as_posix()
        if rel in bench.answer_key:
            continue
        client.stage_input(run["run_id"], rel, p.read_bytes())

    contract = compile_contract(
        objective=bench.goal, capability_profile=capability_profile,
        interaction_mode=interaction_mode,
        deliverables=list(bench.deliverables),
        success_criteria=list(bench.criteria),
        approval_required_for=["publish", "spend", "deploy"])
    verifier = DomainVerifier(bench, workspace, run_ws)
    out = run_task(run_id=run["run_id"], contract=contract, client=client,
                   planner=DomainPlanner(max_repairs=max_repairs),
                   verifier=verifier, store=store, task_id=task_id, on_ask=on_ask)
    out["metrics"] = verifier.last
    out["agent"] = agent.name if hasattr(agent, "name") else str(agent)
    if ledgers is not None:
        ledgers.record(OWNER_SET, {"task": task_id, "goal": bench.goal,
                                   "passed": out.get("status") == "delivered",
                                   "metrics": verifier.last})
    return out


# ------------------------------------------------ 2. the autonomous function

@dataclass
class Round:
    """One night's work on one question."""
    agent: str
    claim: Optional[str]
    metric: str
    spent: float
    improvement: Optional[Improvement] = None
    outcome: Dict[str, Any] = field(default_factory=dict)
    #: The raw search result: every candidate tried, and the validation numbers.
    search: Dict[str, Any] = field(default_factory=dict)
    stopped: str = ""

    def report(self) -> str:
        L = ["%s — %s" % (self.agent, self.claim or "no open claim")]
        if self.improvement is not None:
            L.append(self.improvement.report())
        elif self.outcome:
            L.append("  %s" % self.outcome.get("why", ""))
        if self.stopped:
            L.append("  stopped: %s" % self.stopped)
        return "\n".join(L)


def _measure_only(agent, bench: DomainBenchmark, *, client_factory,
                  workspace_root: Path, seeds, cost_per_seed: float,
                  ledgers, claim, budget) -> "Round":
    """Run the benchmark across the seed set and record it. No search.

    Every seed is run and every seed is recorded — the loop stops if the owner
    turns the switch off part-way or the budget will not cover the next one, and
    neither asks for more."""
    spent = 0.0
    metrics = []
    for s in seeds:
        if not agent.switch.on:
            return Round(agent.name, claim.statement if claim else None,
                         bench.objective or "measurement", spent,
                         stopped="the owner turned it off mid-round")
        if not budget.would_fit(cost_per_seed):
            return Round(agent.name, claim.statement if claim else None,
                         bench.objective or "measurement", spent,
                         stopped="the budget would not cover the next seed "
                                 "(%.3g needed, %.3g left) — it stops rather "
                                 "than asking" % (cost_per_seed, budget.remaining()))
        budget.spend(cost_per_seed, what="seed %d of %s" % (s, bench.agent))
        spent += cost_per_seed
        out = run_domain_task(bench, client=client_factory(s),
                              workspace=Path(workspace_root) / ("m%d" % s), seed=s)
        metrics.append(out.get("metrics") or {})
        if ledgers is not None:
            ledgers.record(BENCHMARK, {"seed": s, "params": {},
                                       "passed": out.get("status") == "delivered",
                                       "metrics": out.get("metrics")})
    r = Round(agent.name, claim.statement if claim else None,
              bench.objective or "measurement", spent)
    r.outcome = no_change(
        agent.name,
        because="%s declares no tunable parameters, so this night measured "
                "rather than searched: %d seeds run and recorded"
                % (bench.agent, len(metrics)))
    if ledgers is not None:
        ledgers.record(SELF_DIRECTED,
                       {"claim": r.claim, "metric": r.metric, "spent": spent,
                        "params": {}, "passed": False})
    return r


def seed_data_classes(bench, seeds, workspace_root) -> Dict[int, str]:
    """Hash the data each seed actually generates.

    A seed is a request for a different problem; it is not a guarantee of one.
    Every benchmark here maps its seed into a FINITE corpus — a patient index, a
    site permutation, a video split — so past some width, more seeds means the
    same data again under a new number. Measured: low-dose CT produces 4 distinct
    datasets across 16 seeds, medical physics 8, reverse aging 7.

    That is the same failure as the seed that did nothing and reported p = 0,
    only quieter: the duplicates are real data, so nothing looks wrong.
    """
    from .runners.common import seed_workspace
    import hashlib, tempfile
    out: Dict[int, str] = {}
    for s in seeds:
        ws = Path(workspace_root) / ("cls%d" % s)
        seed_workspace(bench, ws, seed=s)
        h = hashlib.sha256()
        for f in sorted((ws / "data").rglob("*")):
            if f.is_file():
                h.update(f.name.encode())
                h.update(f.read_bytes())
        out[s] = h.hexdigest()[:16]
    return out


def check_seed_independence(bench, search_seeds, validation_seeds, workspace_root):
    """Refuse a round whose validation set is not actually held out.

    Two ways it fails, both silent:
      * a validation seed generates the SAME data as a search seed — the winner
        was selected on the set it is then validated on;
      * two validation seeds generate the same data — the paired test counts one
        measurement twice, so the spread is understated and the p-value is not
        what it says it is.

    Returns None when the split is sound, or a sentence saying why it is not.
    """
    cls = seed_data_classes(bench, tuple(search_seeds) + tuple(validation_seeds),
                            workspace_root)
    searched = {cls[s] for s in search_seeds}
    leaked = [s for s in validation_seeds if cls[s] in searched]
    if leaked:
        return ("validation seeds %s generate the same data as the search seeds — "
                "the winner would be validated on what it was selected on. %s "
                "produces only %d distinct problems across these seeds."
                % (leaked, bench.agent, len(set(cls.values()))))
    seen: Dict[str, int] = {}
    dupes = []
    for s in validation_seeds:
        if cls[s] in seen:
            dupes.append((seen[cls[s]], s))
        else:
            seen[cls[s]] = s
    if dupes:
        return ("validation seeds %s are the same problem: %d seeds but %d "
                "distinct, so the paired test would count a measurement more "
                "than once and report a spread it did not measure"
                % (dupes, len(validation_seeds), len(seen)))
    return None


def autonomous_round(agent, bench: DomainBenchmark, *, client_factory,
                     workspace_root: Path, seeds: Sequence[int] = (0, 1, 2, 3, 4),
                     metric: str = "", cost_per_seed: float = 0.5,
                     ledgers: Optional[Ledgers] = None,
                     candidate: str = "search",
                     validation_seeds: Optional[Sequence[int]] = None,
                     rounds: int = 2) -> Round:
    """One round: propose variants, score them paired against the incumbent,
    and validate the winner on seeds it was never selected on.

    The first version of this scored the incumbent against itself and reported a
    delta of zero every time — it ran a night correctly and could not have found
    anything. `search.run_search` is the missing half."""
    from .search import run_search

    budget = agent.switch.require_on()          # raises PermissionError when off
    claim = agent.field_map.next_work()
    seeds = tuple(seeds)
    # Where the benchmark declares which seeds generate different problems, use
    # them. A caller asking for six seeds from a benchmark with four distinct
    # problems is asking for two duplicates, and getting them silently is how a
    # validation set stops being held out.
    usable = tuple(getattr(bench, "usable_seeds", ()) or ())
    if usable:
        # The declared set IS the seed set for this benchmark — it is the widest
        # set of genuinely different problems it has. Intersecting it with a
        # caller's range(6) would quietly throw away the distinct problems that
        # happen to sit at higher seed numbers, which is the opposite of the
        # point: reverse aging's are at 9 and 12.
        seeds = usable
    if validation_seeds is None:
        # Validation gets the LARGER share. The search only has to rank
        # candidates; the validation set has to carry a claim, and the first
        # searching night validated on two seeds and produced a spread wider
        # than the effect it was measuring.
        cut = max(1, len(seeds) // 3)
        search_seeds, validation_seeds = seeds[:cut], seeds[cut:]
    else:
        validation_seeds = tuple(validation_seeds)
        search_seeds = tuple(s for s in seeds if s not in validation_seeds) or seeds
    # A seed set is only as wide as the distinct problems behind it. Checked
    # before anything is spent, because the failure is invisible afterwards: the
    # numbers look fine and the held-out set quietly is not one.
    bad = check_seed_independence(bench, search_seeds, validation_seeds,
                                  Path(workspace_root) / "seedcheck")
    if bad:
        return Round(agent.name, claim.statement if claim else None,
                     bench.objective or "measurement", 0.0,
                     stopped="the seed set does not hold a validation set apart: "
                             + bad)

    spent = {"n": 0.0}

    def spend(n_runs: int) -> None:
        cost = cost_per_seed * n_runs
        budget.spend(cost, what="%d runs of %s" % (n_runs, bench.agent))
        spent["n"] += cost

    class _SwitchedOff(Exception):
        pass

    def score(params, seed):
        # Checked before every run, not once per round. The search path had no
        # switch check at all when it was added: an owner turning the function
        # off mid-round was honoured for a measuring agent and ignored for a
        # searching one, which is the half that spends the most. A test written
        # for the measurement path is what noticed.
        if not agent.switch.on:
            raise _SwitchedOff()
        out = run_domain_task(bench, client=client_factory(seed),
                              workspace=Path(workspace_root) / ("p%d" % abs(hash(
                                  tuple(sorted(params.items())) + (seed,)))),
                              seed=seed, params=params)
        if ledgers is not None:
            ledgers.record(BENCHMARK, {"seed": seed, "params": params,
                                       "passed": out.get("status") == "delivered",
                                       "metrics": out.get("metrics")})
        return out.get("metrics") or {}

    # Continue from the best point this night has found, not from the defaults.
    #
    # Round 2 of the first corrected night repeated round 1 exactly — same
    # candidates, same winner, same numbers — because the search always
    # restarted from the defaults and never consulted the claim. It then
    # penalised itself: as the night's second validation test the corrected p
    # went from 0.044 to 0.089, so looking twice at the same result destroyed
    # it. Continuing from the winner makes the second round explore somewhere
    # new; adoption still needs the owner, so this is search, not adoption.
    # A benchmark with no declared knobs cannot be searched — but a night with
    # nothing to search is still a night of measurement, and the first version
    # of this regressed that to nothing at all: no runs, no spend, no ledger
    # entries, not even a stop. Reproducing and recording IS the work for an
    # agent whose method is fixed, and it is the strongest single use the
    # design claims for these agents.
    if not bench.parameters or not bench.objective:
        return _measure_only(agent, bench, client_factory=client_factory,
                             workspace_root=workspace_root, seeds=seeds,
                             cost_per_seed=cost_per_seed, ledgers=ledgers,
                             claim=claim, budget=budget)

    incumbent = dict(getattr(agent, "_incumbent", None) or bench.defaults())
    try:
        res = run_search(bench, score=score, incumbent=incumbent,
                         search_seeds=search_seeds,
                         validation_seeds=validation_seeds,
                         rounds=rounds, spend=spend,
                         guardrail_direction=bench.guardrail_directions(),
                         prior_validations=getattr(agent, "_validations", 0))
    except BudgetExhausted as e:
        return Round(agent.name, claim.statement if claim else None,
                     bench.objective, spent["n"], stopped=str(e))
    except _SwitchedOff:
        return Round(agent.name, claim.statement if claim else None,
                     bench.objective, spent["n"],
                     stopped="the owner turned it off mid-round")

    if not res.get("searched"):
        # A round must never idle. Searching was impossible — no parameters, no
        # objective, or too few seeds to hold a validation set back — so the
        # night measures instead, which is real work and the strongest single
        # use this design claims for these agents.
        #
        # This is the second time the same hole appeared: first for agents with
        # no parameters at all, and then again for parameterised agents given
        # too few seeds to validate on. Both times the round returned having run
        # nothing, spent nothing and stopped for no stated reason. Falling back
        # on ANY refusal to search closes the shape rather than the instance.
        fell_back = _measure_only(agent, bench, client_factory=client_factory,
                                  workspace_root=workspace_root, seeds=seeds,
                                  cost_per_seed=cost_per_seed, ledgers=ledgers,
                                  claim=claim, budget=budget)
        if fell_back.outcome:
            fell_back.outcome["why"] = "%s; %s" % (
                res.get("why", "could not search"), fell_back.outcome.get("why", ""))
        fell_back.spent += spent["n"]
        return fell_back

    r = Round(agent.name, claim.statement if claim else None,
              bench.objective or "unnamed", spent["n"])
    if False:
        pass
    elif not res.get("improved"):
        r.outcome = no_change(agent.name,
                              because=res.get("why")
                              or "the winner did not hold on the validation seeds")
        r.search = res
    else:
        v = res["validation"]
        r.search = res
        # `comparisons` is the number of times this night has reached for the
        # validation set, not the number of candidates ranked on the search
        # seeds. Selection happened on different data; correcting the held-out
        # test for the size of the search would be double-counting.
        agent._validations = v["validation_tests_this_night"]
        agent._incumbent = dict(res["params"])
        r.improvement = Improvement(
            agent=agent.name, candidate=res["origin"], metric=res["objective"],
            baseline_reproduced=True, held_out=True,
            comparisons=v["validation_tests_this_night"],
            corrected_p=v.get("corrected_p"),
            mechanism="", verifier_passed=True,
            seeds=[SeedResult(s, i, c) for s, i, c
                   in zip(v["seeds"], v["incumbent"], v["candidate"])])
        if not r.improvement.survives():
            r.outcome = no_change(agent.name,
                                  because="; ".join(r.improvement.failures())[:200])
    if ledgers is not None:
        ledgers.record(SELF_DIRECTED,
                       {"claim": r.claim, "metric": r.metric, "spent": spent["n"],
                        "params": res.get("params"),
                        "passed": bool(r.improvement and r.improvement.survives())})
    return r


def _headline_metric(bench: DomainBenchmark, results) -> Optional[str]:
    for r in results:
        m = r.get("metrics")
        if m:
            return sorted(m)[0]
    return None


def autonomous_loop(agent, bench: DomainBenchmark, *, client_factory,
                    workspace_root: Path, rounds: int = 3,
                    seeds: Sequence[int] = (0, 1, 2),
                    cost_per_seed: float = 0.5,
                    ledgers: Optional[Ledgers] = None) -> List[Round]:
    """Rounds until the switch goes off, the budget runs out, or the map is dry.

    None of the three asks for anything."""
    out: List[Round] = []
    for i in range(rounds):
        if not agent.switch.on:
            out.append(Round(agent.name, None, "", 0.0,
                             stopped="the switch is off"))
            break
        if agent.field_map.next_work() is None:
            out.append(Round(agent.name, None, "", 0.0,
                             stopped="the field map is dry — nothing left "
                                     "unchecked that this agent can check"))
            break
        try:
            r = autonomous_round(agent, bench, client_factory=client_factory,
                                 workspace_root=Path(workspace_root) / ("r%d" % i),
                                 seeds=seeds, cost_per_seed=cost_per_seed,
                                 ledgers=ledgers, candidate="round-%d" % i)
        except BudgetExhausted as e:
            out.append(Round(agent.name, None, "", 0.0, stopped=str(e)))
            break
        out.append(r)
        if r.stopped:
            break
        if r.search and r.search.get("searched") and not r.search.get("params"):
            # The search is exhausted at this incumbent. Running it again would
            # re-derive the same answer and spend another validation test doing
            # it, which makes the result worse rather than better.
            out.append(Round(agent.name, None, bench.objective or "", 0.0,
                             stopped="the search found nothing new at this "
                                     "incumbent; another round would re-test "
                                     "the same candidates and cost a correction"))
            break
        # A claim that has been checked is not checked again: the map is how the
        # second night differs from the first.
        if r.claim:
            for key, c in agent.field_map.claims.items():
                if c.statement == r.claim:
                    agent.field_map.reproduced(
                        key, evidence="ran %d seeds of %s" % (len(seeds), bench.agent),
                        agrees=bool(r.improvement and r.improvement.survives()))
                    break
    return out
