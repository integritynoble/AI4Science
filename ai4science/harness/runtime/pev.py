from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol
from .task_store import TaskStore, TaskState
from .verifier import Verdict

_EXTERNAL = {"network_egress", "publish", "send", "delete", "spend", "deploy"}
MAX_STEPS = 50

@dataclass
class PlanStep:
    summary: str
    command: list
    action_type: str = "sandbox_exec"
    flagged_kind: str | None = None
    done: bool = False

class Planner(Protocol):
    def next_step(self, state: TaskState) -> PlanStep: ...
    def replan(self, state: TaskState, verdict: Verdict) -> None: ...

def detect_boundary(step: PlanStep, state: TaskState) -> str:
    approval = [a.lower() for a in state.contract.approval_required_for]
    if step.action_type in _EXTERNAL or any(a in step.summary.lower() for a in approval):
        return "irreversible_or_external"
    if step.flagged_kind in {"preference_fork", "blocker"}:
        return step.flagged_kind
    if state.journal and state.journal[-1].get("failed"):
        return "recoverable_failure"
    return "routine"

def run_task(*, run_id, contract, client, planner, verifier, store, task_id, on_ask=None) -> dict:
    state = store.open_or_resume(task_id, contract)
    steps = 0
    while not state.finished and steps < MAX_STEPS:
        steps += 1
        step = planner.next_step(state)
        if step.done:
            store.record(state, kind="finish", payload={"status": "delivered"})
            return {"status": "delivered", "task_id": task_id}
        kind = detect_boundary(step, state)
        decision = client.classify(run_id, kind, step_summary=step.summary,
                                   action_type=step.action_type)["decision"]
        if decision == "ASK":
            store.checkpoint(state)
            if on_ask:
                on_ask(step, state)
            return {"status": "awaiting_owner", "task_id": task_id, "step": step.summary}
        if decision == "DENY":
            store.record(state, kind="finish", payload={"status": "blocked", "why": "denied"})
            return {"status": "blocked", "task_id": task_id, "why": "denied"}
        result = client.sandbox_execute(run_id, step.command, scope=None,
                                        net_allowlist=None, workspace_target=None)
        verdict = verifier.check(result, contract)
        store.record(state, kind="step", payload={"plan": step.summary,
                                                  "failed": bool(result.get("is_error")),
                                                  "complete": verdict.complete})
        store.checkpoint(state)
        if verdict.complete:
            store.record(state, kind="finish", payload={"status": "delivered"})
            return {"status": "delivered", "task_id": task_id}
        if verdict.repairable:
            planner.replan(state, verdict)
            continue
        store.record(state, kind="finish", payload={"status": "blocked", "why": "unverifiable"})
        return {"status": "blocked", "task_id": task_id, "why": "unverifiable"}
    return {"status": "blocked", "task_id": task_id, "why": "step budget exhausted"}
