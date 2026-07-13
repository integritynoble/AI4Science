from __future__ import annotations
import hashlib
import json
from pathlib import Path
from ai4science.harness.runtime.contract import compile_contract
from ai4science.harness.runtime.verifier import ExternalCommandVerifier
from ai4science.harness.runtime.pev import run_task
from ai4science.harness.agents.work.planner import DEFAULT_MODEL, MAX_LLM_TOKENS, llm_text
from .planner import LLMLearningPlanner
from .prompt import build_coverage_proposal_messages
from .extract import parse_coverage_proposal

_CHECK_SRC = (Path(__file__).parent / "quiz_check.py").read_text()
_DELIVERABLES = ["study_guide.md", "quiz.json"]


def _sha(content) -> str:
    data = content if isinstance(content, bytes) else str(content).encode()
    return hashlib.sha256(data).hexdigest()


def propose_coverage(client, run_id, topic, sources_index, model=DEFAULT_MODEL):
    system, messages = build_coverage_proposal_messages(topic, sources_index)
    resp = client.llm_egress(run_id, {"model": model, "max_tokens": MAX_LLM_TOKENS,
                                      "system": system, "messages": messages})
    return parse_coverage_proposal(llm_text(resp))


def run_learning_task(*, demand, client, store, task_id, interaction_mode="I1",
                      capability_profile="A1", max_steps=30, model=DEFAULT_MODEL,
                      prompt_profile="terse", governed=True, on_ask=None,
                      planner=None, propose=None) -> dict:
    """demand = {"topic": str, "material": {name: bytes|str},
                 "min_questions"?: int, "coverage_points"?: [str]}
    Stages topic + material + quiz_check.py; the grounding gate re-checks the
    authored study_guide.md + quiz.json; coverage points supplied or proposed
    through the mode gateway (I0/I1 ASK, I2 ACT)."""
    topic = demand["topic"]
    material = demand.get("material") or {}
    min_questions = int(demand.get("min_questions", 3))
    if governed:
        try:
            lkg = client.get_last_known_good("agent", "learning")
        except Exception:
            lkg = None
        meta = (lkg or {}).get("metadata") if lkg else None
        if meta:
            if "max_steps" in meta:
                max_steps = int(meta["max_steps"])
            if "prompt_profile" in meta:
                prompt_profile = str(meta["prompt_profile"])

    from ai4science.harness.agents.specs.learning import AGENT
    source_rels = [f"material/{name}" for name in sorted(material)]
    contract = compile_contract(
        objective=f"teach: {topic}", capability_profile=capability_profile,
        interaction_mode=interaction_mode, deliverables=list(_DELIVERABLES),
        budget={"tool_calls": max_steps, "runtime_minutes": 90},
        approval_required_for=list(AGENT.approval_required_for))
    run = client.open_run(f"teach: {topic}", capability_profile,
                          {"actions": max_steps + 5}, interaction_profile=interaction_mode)
    run_id = run["run_id"]

    def _stage(rel, content):
        data = content if isinstance(content, bytes) else str(content).encode()
        return client.stage_input(run_id, rel, data).get("ok")
    if not _stage("topic.txt", topic):
        return {"status": "blocked", "task_id": task_id, "why": "stage topic refused"}
    for name, content in material.items():
        if not _stage(f"material/{name}", content):
            return {"status": "blocked", "task_id": task_id, "why": f"stage material {name!r} refused"}
    if not _stage("quiz_check.py", _CHECK_SRC):
        return {"status": "blocked", "task_id": task_id, "why": "stage checker refused"}

    coverage = demand.get("coverage_points")
    if not coverage:
        proposer = propose or propose_coverage
        proposed = proposer(client, run_id, topic, source_rels, model)
        if not proposed:
            return {"status": "blocked", "task_id": task_id, "why": "coverage proposal unusable"}
        summary = "propose coverage points: " + json.dumps(proposed)
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
                     payload={"assumption": "llm-proposed coverage points (reversible)",
                              "coverage_points": proposed})
        coverage = proposed

    source_hashes = {f"material/{name}": _sha(content) for name, content in material.items()}
    config = {"study_guide": "study_guide.md", "quiz": "quiz.json",
              "sources": source_hashes, "min_questions": min_questions,
              "coverage_points": list(coverage)}
    verify = [["python3", "-I", "quiz_check.py", "--config", json.dumps(config, sort_keys=True)]]
    reg = client.set_criteria(run_id, verify, list(_DELIVERABLES))
    if not reg.get("ok"):
        return {"status": "blocked", "task_id": task_id,
                "why": f"set_criteria refused: {reg.get('reason', 'unknown')}"}

    run_planner = planner if planner is not None else LLMLearningPlanner(
        client, run_id, topic=topic, coverage_points=coverage,
        sources_index=source_rels, model=model, prompt_profile=prompt_profile)
    verifier = ExternalCommandVerifier(client, run_id)
    return run_task(run_id=run_id, contract=contract, client=client,
                    planner=run_planner, verifier=verifier, store=store,
                    task_id=task_id, on_ask=on_ask)
