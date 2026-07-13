from __future__ import annotations
import hashlib
import json
from pathlib import Path
from ai4science.harness.runtime.contract import compile_contract
from ai4science.harness.runtime.verifier import ExternalCommandVerifier
from ai4science.harness.runtime.pev import run_task
from ai4science.harness.agents.work.planner import DEFAULT_MODEL, MAX_LLM_TOKENS, llm_text
from ai4science.harness.agents.research import research_check
from .planner import LLMProcessPlanner
from .prompt import build_coverage_proposal_messages
from .extract import parse_coverage_proposal

# Reuse the generic grounding checker (grounds [S<n>] spans verbatim in staged
# files + SHA-verifies them). For process-learning the "sources" are the trace
# files and the "report" is explanation.md. No new checker code.
_CHECK_SRC = Path(research_check.__file__).read_text()
_DELIVERABLE = "explanation.md"


def _sha(content) -> str:
    data = content if isinstance(content, bytes) else str(content).encode()
    return hashlib.sha256(data).hexdigest()


def propose_coverage(client, run_id, run_label, trace_index, model=DEFAULT_MODEL):
    system, messages = build_coverage_proposal_messages(run_label, trace_index)
    resp = client.llm_egress(run_id, {"model": model, "max_tokens": MAX_LLM_TOKENS,
                                      "system": system, "messages": messages})
    return parse_coverage_proposal(llm_text(resp))


def run_process_learning_task(*, demand, client, store, task_id, interaction_mode="I1",
                              capability_profile="A1", max_steps=25, model=DEFAULT_MODEL,
                              prompt_profile="terse", governed=True, on_ask=None,
                              planner=None, propose=None) -> dict:
    """demand = {"run_label": str, "trace": {name: bytes|str},
                 "coverage_points"?: [str], "deliverable"?: str}
    Stages the verified trace + the (reused) grounding checker; every claim in
    explanation.md must cite a verbatim span from the trace (anti-fabrication).
    Decision points supplied or proposed through the mode gateway."""
    run_label = demand["run_label"]
    trace = demand.get("trace") or {}
    deliverable = demand.get("deliverable", _DELIVERABLE)
    if governed:
        try:
            lkg = client.get_last_known_good("agent", "process-learning")
        except Exception:
            lkg = None
        meta = (lkg or {}).get("metadata") if lkg else None
        if meta:
            if "max_steps" in meta:
                max_steps = int(meta["max_steps"])
            if "prompt_profile" in meta:
                prompt_profile = str(meta["prompt_profile"])

    from ai4science.harness.agents.specs.process_learning import AGENT
    trace_rels = [f"trace/{name}" for name in sorted(trace)]
    contract = compile_contract(
        objective=f"explain trace: {run_label}", capability_profile=capability_profile,
        interaction_mode=interaction_mode, deliverables=[deliverable],
        budget={"tool_calls": max_steps, "runtime_minutes": 90},
        approval_required_for=list(AGENT.approval_required_for))
    run = client.open_run(f"explain trace: {run_label}", capability_profile,
                          {"actions": max_steps + 5}, interaction_profile=interaction_mode)
    run_id = run["run_id"]

    def _stage(rel, content):
        data = content if isinstance(content, bytes) else str(content).encode()
        return client.stage_input(run_id, rel, data).get("ok")
    if not _stage("run_label.txt", run_label):
        return {"status": "blocked", "task_id": task_id, "why": "stage run_label refused"}
    for name, content in trace.items():
        if not _stage(f"trace/{name}", content):
            return {"status": "blocked", "task_id": task_id, "why": f"stage trace {name!r} refused"}
    if not _stage("research_check.py", _CHECK_SRC):
        return {"status": "blocked", "task_id": task_id, "why": "stage checker refused"}

    coverage = demand.get("coverage_points")
    if not coverage:
        proposer = propose or propose_coverage
        proposed = proposer(client, run_id, run_label, trace_rels, model)
        if not proposed:
            return {"status": "blocked", "task_id": task_id, "why": "coverage proposal unusable"}
        summary = "propose decision points: " + json.dumps(proposed)
        decision = client.classify(run_id, "preference_fork", step_summary=summary,
                                   action_type="sandbox_exec")["decision"]
        if decision == "ASK":
            state = store.open_or_resume(task_id, contract)
            store.checkpoint(state)
            if on_ask:
                on_ask(proposed, state)
            return {"status": "awaiting_owner", "task_id": task_id, "proposed_coverage": proposed}
        if decision != "ACT":
            return {"status": "blocked", "task_id": task_id, "why": f"decision {decision}"}
        state = store.open_or_resume(task_id, contract)
        store.record(state, kind="assumption",
                     payload={"assumption": "llm-proposed decision points (reversible)",
                              "coverage_points": proposed})
        coverage = proposed

    trace_hashes = {f"trace/{name}": _sha(content) for name, content in trace.items()}
    config = {"report": deliverable, "sources": trace_hashes, "coverage_points": list(coverage)}
    verify = [["python3", "-I", "research_check.py", "--config", json.dumps(config, sort_keys=True)]]
    reg = client.set_criteria(run_id, verify, [deliverable])
    if not reg.get("ok"):
        return {"status": "blocked", "task_id": task_id,
                "why": f"set_criteria refused: {reg.get('reason', 'unknown')}"}

    run_planner = planner if planner is not None else LLMProcessPlanner(
        client, run_id, run_label=run_label, coverage_points=coverage,
        trace_index=trace_rels, model=model, prompt_profile=prompt_profile)
    verifier = ExternalCommandVerifier(client, run_id)
    return run_task(run_id=run_id, contract=contract, client=client,
                    planner=run_planner, verifier=verifier, store=store,
                    task_id=task_id, on_ask=on_ask)
