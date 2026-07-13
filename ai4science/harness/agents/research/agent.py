from __future__ import annotations
import hashlib
import json
from pathlib import Path
from ai4science.harness.runtime.contract import compile_contract
from ai4science.harness.runtime.verifier import ExternalCommandVerifier
from ai4science.harness.runtime.pev import run_task
from ai4science.harness.agents.work.planner import DEFAULT_MODEL, MAX_LLM_TOKENS, llm_text
from .planner import LLMResearchPlanner
from .prompt import build_coverage_proposal_messages
from .extract import parse_coverage_proposal

_CHECK_SRC = (Path(__file__).parent / "research_check.py").read_text()


def _sha(content) -> str:
    data = content if isinstance(content, bytes) else str(content).encode()
    return hashlib.sha256(data).hexdigest()


def propose_coverage(client, run_id, question, sources_index, model=DEFAULT_MODEL):
    system, messages = build_coverage_proposal_messages(question, sources_index)
    resp = client.llm_egress(run_id, {"model": model, "max_tokens": MAX_LLM_TOKENS,
                                      "system": system, "messages": messages})
    return parse_coverage_proposal(llm_text(resp))


def run_research_task(*, demand, client, store, task_id, interaction_mode="I1",
                      capability_profile="A1", max_steps=25, model=DEFAULT_MODEL,
                      prompt_profile="terse", governed=True, on_ask=None,
                      planner=None, propose=None) -> dict:
    """demand = {"question": str, "sources": {name: bytes|str},
                 "coverage_points": [str]?, "deliverable": "report.md"?}
    Stages question + sources + research_check.py; the fixed grounding verify
    command gates delivery; coverage points are supplied or LLM-proposed
    through the mode gateway (I0/I1 ASK, I2 ACT)."""
    question = demand["question"]
    sources = demand.get("sources") or {}
    report_name = demand.get("deliverable", "report.md")
    if governed:
        try:
            lkg = client.get_last_known_good("agent", "research")
        except Exception:
            lkg = None
        meta = (lkg or {}).get("metadata") if lkg else None
        if meta:
            if "max_steps" in meta:
                max_steps = int(meta["max_steps"])
            if "prompt_profile" in meta:
                prompt_profile = str(meta["prompt_profile"])

    from ai4science.harness.agents.specs.research import AGENT
    source_rels = [f"sources/{name}" for name in sorted(sources)]
    contract = compile_contract(
        objective=f"research: {question}", capability_profile=capability_profile,
        interaction_mode=interaction_mode, deliverables=[report_name],
        budget={"tool_calls": max_steps, "runtime_minutes": 90},
        approval_required_for=list(AGENT.approval_required_for))
    run = client.open_run(f"research: {question}", capability_profile,
                          {"actions": max_steps + 5}, interaction_profile=interaction_mode)
    run_id = run["run_id"]

    # stage question, sources, and the grounding checker
    def _stage(rel, content):
        data = content if isinstance(content, bytes) else str(content).encode()
        return client.stage_input(run_id, rel, data).get("ok")
    if not _stage("question.txt", question):
        return {"status": "blocked", "task_id": task_id, "why": "stage question refused"}
    for name, content in sources.items():
        if not _stage(f"sources/{name}", content):
            return {"status": "blocked", "task_id": task_id, "why": f"stage source {name!r} refused"}
    if not _stage("research_check.py", _CHECK_SRC):
        return {"status": "blocked", "task_id": task_id, "why": "stage checker refused"}

    # coverage points: supplied or proposed through the mode gateway
    coverage = demand.get("coverage_points")
    if not coverage:
        proposer = propose or propose_coverage
        proposed = proposer(client, run_id, question, source_rels, model)
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

    # build the CP-private config (report / source SHAs / coverage) and register
    # the grounding gate; the config rides the verify-command argv in criteria.json,
    # so the agent can alter neither the parameters nor (via SHA) the sources.
    source_hashes = {f"sources/{name}": _sha(content) for name, content in sources.items()}
    config = {"report": report_name, "sources": source_hashes, "coverage_points": list(coverage)}
    verify = [["python3", "-I", "research_check.py", "--config", json.dumps(config, sort_keys=True)]]
    reg = client.set_criteria(run_id, verify, [report_name])
    if not reg.get("ok"):
        return {"status": "blocked", "task_id": task_id,
                "why": f"set_criteria refused: {reg.get('reason', 'unknown')}"}

    run_planner = planner if planner is not None else LLMResearchPlanner(
        client, run_id, question=question, coverage_points=coverage,
        sources_index=source_rels, model=model, prompt_profile=prompt_profile)
    verifier = ExternalCommandVerifier(client, run_id)
    return run_task(run_id=run_id, contract=contract, client=client,
                    planner=run_planner, verifier=verifier, store=store,
                    task_id=task_id, on_ask=on_ask)
