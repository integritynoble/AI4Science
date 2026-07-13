from __future__ import annotations
from ai4science.harness.runtime.pev import PlanStep, run_task
from ai4science.harness.runtime.verifier import ExternalCommandVerifier
from ai4science.harness.runtime.contract import compile_contract

DEFAULT_WORK_GRID = [
    {"prompt_profile": "terse", "max_steps": 8},
    {"prompt_profile": "terse", "max_steps": 20},
    {"prompt_profile": "checklist", "max_steps": 8},
    {"prompt_profile": "checklist", "max_steps": 20},
]


def config_id(cfg: dict) -> str:
    return f"{cfg['prompt_profile']}_s{cfg['max_steps']}"


class ScriptedWorkPlanner:
    """Deterministic planner for RSI scoring/CI: emits one artifact-producing
    step then a verify step. Its behavior is a pure function of the config; the
    seeded corpus + the CP command judge decide pass/fail. (Real scoring uses
    LLMWorkPlanner; that is the deferred real-LLM increment.)"""
    def __init__(self, config: dict, task_hint=None):
        self._config = config
        self._task_hint = task_hint
        self._emitted = False

    def next_step(self, state) -> PlanStep:
        if not self._emitted:
            self._emitted = True
            # A generic "produce the expected artifact" step. In the deterministic
            # unit path the StubClient scores directly; in the podman path the
            # scripted commands below satisfy the seeded task templates.
            return PlanStep(summary="produce artifact", command=["true"],
                            request_verify=False)
        return PlanStep(summary="verify", command=[], request_verify=True)

    def replan(self, state, verdict) -> None:
        pass


def run_work_rsi_round(*, client, held_out_task_ids, candidates=DEFAULT_WORK_GRID,
                       planner_factory, store_factory, domain="work_search",
                       capability_profile="A1", interaction_mode="I2") -> dict:
    """Score every candidate config on every held-out task under ONE control-plane
    run for the whole round (required so /evaluate_candidates' _candidate_round_means
    can derive per-candidate means from score_heldout audit records filtered by a
    single run_id). /stage_worktask clears the run workspace and overwrites criteria
    on every call, so staging task N in the shared run gives each task a clean slate.
    Ranks candidates by (mean pass-rate desc, total steps asc)."""
    max_step_budget = max(c["max_steps"] for c in candidates)
    run = client.open_run(
        "work rsi round", capability_profile,
        {"actions": len(candidates) * len(held_out_task_ids) * (max_step_budget + 5) + 1},
        interaction_profile=interaction_mode)
    run_id = run["run_id"]

    results = []
    for cfg in candidates:
        cid = config_id(cfg)
        # planner_factory(cfg) returns a zero-arg maker; call it fresh per task_id so
        # each held-out task's PEV loop starts with clean planner state (e.g.
        # ScriptedWorkPlanner._emitted reset), rather than reusing one planner
        # instance whose internal state carried over from a prior task.
        make_planner = planner_factory(cfg)
        passes, total_steps = [], 0
        for task_id in held_out_task_ids:
            client.stage_worktask(run_id, task_id, domain=domain)
            contract = compile_contract(objective=f"held-out task {task_id}",
                                        capability_profile=capability_profile,
                                        interaction_mode=interaction_mode,
                                        budget={"tool_calls": cfg["max_steps"],
                                                "runtime_minutes": 90})
            run_task(run_id=run_id, contract=contract, client=client,
                     planner=make_planner(),
                     verifier=ExternalCommandVerifier(client, run_id),
                     store=store_factory(), task_id=f"{run_id}-{cid}-t{task_id}")
            score = client.score_worktask(run_id, task_id, domain=domain, version=cid)
            passes.append(score.get("pass", 0.0) or 0.0)
            total_steps += int(score.get("steps", 0) or 0)
        mean_pass = sum(passes) / len(passes) if passes else 0.0
        client.register_version("agent", "work", cid,
                                {"prompt_profile": cfg["prompt_profile"],
                                 "max_steps": cfg["max_steps"],
                                 "mean_pass": mean_pass, "total_steps": total_steps})
        results.append({"version": cid, "mean_psnr": mean_pass, "total_steps": total_steps})

    # Reuse key `mean_psnr` because /evaluate_candidates binds on that field name
    # (the endpoint is metric-agnostic; the value here is the pass-rate).
    evaluation = client.evaluate_candidates(run_id, results=[
        {"version": r["version"], "mean_psnr": r["mean_psnr"]} for r in results],
        domain=domain)
    ranked = sorted(((r["version"], r["mean_psnr"], r["total_steps"]) for r in results),
                    key=lambda item: (-(item[1] or 0.0), item[2]))
    return {"ranked": ranked, "eval_ref": evaluation.get("eval_ref")}


def _incumbent_work_config(client) -> dict:
    try:
        lkg = client.get_last_known_good("agent", "work")
    except Exception:
        lkg = None
    meta = (lkg or {}).get("metadata") if lkg else None
    if meta and "prompt_profile" in meta and "max_steps" in meta:
        return {"prompt_profile": str(meta["prompt_profile"]), "max_steps": int(meta["max_steps"])}
    return {"prompt_profile": "terse", "max_steps": 20}


def run_work_rsi_search(*, client, planner_factory, store_factory,
                        search_task_ids, val_task_ids, candidates=DEFAULT_WORK_GRID,
                        search_domain="work_search", val_domain="work_val",
                        round_fn=None) -> dict:
    """v1: score the fixed grid on the search set, rank, then run a validation
    round scoring the best config + the incumbent on the untouched val set.
    Promotion (owner-signed, Gate B) is gated on val_pass vs incumbent_val_pass."""
    round_fn = round_fn or run_work_rsi_round
    incumbent = _incumbent_work_config(client)

    search = round_fn(client=client, held_out_task_ids=search_task_ids,
                      candidates=candidates, planner_factory=planner_factory,
                      store_factory=store_factory, domain=search_domain)
    ranked = search["ranked"]
    best_id = ranked[0][0]
    best = next(c for c in candidates if config_id(c) == best_id)

    val_cands = [best] if config_id(best) == config_id(incumbent) else [best, incumbent]
    val = round_fn(client=client, held_out_task_ids=val_task_ids,
                   candidates=val_cands, planner_factory=planner_factory,
                   store_factory=store_factory, domain=val_domain)
    val_scores = {cid: p for cid, p, _ in val["ranked"]}
    return {"best_config": best, "search_pass": ranked[0][1],
            "val_pass": val_scores.get(config_id(best)),
            "incumbent_val_pass": val_scores.get(config_id(incumbent)),
            "ranked": ranked, "val_eval_ref": val["eval_ref"]}
