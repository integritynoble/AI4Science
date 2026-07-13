from __future__ import annotations
import json
from ai4science.harness.runtime.contract import compile_contract
from ai4science.harness.runtime.verifier import ExternalCommandVerifier
from ai4science.harness.runtime.pev import run_task
from .planner import LLMWorkPlanner, DEFAULT_MODEL, MAX_LLM_TOKENS, llm_text
from .prompt import build_criteria_messages
from .extract import parse_work_action


def propose_criteria(client, run_id: str, objective: str, input_files: list,
                     model: str = DEFAULT_MODEL) -> dict | None:
    """One brokered LLM call proposing success criteria; None if unusable."""
    system, messages = build_criteria_messages(objective, input_files)
    resp = client.llm_egress(run_id, {"model": model, "max_tokens": MAX_LLM_TOKENS,
                                      "system": system, "messages": messages})
    action = parse_work_action(llm_text(resp))
    if action is None or action.action != "propose_criteria":
        return None
    return {"verify_commands": action.verify_commands,
            "required_artifacts": action.required_artifacts}


def run_work_task(*, demand: dict, client, store, task_id: str,
                  interaction_mode: str = "I1", capability_profile: str = "A1",
                  max_steps: int = 20, model: str = DEFAULT_MODEL,
                  prompt_profile: str = "terse", governed: bool = True,
                  on_ask=None, planner=None, propose=None) -> dict:
    """demand = {"objective": str, "input_files": {rel_path: bytes|str}?,
                 "verify_commands": [[argv]]?, "required_artifacts": [paths]?}

    Flow (spec 2026-07-13): stage inputs -> register write-once criteria
    (supplied, or LLM-proposed through the mode gateway: I0/I1 ASK, I2 ACT
    with a recorded assumption) -> PEV loop with the freeform LLM planner ->
    delivery gated by the CP-side command judge."""
    objective = demand["objective"]
    if governed:
        try:
            lkg = client.get_last_known_good("agent", "work")
        except Exception:
            lkg = None
        meta = (lkg or {}).get("metadata") if lkg else None
        if meta:
            if "max_steps" in meta:
                max_steps = int(meta["max_steps"])
            if "prompt_profile" in meta:
                prompt_profile = str(meta["prompt_profile"])
    input_files = demand.get("input_files") or {}
    from ai4science.harness.agents.specs.work import AGENT
    supplied = {"verify_commands": demand.get("verify_commands") or [],
                "required_artifacts": demand.get("required_artifacts") or []}
    has_supplied = bool(supplied["verify_commands"] or supplied["required_artifacts"])
    contract = compile_contract(
        objective=objective, capability_profile=capability_profile,
        interaction_mode=interaction_mode,
        deliverables=list(supplied["required_artifacts"]),
        constraints=list(demand.get("constraints") or []),
        success_criteria=[json.dumps(supplied, sort_keys=True)] if has_supplied else [],
        budget={"tool_calls": max_steps, "runtime_minutes": 90},
        approval_required_for=list(AGENT.approval_required_for))
    run = client.open_run(objective, capability_profile,
                          {"actions": max_steps + 5}, interaction_profile=interaction_mode)
    run_id = run["run_id"]
    for rel, content in input_files.items():
        data = content if isinstance(content, bytes) else str(content).encode()
        staged = client.stage_input(run_id, rel, data)
        if not staged.get("ok"):
            return {"status": "blocked", "task_id": task_id,
                    "why": f"stage_input refused for {rel!r}"}
    if has_supplied:
        criteria = supplied
    else:
        proposer = propose or propose_criteria
        proposal = proposer(client, run_id, objective, sorted(input_files), model)
        if proposal is None:
            return {"status": "blocked", "task_id": task_id,
                    "why": "criteria proposal unusable"}
        summary = "propose success criteria: " + json.dumps(proposal, sort_keys=True)
        decision = client.classify(run_id, "preference_fork", step_summary=summary,
                                   action_type="sandbox_exec")["decision"]
        if decision == "ASK":
            state = store.open_or_resume(task_id, contract)
            store.checkpoint(state)
            if on_ask:
                on_ask(proposal, state)
            return {"status": "awaiting_owner", "task_id": task_id,
                    "proposed_criteria": proposal}
        if decision != "ACT":   # DENY or anything unexpected -> fail closed
            return {"status": "blocked", "task_id": task_id, "why": f"decision {decision}"}
        state = store.open_or_resume(task_id, contract)
        store.record(state, kind="assumption",
                     payload={"assumption": "llm-proposed success criteria (reversible)",
                              "criteria": proposal})
        criteria = proposal
    reg = client.set_criteria(run_id, criteria["verify_commands"],
                              criteria["required_artifacts"])
    if not reg.get("ok"):
        return {"status": "blocked", "task_id": task_id,
                "why": f"set_criteria refused: {reg.get('reason', 'unknown')}"}
    run_planner = planner if planner is not None else LLMWorkPlanner(
        client, run_id, criteria=criteria, model=model, prompt_profile=prompt_profile)
    verifier = ExternalCommandVerifier(client, run_id)
    return run_task(run_id=run_id, contract=contract, client=client,
                    planner=run_planner, verifier=verifier, store=store,
                    task_id=task_id, on_ask=on_ask)
