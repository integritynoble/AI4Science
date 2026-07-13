from __future__ import annotations
from dataclasses import dataclass, field
from typing import Protocol
from .task_store import TaskStore, TaskState
from .verifier import Verdict

_EXTERNAL = {"network_egress", "publish", "send", "delete", "spend", "deploy"}
_SAFE_ACTIONS = {"sandbox_exec", "read"}
MAX_STEPS = 50

@dataclass
class PlanStep:
    summary: str
    command: list
    action_type: str = "sandbox_exec"
    flagged_kind: str | None = None
    done: bool = False
    stage_files: dict = field(default_factory=dict)   # {rel_path: text} staged via /stage_input
    request_verify: bool = True                       # False -> skip verifier, keep looping

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
    if step.action_type in _SAFE_ACTIONS:
        return "routine"
    return "irreversible_or_external"   # unknown/None action_type -> fail safe (never routine)

def run_task(*, run_id, contract, client, planner, verifier, store, task_id, on_ask=None) -> dict:
    state = store.open_or_resume(task_id, contract)
    if state.finished:
        return {"status": state.final_status or "delivered", "task_id": task_id, "resumed": True}
    max_steps = int(state.contract.budget.get("tool_calls", MAX_STEPS))
    steps = 0
    while not state.finished and steps < max_steps:
        steps += 1
        step = planner.next_step(state)
        if step.done:
            store.record(state, kind="finish", payload={"status": "blocked",
                         "why": "planner exhausted without verified completion"})
            return {"status": "blocked", "task_id": task_id,
                    "why": "planner exhausted without verified completion"}
        kind = detect_boundary(step, state)
        decision = client.classify(run_id, kind, step_summary=step.summary,
                                   action_type=step.action_type)["decision"]
        if decision == "ASK":
            store.checkpoint(state)
            if on_ask:
                on_ask(step, state)
            return {"status": "awaiting_owner", "task_id": task_id, "step": step.summary}
        if decision != "ACT":   # DENY or ANY unexpected value -> fail closed, never execute
            store.record(state, kind="finish", payload={"status": "blocked", "why": f"decision {decision}"})
            return {"status": "blocked", "task_id": task_id, "why": f"decision {decision}"}
        for rel_path, content in (step.stage_files or {}).items():
            staged = client.stage_input(run_id, rel_path, content.encode())
            if not staged.get("ok"):
                why = f"stage_input refused for {rel_path!r}"
                store.record(state, kind="finish", payload={"status": "blocked", "why": why})
                return {"status": "blocked", "task_id": task_id, "why": why}
        if step.command:
            result = client.sandbox_execute(run_id, step.command, scope=None,
                                            net_allowlist=None, workspace_target=None)
        else:
            result = {"exit_code": 0, "is_error": False, "skipped": True}
        verdict = verifier.check(result, contract) if step.request_verify else None
        store.record(state, kind="step", payload={
            "plan": step.summary,
            "failed": bool(result.get("is_error")),
            "complete": bool(verdict and verdict.complete),
            "exit_code": result.get("exit_code"),
            "stdout_tail": (result.get("stdout") or "")[-2000:],
            "stderr_tail": (result.get("stderr") or "")[-2000:],
        })
        store.checkpoint(state)
        if verdict is None:
            continue
        if verdict.complete:
            store.record(state, kind="finish", payload={"status": "delivered"})
            return {"status": "delivered", "task_id": task_id}
        if verdict.repairable:
            planner.replan(state, verdict)
            continue
        store.record(state, kind="finish", payload={"status": "blocked", "why": "unverifiable"})
        return {"status": "blocked", "task_id": task_id, "why": "unverifiable"}
    return {"status": "blocked", "task_id": task_id, "why": "step budget exhausted"}
